"""
ingestion.py
------------
RAG Pipeline — Step 1: Codebase ingestion into ChromaDB.

Pipeline flow:
    Directory / ZIP  →  File Loading  →  Language-Aware Chunking
    →  Gemini Embeddings  →  ChromaDB (persisted to disk)

Interview talking point:
    "I used RecursiveCharacterTextSplitter.from_language() so the chunker
     respects function and class boundaries instead of splitting blindly at
     character count. Combined with file-path metadata, the retriever can
     cite exact source locations."
"""

import os
import zipfile
import tempfile
import logging
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    Language,
)
from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.config import settings

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


# ── Language extension map ─────────────────────────────────────────────────────
# Maps file extensions to LangChain Language enum for smart splitting.
LANGUAGE_MAP: dict[str, Language] = {
    ".py":   Language.PYTHON,
    ".js":   Language.JS,
    ".ts":   Language.JS,       # TypeScript uses JS splitter
    ".jsx":  Language.JS,
    ".tsx":  Language.JS,
    ".java": Language.JAVA,
    ".go":   Language.GO,
    ".rs":   Language.RUST,
    ".cpp":  Language.CPP,
    ".c":    Language.C,
    ".cs":   Language.CSHARP,
    ".rb":   Language.RUBY,
    ".md":   Language.MARKDOWN,
    ".html": Language.HTML,
}

# File types we support (everything else is skipped)
SUPPORTED_EXTENSIONS = set(LANGUAGE_MAP.keys()) | {
    ".txt", ".json", ".yaml", ".yml", ".toml", ".env.example", ".sh"
}

# Max file size to ingest (skip minified/generated files)
MAX_FILE_SIZE_BYTES = 500_000  # 500KB


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Return Gemini embedding model instance."""
    return GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
    )


def _load_files_from_directory(directory: str) -> list[Document]:
    """
    Walk a directory and load all supported source files.
    Each file becomes a LangChain Document with rich metadata.
    """
    docs: list[Document] = []
    base_path = Path(directory).resolve()

    for file_path in base_path.rglob("*"):
        # Skip directories, hidden files, and unsupported types
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
        if file_path.suffix not in SUPPORTED_EXTENSIONS:
            continue
        if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
            logger.warning(f"Skipping large file: {file_path.name}")
            continue

        # Skip common non-source directories
        parts = file_path.parts
        if any(p in parts for p in ["node_modules", "__pycache__", ".git", "dist", "build", ".venv", "venv"]):
            continue

        try:
            loader = TextLoader(str(file_path), encoding="utf-8", autodetect_encoding=True)
            file_docs = loader.load()

            # Enrich each document's metadata
            for doc in file_docs:
                doc.metadata.update({
                    "file_path": str(file_path.relative_to(base_path)),
                    "file_name": file_path.name,
                    "file_extension": file_path.suffix,
                    "language": LANGUAGE_MAP.get(file_path.suffix, "text"),
                    "file_size": file_path.stat().st_size,
                })
            docs.extend(file_docs)

        except Exception as e:
            logger.warning(f"Could not load {file_path.name}: {e}")
            continue

    logger.info(f"Loaded {len(docs)} files from {directory}")
    return docs


def _split_documents(documents: list[Document]) -> list[Document]:
    """
    Split documents into chunks using language-aware splitters.
    Language-specific splitters respect function/class boundaries.
    """
    all_chunks: list[Document] = []

    for doc in documents:
        extension = doc.metadata.get("file_extension", "")
        language = LANGUAGE_MAP.get(extension)

        try:
            if language:
                # Language-aware splitting: preserves syntax structure
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=language,
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                )
            else:
                # Generic splitting for config/data files
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                )

            chunks = splitter.split_documents([doc])

            # Add chunk index to metadata for ordering
            for i, chunk in enumerate(chunks):
                chunk.metadata["chunk_index"] = i
                chunk.metadata["total_chunks"] = len(chunks)

            all_chunks.extend(chunks)

        except Exception as e:
            logger.warning(f"Failed to split {doc.metadata.get('file_name')}: {e}")
            continue

    logger.info(f"Created {len(all_chunks)} chunks from {len(documents)} files")
    return all_chunks


def ingest_directory(
    directory: str,
    collection_name: str = "codebase",
    overwrite: bool = False,
) -> Chroma:
    """
    Full ingestion pipeline: Load → Chunk → Embed → Store in ChromaDB.

    Args:
        directory:       Path to the codebase directory to ingest.
        collection_name: ChromaDB collection name (one per project).
        overwrite:       If True, deletes existing collection before re-ingesting.

    Returns:
        Chroma vectorstore instance (ready for retrieval).
    """
    logger.info(f"Starting ingestion of '{directory}' → collection '{collection_name}'")

    persist_dir = Path(settings.chroma_persist_dir).resolve()
    persist_dir.mkdir(parents=True, exist_ok=True)

    embeddings = _get_embeddings()

    # Check if collection already exists
    if not overwrite:
        try:
            existing = Chroma(
                collection_name=collection_name,
                embedding_function=embeddings,
                persist_directory=str(persist_dir),
            )
            count = existing._collection.count()
            if count > 0:
                logger.info(f"Collection '{collection_name}' already has {count} chunks. Skipping re-ingestion.")
                logger.info("Pass overwrite=True to force re-ingestion.")
                return existing
        except Exception:
            pass  # Collection doesn't exist yet — proceed with fresh ingestion

    # Step 1: Load
    documents = _load_files_from_directory(directory)
    if not documents:
        raise ValueError(f"No supported files found in '{directory}'")

    # Step 2: Chunk
    chunks = _split_documents(documents)
    if not chunks:
        raise ValueError("Document splitting produced no chunks — check your files.")

    # Step 3: Embed + Store (Chroma handles both in one call)
    logger.info(f"Embedding {len(chunks)} chunks with Gemini... (this may take a moment)")
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=str(persist_dir),
    )

    logger.info(f"✅ Ingestion complete. {len(chunks)} chunks stored in '{collection_name}'")
    return vectorstore


def ingest_zip(
    zip_path: str,
    collection_name: str = "codebase",
    overwrite: bool = False,
) -> Chroma:
    """
    Convenience function: Extracts a ZIP archive then runs ingest_directory().
    Useful for the API endpoint that accepts uploaded ZIP files.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        logger.info(f"Extracting ZIP: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        return ingest_directory(tmpdir, collection_name, overwrite)


def get_collection_stats(collection_name: str = "codebase") -> dict:
    """Return metadata about an existing ChromaDB collection."""
    persist_dir = str(Path(settings.chroma_persist_dir).resolve())
    embeddings = _get_embeddings()

    try:
        store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )
        count = store._collection.count()
        # Sample a few chunks to show file distribution
        sample = store.get(limit=100, include=["metadatas"])
        files = list({m.get("file_path", "unknown") for m in sample["metadatas"]})
        return {
            "collection": collection_name,
            "total_chunks": count,
            "sample_files": files[:10],
        }
    except Exception as e:
        return {"error": str(e)}


# ── CLI entrypoint ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest a codebase into ChromaDB")
    parser.add_argument("--dir", required=True, help="Path to the codebase directory")
    parser.add_argument("--collection", default="codebase", help="ChromaDB collection name")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing collection")
    args = parser.parse_args()

    result = ingest_directory(args.dir, args.collection, args.overwrite)
    stats = get_collection_stats(args.collection)
    print(f"\n📊 Collection Stats: {stats}")
