import os

import pytest

from backend import project_manager


os.environ["DEBUG"] = "true"
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("TAVILY_API_KEY", "")


@pytest.fixture(autouse=True)
def isolated_project_state(monkeypatch, tmp_path):
    managed_root = tmp_path / "managed_projects"
    state_file = managed_root / "active_project.json"
    run_history_dir = managed_root / "run_history"

    monkeypatch.setattr(project_manager.settings, "managed_projects_dir", str(managed_root))
    monkeypatch.setattr(project_manager.settings, "active_project_state_file", str(state_file))
    monkeypatch.setattr(project_manager.settings, "run_history_dir", str(run_history_dir))

    yield


@pytest.fixture
def active_project(tmp_path):
    project_root = tmp_path / "repo"
    project_root.mkdir()
    project_manager.set_active_project_root(project_root, source="test")
    return project_root
