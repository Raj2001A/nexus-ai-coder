"""
FastAPI backend for the AI coding assistant.

Phase 2 behavior:
    - one active project root at a time
    - local directory ingestion points directly at the real project
    - ZIP uploads are extracted into managed storage and then become the active project
    - chat execution requires an active project
"""

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import settings
from backend.git_inspector import get_git_patch, inspect_git_state
from backend.graph.state import AgentState
from backend.graph.workflow import workflow
from backend.project_artifacts import build_changed_files, capture_project_snapshot
from backend.project_manager import (
    get_active_project_metadata,
    get_active_collection_name,
    get_active_project_root,
    get_managed_projects_dir,
    infer_project_root,
    require_active_collection_name,
    require_active_project_root,
    set_active_project,
)
from backend.rag.ingestion import get_collection_stats, ingest_directory
from backend.rag.retriever import CodebaseRetriever, format_results_for_agent, hybrid_search, serialize_results
from backend.run_analytics import summarize_run_history
from backend.run_artifacts import get_verification_runs, reset_verification_runs
from backend.run_history import list_run_records, load_run_record, persist_run_record

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Multi-Agent Coding Assistant",
    description="Production-grade multi-agent system with RAG, tool-calling, and review loops",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


class ChatRequest(BaseModel):
    task: str
    collection: str = "codebase"


class ChatResponse(BaseModel):
    run_id: str | None = None
    final_answer: str
    iterations: int
    review_passed: bool
    retrieved_context: list[dict] = Field(default_factory=list)
    changed_files: list[dict] = Field(default_factory=list)
    verification_runs: list[dict] = Field(default_factory=list)
    trust_metrics: dict = Field(default_factory=dict)


class IngestRequest(BaseModel):
    directory: str
    collection: str = "codebase"
    overwrite: bool = False


class SearchRequest(BaseModel):
    query: str
    collection: str = "codebase"
    k: int = 5


def _build_trust_metrics(
    retrieved_context: list[dict],
    changed_files: list[dict],
    verification_runs: list[dict],
    review_passed: bool,
    iterations: int,
    git_summary: dict,
) -> dict:
    changed_status_counts = {"created": 0, "modified": 0, "deleted": 0}
    for item in changed_files:
        status = item.get("status")
        if status in changed_status_counts:
            changed_status_counts[status] += 1

    verification_passed = sum(1 for item in verification_runs if item.get("success"))
    verification_failed = len(verification_runs) - verification_passed

    by_kind: dict[str, int] = {}
    by_classification: dict[str, int] = {}
    for item in verification_runs:
        kind = item.get("kind") or "unknown"
        classification = item.get("classification") or "unknown"
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_classification[classification] = by_classification.get(classification, 0) + 1

    return {
        "retrieved_chunks": len(retrieved_context),
        "changed_files": len(changed_files),
        "changed_status_counts": changed_status_counts,
        "verification_total": len(verification_runs),
        "verification_passed": verification_passed,
        "verification_failed": verification_failed,
        "verification_by_kind": by_kind,
        "verification_by_classification": by_classification,
        "review_passed": review_passed,
        "iterations": iterations,
        "git_available": git_summary.get("git_available", False),
        "git_branch": git_summary.get("branch"),
        "git_dirty_files": git_summary.get("dirty_files", 0),
    }


def _persist_completed_run(
    *,
    task: str,
    final_answer: str,
    iterations: int,
    review_passed: bool,
    retrieved_context: list[dict],
    changed_files: list[dict],
    verification_runs: list[dict],
    trust_metrics: dict,
) -> dict:
    active_metadata = get_active_project_metadata()
    return persist_run_record(
        {
            "task": task,
            "final_answer": final_answer,
            "iterations": iterations,
            "review_passed": review_passed,
            "retrieved_context": retrieved_context,
            "changed_files": changed_files,
            "verification_runs": verification_runs,
            "trust_metrics": trust_metrics,
            **active_metadata,
        }
    )


def _build_collection_response(collection_name: str = "codebase") -> dict:
    response = get_collection_stats(collection_name)
    response.update(get_active_project_metadata())
    return response


def _safe_extract_zip(zip_path: str, destination: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        destination_resolved = destination.resolve()
        for member in archive.infolist():
            target_path = (destination / member.filename).resolve()
            try:
                target_path.relative_to(destination_resolved)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="ZIP archive contains unsafe paths") from exc

        archive.extractall(destination)


def _prepare_uploaded_project(zip_path: str) -> Path:
    managed_root = get_managed_projects_dir()
    extraction_root = managed_root / "uploaded_active_project"

    if extraction_root.exists():
        shutil.rmtree(extraction_root)
    extraction_root.mkdir(parents=True, exist_ok=True)

    _safe_extract_zip(zip_path, extraction_root)
    return infer_project_root(extraction_root)


def _ensure_active_project_for_execution() -> Path:
    try:
        return require_active_project_root()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_effective_overwrite(
    target_project_root: Path,
    collection_name: str,
    requested_overwrite: bool,
) -> bool:
    """
    Keep the active project root and indexed collection in sync.

    If the caller switches either the project root or collection, force a fresh
    ingestion so retrieval cannot point at stale chunks from a previous project.
    """
    if requested_overwrite:
        return True

    active_root = get_active_project_root()
    active_collection = get_active_collection_name()

    if active_root is None or active_collection is None:
        return False

    if active_root != target_project_root.resolve() or active_collection != collection_name:
        logger.info(
            "[API] Switching active project or collection; forcing re-ingestion to keep index and project in sync."
        )
        return True

    return False


@app.get("/")
async def root():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "AI Coding Assistant API is running. Frontend not found."}


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.post("/ingest/directory")
async def ingest_from_directory(request: IngestRequest):
    directory = Path(request.directory).resolve()

    if not directory.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    if not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {directory}")

    try:
        effective_overwrite = _resolve_effective_overwrite(directory, request.collection, request.overwrite)
        ingest_directory(str(directory), request.collection, effective_overwrite)
        set_active_project(directory, collection_name=request.collection, source="directory")
        return {"status": "success", "stats": _build_collection_response(request.collection)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/ingest/upload")
async def ingest_from_upload(
    file: UploadFile = File(...),
    collection: str = Form(default="codebase"),
    overwrite: bool = Form(default=False),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, file.filename)

    try:
        with open(zip_path, "wb") as handle:
            handle.write(await file.read())

        project_root = _prepare_uploaded_project(zip_path)
        effective_overwrite = _resolve_effective_overwrite(project_root, collection, overwrite)
        ingest_directory(str(project_root), collection, effective_overwrite)
        set_active_project(project_root, collection_name=collection, source="upload")
        return {"status": "success", "stats": _build_collection_response(collection)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/collections")
async def list_collections():
    return _build_collection_response()


@app.get("/runs")
async def list_runs(limit: int = 20):
    return {"runs": list_run_records(limit=max(1, min(limit, 100)))}


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    record = load_run_record(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return record


@app.get("/analytics/summary")
async def analytics_summary(limit: int = 50, scope: str = "active"):
    active_metadata = get_active_project_metadata() if scope == "active" else {}
    summary = summarize_run_history(
        limit=max(1, min(limit, 200)),
        active_project_name=active_metadata.get("active_project_name"),
        active_project_dir=active_metadata.get("active_project_dir"),
    )
    return summary


@app.get("/review/git-patch")
async def review_git_patch(path: str | None = None):
    project_root = _ensure_active_project_for_execution()
    paths = [path] if path else None
    return get_git_patch(project_root, paths=paths)


@app.post("/search")
async def search_codebase(request: SearchRequest):
    results = hybrid_search(request.query, request.collection, request.k)
    formatted = format_results_for_agent(results)
    return {
        "query": request.query,
        "num_results": len(results),
        "results": formatted,
        "structured_results": serialize_results(results),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    project_root = _ensure_active_project_for_execution()
    active_collection = require_active_collection_name()
    logger.info(f"[API] Chat request: '{request.task[:80]}...'")
    before_snapshot = capture_project_snapshot(project_root)
    reset_verification_runs()

    initial_state: AgentState = {
        "task": request.task,
        "collection_name": active_collection,
        "codebase_context": "",
        "retrieved_context_items": [],
        "plan": "",
        "code_output": "",
        "review_result": "",
        "review_passed": False,
        "iteration_count": 0,
        "max_iterations": settings.max_review_iterations,
        "final_answer": "",
        "error": "",
        "messages": [],
    }

    try:
        result = workflow.invoke(initial_state)
        changed_files = build_changed_files(before_snapshot, capture_project_snapshot(project_root))
        changed_files, git_summary = inspect_git_state(project_root, changed_files)
        verification_runs = get_verification_runs()
        retrieved_context = result.get("retrieved_context_items", [])
        trust_metrics = _build_trust_metrics(
            retrieved_context,
            changed_files,
            verification_runs,
            result.get("review_passed", False),
            result.get("iteration_count", 0),
            git_summary,
        )
        persisted = _persist_completed_run(
            task=request.task,
            final_answer=result.get("final_answer", "No output generated."),
            iterations=result.get("iteration_count", 0),
            review_passed=result.get("review_passed", False),
            retrieved_context=retrieved_context,
            changed_files=changed_files,
            verification_runs=verification_runs,
            trust_metrics=trust_metrics,
        )
        return ChatResponse(
            run_id=persisted["run_id"],
            final_answer=result.get("final_answer", "No output generated."),
            iterations=result.get("iteration_count", 0),
            review_passed=result.get("review_passed", False),
            retrieved_context=retrieved_context,
            changed_files=changed_files,
            verification_runs=verification_runs,
            trust_metrics=trust_metrics,
        )
    except Exception as exc:
        logger.error(f"[API] Workflow error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    logger.info("[WS] Client connected")

    try:
        data = await ws.receive_json()
        task = data.get("task", "")

        if not task:
            await ws.send_json({"type": "error", "message": "No task provided."})
            await ws.close()
            return

        project_root = get_active_project_root()
        if project_root is None:
            await ws.send_json({
                "type": "error",
                "message": "No active project is configured. Ingest a directory or upload a ZIP first.",
            })
            await ws.close()
            return

        logger.info(f"[WS] Task received: '{task[:80]}...'")
        active_collection = require_active_collection_name()
        before_snapshot = capture_project_snapshot(project_root)
        reset_verification_runs()

        await ws.send_json({"type": "status", "agent": "rag", "state": "running"})
        try:
            retriever = CodebaseRetriever(active_collection)
            rag_docs = retriever.get_relevant_documents(task)
            context = format_results_for_agent(rag_docs)
            rag_items = serialize_results(rag_docs)
        except Exception:
            context = "No codebase ingested. Working from scratch."
            rag_items = []
        await ws.send_json({
            "type": "result",
            "agent": "rag",
            "data": f"Retrieved {len(rag_items)} relevant chunk(s)",
            "items": rag_items,
        })

        await ws.send_json({"type": "status", "agent": "planner", "state": "running"})
        from backend.agents.planner import run_planner

        plan = run_planner(task, context)
        await ws.send_json({"type": "result", "agent": "planner", "data": plan})

        code_output = ""
        review_result = ""
        review_passed = False
        iteration = 0

        while iteration < settings.max_review_iterations:
            iteration += 1

            await ws.send_json({
                "type": "status",
                "agent": "executor",
                "state": "running",
                "iteration": iteration,
            })

            exec_plan = plan
            if iteration > 1 and review_result:
                exec_plan = (
                    f"{plan}\n\n## REVIEWER FEEDBACK (Iteration {iteration - 1})\n"
                    f"Fix these issues:\n{review_result}"
                )

            from backend.agents.executor import run_executor

            code_output = run_executor(exec_plan, task)
            await ws.send_json({"type": "result", "agent": "executor", "data": code_output})

            await ws.send_json({
                "type": "status",
                "agent": "reviewer",
                "state": "running",
                "iteration": iteration,
            })
            from backend.agents.reviewer import run_reviewer

            review = run_reviewer(task, plan, code_output)
            review_passed = review["passed"]
            review_result = review["feedback"]

            await ws.send_json({
                "type": "result",
                "agent": "reviewer",
                "data": review_result,
                "passed": review_passed,
            })

            if review_passed:
                break

        final_answer = (
            "# AI Coding Assistant - Results\n\n"
            f"## Task\n{task}\n\n"
            f"## Plan\n{plan}\n\n"
            f"## Implementation\n{code_output}\n\n"
            f"## Review ({'APPROVED' if review_passed else 'MAX RETRIES'})\n"
            f"{review_result}\n\n"
            f"---\nCompleted in {iteration} iteration(s)"
        )
        changed_files = build_changed_files(before_snapshot, capture_project_snapshot(project_root))
        changed_files, git_summary = inspect_git_state(project_root, changed_files)
        verification_runs = get_verification_runs()
        trust_metrics = _build_trust_metrics(
            rag_items,
            changed_files,
            verification_runs,
            review_passed,
            iteration,
            git_summary,
        )
        persisted = _persist_completed_run(
            task=task,
            final_answer=final_answer,
            iterations=iteration,
            review_passed=review_passed,
            retrieved_context=rag_items,
            changed_files=changed_files,
            verification_runs=verification_runs,
            trust_metrics=trust_metrics,
        )

        await ws.send_json({
            "type": "complete",
            "run_id": persisted["run_id"],
            "final_answer": final_answer,
            "iterations": iteration,
            "passed": review_passed,
            "retrieved_context": rag_items,
            "changed_files": changed_files,
            "verification_runs": verification_runs,
            "trust_metrics": trust_metrics,
        })
    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")
    except Exception as exc:
        logger.error(f"[WS] Error: {exc}")
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
