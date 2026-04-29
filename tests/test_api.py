from io import BytesIO
import zipfile

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from backend.api.main import app
from backend.project_manager import get_active_project_root


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "1.0.0"}


def test_collections_endpoint(monkeypatch, active_project):
    def fake_stats(collection_name="codebase"):
        return {
            "collection": collection_name,
            "total_chunks": 12,
            "sample_files": ["app.py", "utils.py"],
        }

    monkeypatch.setattr("backend.api.main.get_collection_stats", fake_stats)

    response = client.get("/collections")

    assert response.status_code == 200
    body = response.json()
    assert body["total_chunks"] == 12
    assert body["active_project_dir"] == str(active_project.resolve())
    assert body["active_project_source"] == "test"


def test_runs_endpoints(monkeypatch):
    monkeypatch.setattr(
        "backend.api.main.list_run_records",
        lambda limit=20: [{"run_id": "run-1", "task": "task", "review_passed": True}],
    )
    monkeypatch.setattr(
        "backend.api.main.load_run_record",
        lambda run_id: {"run_id": run_id, "task": "task", "verification_runs": []},
    )

    list_response = client.get("/runs")
    detail_response = client.get("/runs/run-1")

    assert list_response.status_code == 200
    assert list_response.json()["runs"][0]["run_id"] == "run-1"
    assert detail_response.status_code == 200
    assert detail_response.json()["run_id"] == "run-1"


def test_analytics_summary_endpoint(monkeypatch):
    monkeypatch.setattr(
        "backend.api.main.summarize_run_history",
        lambda **kwargs: {
            "summary": {"total_runs": 3, "pass_rate": 0.67},
            "improvement_insights": [{"title": "Insight"}],
        },
    )

    response = client.get("/analytics/summary?limit=10&scope=active")

    assert response.status_code == 200
    assert response.json()["summary"]["total_runs"] == 3


def test_review_git_patch_endpoint(monkeypatch, active_project):
    monkeypatch.setattr(
        "backend.api.main.get_git_patch",
        lambda project_root, paths=None: {"git_available": True, "patch": "diff --git a/app.py b/app.py", "truncated": False, "paths": paths or []},
    )

    response = client.get("/review/git-patch?path=app.py")

    assert response.status_code == 200
    assert response.json()["git_available"] is True
    assert response.json()["paths"] == ["app.py"]


def test_search_endpoint(monkeypatch):
    def fake_hybrid_search(query, collection_name="codebase", k=5):
        return ["result-a", "result-b"]

    def fake_formatter(results):
        assert results == ["result-a", "result-b"]
        return "formatted results"

    def fake_serializer(results):
        assert results == ["result-a", "result-b"]
        return [{"file_path": "app.py", "preview": "def main"}]

    monkeypatch.setattr("backend.api.main.hybrid_search", fake_hybrid_search)
    monkeypatch.setattr("backend.api.main.format_results_for_agent", fake_formatter)
    monkeypatch.setattr("backend.api.main.serialize_results", fake_serializer)

    response = client.post(
        "/search",
        json={"query": "find websocket", "collection": "codebase", "k": 2},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "find websocket"
    assert data["num_results"] == 2
    assert data["results"] == "formatted results"
    assert data["structured_results"] == [{"file_path": "app.py", "preview": "def main"}]


def test_chat_endpoint(monkeypatch, active_project):
    class FakeWorkflow:
        def invoke(self, initial_state):
            assert initial_state["task"] == "add health checks"
            assert initial_state["collection_name"] == "codebase"
            assert initial_state["retrieved_context_items"] == []
            return {
                "final_answer": "done",
                "iteration_count": 2,
                "review_passed": True,
                "retrieved_context_items": [{"file_path": "app.py", "preview": "def main"}],
            }

    monkeypatch.setattr("backend.api.main.workflow", FakeWorkflow())
    monkeypatch.setattr("backend.api.main.capture_project_snapshot", lambda project_root: {"snapshot": str(project_root)})
    monkeypatch.setattr(
        "backend.api.main.build_changed_files",
        lambda before, after: [{"path": "app.py", "status": "modified", "language": "py", "size_bytes": 10, "diff_preview": "@@"}],
    )
    monkeypatch.setattr(
        "backend.api.main.inspect_git_state",
        lambda project_root, changed_files: (changed_files, {"git_available": True, "branch": "main", "dirty_files": 1}),
    )
    monkeypatch.setattr("backend.api.main.reset_verification_runs", lambda: None)
    monkeypatch.setattr(
        "backend.api.main.get_verification_runs",
        lambda: [{"kind": "command", "target": "python -m pytest", "classification": "python_test", "success": True, "exit_code": 0, "stdout": "", "stderr": ""}],
    )
    monkeypatch.setattr(
        "backend.api.main.persist_run_record",
        lambda record: {**record, "run_id": "run-123"},
    )

    response = client.post(
        "/chat",
        json={"task": "add health checks", "collection": "codebase"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run-123",
        "final_answer": "done",
        "iterations": 2,
        "review_passed": True,
        "retrieved_context": [{"file_path": "app.py", "preview": "def main"}],
        "changed_files": [{"path": "app.py", "status": "modified", "language": "py", "size_bytes": 10, "diff_preview": "@@"}],
        "verification_runs": [{"kind": "command", "target": "python -m pytest", "classification": "python_test", "success": True, "exit_code": 0, "stdout": "", "stderr": ""}],
        "trust_metrics": {
            "retrieved_chunks": 1,
            "changed_files": 1,
            "changed_status_counts": {"created": 0, "modified": 1, "deleted": 0},
            "verification_total": 1,
            "verification_passed": 1,
            "verification_failed": 0,
            "verification_by_kind": {"command": 1},
            "verification_by_classification": {"python_test": 1},
            "review_passed": True,
            "iterations": 2,
            "git_available": True,
            "git_branch": "main",
            "git_dirty_files": 1,
        },
    }


def test_chat_requires_active_project(monkeypatch):
    monkeypatch.setattr(
        "backend.api.main.require_active_project_root",
        lambda: (_ for _ in ()).throw(RuntimeError("No active project is configured.")),
    )

    response = client.post(
        "/chat",
        json={"task": "add health checks", "collection": "codebase"},
    )

    assert response.status_code == 400
    assert "No active project" in response.json()["detail"]


def test_ingest_directory_sets_active_project(monkeypatch, tmp_path):
    target_project = tmp_path / "demo_repo"
    target_project.mkdir()

    monkeypatch.setattr("backend.api.main.ingest_directory", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "backend.api.main.get_collection_stats",
        lambda collection_name="codebase": {"collection": collection_name, "total_chunks": 4, "sample_files": []},
    )

    response = client.post(
        "/ingest/directory",
        json={"directory": str(target_project), "collection": "codebase", "overwrite": False},
    )

    assert response.status_code == 200
    assert get_active_project_root() == target_project.resolve()
    assert response.json()["stats"]["active_project_dir"] == str(target_project.resolve())


def test_ingest_directory_forces_overwrite_when_switching_projects(monkeypatch, tmp_path):
    first_project = tmp_path / "repo_a"
    second_project = tmp_path / "repo_b"
    first_project.mkdir()
    second_project.mkdir()

    overwrite_values = []

    def fake_ingest(directory, collection, overwrite):
        overwrite_values.append(overwrite)

    monkeypatch.setattr("backend.api.main.ingest_directory", fake_ingest)
    monkeypatch.setattr(
        "backend.api.main.get_collection_stats",
        lambda collection_name="codebase": {"collection": collection_name, "total_chunks": 1, "sample_files": []},
    )

    first_response = client.post(
        "/ingest/directory",
        json={"directory": str(first_project), "collection": "codebase", "overwrite": False},
    )
    second_response = client.post(
        "/ingest/directory",
        json={"directory": str(second_project), "collection": "codebase", "overwrite": False},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert overwrite_values == [False, True]


def test_ingest_upload_sets_active_project(monkeypatch):
    monkeypatch.setattr("backend.api.main.ingest_directory", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "backend.api.main.get_collection_stats",
        lambda collection_name="codebase": {"collection": collection_name, "total_chunks": 3, "sample_files": []},
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sample-repo/app.py", "print('ok')\n")
    buffer.seek(0)

    response = client.post(
        "/ingest/upload",
        files={"file": ("repo.zip", buffer.getvalue(), "application/zip")},
        data={"collection": "codebase", "overwrite": "false"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["active_project_name"] == "sample-repo"
    assert body["stats"]["active_project_source"] == "upload"


def test_ingest_upload_rejects_unsafe_zip(monkeypatch):
    monkeypatch.setattr("backend.api.main.ingest_directory", lambda *args, **kwargs: None)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.py", "print('bad')\n")
    buffer.seek(0)

    response = client.post(
        "/ingest/upload",
        files={"file": ("repo.zip", buffer.getvalue(), "application/zip")},
        data={"collection": "codebase", "overwrite": "false"},
    )

    assert response.status_code == 400
    assert "unsafe paths" in response.json()["detail"]


def test_websocket_chat_streams_retrieval_items_and_changed_files(monkeypatch, active_project):
    class FakeRetriever:
        def __init__(self, collection_name):
            assert collection_name == "codebase"

        def get_relevant_documents(self, query):
            assert query == "inspect repo"
            return [
                Document(
                    page_content="def healthcheck():\n    return 'ok'\n",
                    metadata={"file_path": "app.py", "file_extension": ".py", "chunk_index": 1, "total_chunks": 2},
                )
            ]

    snapshots = iter([
        {"app.py": {"sha1": "before", "size_bytes": 10, "text": "before"}},
        {"app.py": {"sha1": "after", "size_bytes": 12, "text": "after"}},
    ])

    monkeypatch.setattr("backend.api.main.CodebaseRetriever", FakeRetriever)
    monkeypatch.setattr("backend.api.main.capture_project_snapshot", lambda project_root: next(snapshots))
    monkeypatch.setattr(
        "backend.api.main.build_changed_files",
        lambda before, after: [{"path": "app.py", "status": "modified", "language": "py", "size_bytes": 12, "diff_preview": "@@"}],
    )
    monkeypatch.setattr(
        "backend.api.main.inspect_git_state",
        lambda project_root, changed_files: (changed_files, {"git_available": True, "branch": "main", "dirty_files": 1}),
    )
    monkeypatch.setattr("backend.api.main.reset_verification_runs", lambda: None)
    monkeypatch.setattr(
        "backend.api.main.get_verification_runs",
        lambda: [{"kind": "file", "target": "app.py", "classification": "python_file", "success": True, "exit_code": 0, "stdout": "ok", "stderr": ""}],
    )
    monkeypatch.setattr(
        "backend.api.main.persist_run_record",
        lambda record: {**record, "run_id": "run-456"},
    )
    monkeypatch.setattr("backend.agents.planner.run_planner", lambda task, context: "plan")
    monkeypatch.setattr("backend.agents.executor.run_executor", lambda plan, task: "implemented")
    monkeypatch.setattr("backend.agents.reviewer.run_reviewer", lambda task, plan, code: {"passed": True, "feedback": "looks good"})

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"task": "inspect repo"})
        messages = []
        while True:
            message = websocket.receive_json()
            messages.append(message)
            if message["type"] == "complete":
                break

    rag_result = next(msg for msg in messages if msg["type"] == "result" and msg["agent"] == "rag")
    complete = next(msg for msg in messages if msg["type"] == "complete")

    assert rag_result["items"][0]["file_path"] == "app.py"
    assert rag_result["items"][0]["language"] == "py"
    assert complete["run_id"] == "run-456"
    assert complete["changed_files"] == [
        {"path": "app.py", "status": "modified", "language": "py", "size_bytes": 12, "diff_preview": "@@"}
    ]
    assert complete["verification_runs"] == [
        {"kind": "file", "target": "app.py", "classification": "python_file", "success": True, "exit_code": 0, "stdout": "ok", "stderr": ""}
    ]
    assert complete["trust_metrics"]["retrieved_chunks"] == 1
    assert complete["trust_metrics"]["verification_by_classification"] == {"python_file": 1}
