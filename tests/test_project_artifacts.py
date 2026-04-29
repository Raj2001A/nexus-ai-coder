from backend.project_artifacts import build_changed_files, capture_project_snapshot


def test_capture_project_snapshot_ignores_common_build_directories(tmp_path):
    project_root = tmp_path / "repo"
    project_root.mkdir()

    (project_root / "src").mkdir()
    (project_root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "node_modules").mkdir()
    (project_root / "node_modules" / "ignored.js").write_text("console.log('ignore')\n", encoding="utf-8")

    snapshot = capture_project_snapshot(project_root)

    assert "src/app.py" in snapshot
    assert "node_modules/ignored.js" not in snapshot


def test_build_changed_files_returns_diff_preview_for_text_changes():
    before = {
        "app.py": {
            "sha1": "before",
            "size_bytes": 12,
            "text": "print('old')\n",
        }
    }
    after = {
        "app.py": {
            "sha1": "after",
            "size_bytes": 14,
            "text": "print('new')\n",
        }
    }

    changed_files = build_changed_files(before, after)

    assert len(changed_files) == 1
    assert changed_files[0]["path"] == "app.py"
    assert changed_files[0]["status"] == "modified"
    assert "--- a/app.py" in changed_files[0]["diff_preview"]
    assert "+++ b/app.py" in changed_files[0]["diff_preview"]
