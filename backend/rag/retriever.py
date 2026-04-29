"""
retriever.py
------------
RAG Pipeline — Step 2: Semantic search over the ingested codebase.

Implements hybrid search (vector similarity + keyword matching) to maximize
retrieval accuracy. The retriever is exposed as a LangChain-compatible tool
so CrewAI agents can call it directly.

Interview talking point:
    "Pure vector search misses exact keyword matches (variable names, function
     names). Hybrid search combines semantic understanding with keyword recall.
     I merge and re-rank both result sets using Reciprocal Rank Fusion (RRF)."
"""

import logging
from pathlib import Path
from typing import Optional

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import tool

from backend.config import settings
from backend.project_manager import get_active_collection_name

logger = logging.getLogger(__name__)


def _preview_text(text: str, limit: int = 280) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _get_vectorstore(collection_name: str = "codebase") -> Chroma:
    """Load an existing ChromaDB collection from disk."""
    persist_dir = str(Path(settings.chroma_persist_dir).resolve())
    embeddings = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
    )
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_dir,
    )


def _reciprocal_rank_fusion(
    vector_results: list[Document],
    keyword_results: list[Document],
    k: int = 60,
) -> list[Document]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion (RRF).

    RRF score = sum of 1/(rank + k) across all result lists.
    Documents appearing in both lists get a boosted score.
    This is the industry-standard re-ranking technique for hybrid search.
    """
    scores: dict[str, tuple[float, Document]] = {}

    for rank, doc in enumerate(vector_results):
        doc_id = doc.page_content[:80]  # Use content prefix as unique key
        prev_score = scores.get(doc_id, (0.0, doc))[0]
        scores[doc_id] = (prev_score + 1.0 / (rank + k), doc)

    for rank, doc in enumerate(keyword_results):
        doc_id = doc.page_content[:80]
        prev_score = scores.get(doc_id, (0.0, doc))[0]
        scores[doc_id] = (prev_score + 1.0 / (rank + k), doc)

    # Sort by descending RRF score
    ranked = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    return [doc for _, doc in ranked]


def hybrid_search(
    query: str,
    collection_name: str | None = None,
    k: int = None,
) -> list[Document]:
    """
    Perform hybrid search: vector similarity + keyword (BM25-style) matching.

    Args:
        query:           Natural language or code query string.
        collection_name: ChromaDB collection to search.
        k:               Number of results to return (defaults to settings.retrieval_k).

    Returns:
        Ranked list of Document chunks with file path metadata.
    """
    k = k or settings.retrieval_k
    collection_name = collection_name or get_active_collection_name("codebase")

    try:
        vectorstore = _get_vectorstore(collection_name)
    except Exception as e:
        logger.error(f"Could not load collection '{collection_name}': {e}")
        return []

    # ── Vector Similarity Search ─────────────────────────────────────────────
    try:
        vector_results = vectorstore.similarity_search(query, k=k * 2)
    except Exception as e:
        logger.warning(f"Vector search failed: {e}")
        vector_results = []

    # ── Keyword Search ───────────────────────────────────────────────────────
    # ChromaDB supports $contains for simple keyword filtering (BM25 alternative)
    # This catches exact function names/variable names semantic search might miss
    try:
        keyword_results = vectorstore.get(
            where_document={"$contains": query.split()[0] if query.split() else query},
            limit=k * 2,
            include=["documents", "metadatas"],
        )
        # Convert raw get() output to Document objects
        kw_docs = [
            Document(
                page_content=keyword_results["documents"][i],
                metadata=keyword_results["metadatas"][i],
            )
            for i in range(len(keyword_results["documents"]))
        ]
    except Exception as e:
        logger.debug(f"Keyword search skipped: {e}")
        kw_docs = []

    # ── Merge with RRF ───────────────────────────────────────────────────────
    if vector_results and kw_docs:
        merged = _reciprocal_rank_fusion(vector_results, kw_docs)
    elif vector_results:
        merged = vector_results
    else:
        merged = kw_docs

    return merged[:k]


def format_results_for_agent(results: list[Document]) -> str:
    """
    Format retrieval results into a clean string for agent prompts.
    Includes file path citations for every chunk.
    """
    if not results:
        return "No relevant code found in the codebase."

    formatted_chunks = []
    for i, doc in enumerate(results, 1):
        file_path = doc.metadata.get("file_path", "unknown")
        language = doc.metadata.get("file_extension", "").lstrip(".")
        chunk_idx = doc.metadata.get("chunk_index", "?")
        total = doc.metadata.get("total_chunks", "?")

        formatted_chunks.append(
            f"--- Result {i}: {file_path} (chunk {chunk_idx}/{total}) ---\n"
            f"```{language}\n{doc.page_content}\n```"
        )

    return "\n\n".join(formatted_chunks)


def serialize_results(results: list[Document]) -> list[dict]:
    """Serialize retrieval results for API/UI consumption."""
    serialized: list[dict] = []

    for doc in results:
        file_path = doc.metadata.get("file_path", "unknown")
        language = doc.metadata.get("file_extension", "").lstrip(".")
        serialized.append(
            {
                "file_path": file_path,
                "language": language,
                "chunk_index": doc.metadata.get("chunk_index", "?"),
                "total_chunks": doc.metadata.get("total_chunks", "?"),
                "preview": _preview_text(doc.page_content),
            }
        )

    return serialized


# ── LangChain Tool (used by CrewAI agents) ──────────────────────────────────
@tool
def search_codebase(query: str) -> str:
    """
    Search the ingested codebase using semantic + keyword hybrid search.
    Use this to find relevant code, functions, classes, or implementations
    before planning changes. Always search before writing new code.

    Args:
        query: A natural language description or code snippet to search for.

    Returns:
        Relevant code chunks with file path citations.
    """
    logger.info(f"[RAG Tool] Searching codebase: '{query[:60]}...'")
    results = hybrid_search(query)
    formatted = format_results_for_agent(results)
    logger.info(f"[RAG Tool] Returned {len(results)} chunks")
    return formatted


# ── Standalone retriever class for non-tool usage ───────────────────────────
class CodebaseRetriever:
    """
    Retriever class that can be used directly in LangGraph nodes
    or as a LangChain BaseRetriever-compatible component.
    """

    def __init__(self, collection_name: str | None = None):
        self.collection_name = collection_name or get_active_collection_name("codebase")

    def get_relevant_documents(self, query: str) -> list[Document]:
        return hybrid_search(query, self.collection_name)

    def get_context_string(self, query: str) -> str:
        docs = self.get_relevant_documents(query)
        return format_results_for_agent(docs)


# ── CLI entrypoint ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Query the ingested codebase")
    parser.add_argument("--query", required=True, help="Natural language search query")
    parser.add_argument("--collection", default="codebase", help="ChromaDB collection to search")
    parser.add_argument("--k", type=int, default=5, help="Number of results to return")
    args = parser.parse_args()

    results = hybrid_search(args.query, args.collection, args.k)
    print(format_results_for_agent(results))
