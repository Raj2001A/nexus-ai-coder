from backend.git_inspector import inspect_git_state
from backend.run_history import list_run_records, load_run_record, persist_run_record


def test_run_history_persists_and_lists_records():
    persisted = persist_run_record(
        {
            "task": "add tests",
            "review_passed": True,
            "iterations": 2,
            "trust_metrics": {"changed_files": 1, "verification_total": 2},
            "active_project_name": "repo",
        }
    )

    loaded = load_run_record(persisted["run_id"])
    listing = list_run_records(limit=5)

    assert loaded is not None
    assert loaded["task"] == "add tests"
    assert listing[0]["run_id"] == persisted["run_id"]


def test_inspect_git_state_gracefully_handles_non_git_project(tmp_path):
    project_root = tmp_path / "repo"
    project_root.mkdir()

    changed_files = [{"path": "app.py", "status": "modified", "language": "py", "size_bytes": 10, "diff_preview": "@@"}]
    enriched, summary = inspect_git_state(project_root, changed_files)

    assert enriched == changed_files
    assert summary["git_available"] is False
    assert summary["dirty_files"] == 0
