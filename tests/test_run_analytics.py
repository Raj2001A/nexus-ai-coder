from backend.run_analytics import summarize_run_history


def test_summarize_run_history_builds_insights(monkeypatch):
    monkeypatch.setattr(
        "backend.run_analytics.list_full_run_records",
        lambda limit=50: [
            {
                "active_project_name": "ai-coding-assistant",
                "active_project_dir": "repo",
                "review_passed": False,
                "iterations": 3,
                "changed_files": [{"path": "backend/api/main.py"}],
                "verification_runs": [
                    {"success": False, "classification": "python_test"},
                    {"success": True, "classification": "python_test"},
                ],
            },
            {
                "active_project_name": "ai-coding-assistant",
                "active_project_dir": "repo",
                "review_passed": True,
                "iterations": 2,
                "changed_files": [{"path": "backend/api/main.py"}],
                "verification_runs": [
                    {"success": False, "classification": "node_verification_script"},
                ],
            },
        ],
    )

    summary = summarize_run_history(
        limit=20,
        active_project_name="ai-coding-assistant",
        active_project_dir="repo",
    )

    assert summary["summary"]["total_runs"] == 2
    assert summary["failed_verification_classes"][0]["classification"] == "python_test"
    assert summary["top_changed_paths"][0]["path"] == "backend/api/main.py"
    assert summary["improvement_insights"]
