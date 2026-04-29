from backend import project_manager


def test_infer_project_root_prefers_single_wrapped_directory(tmp_path):
    wrapped = tmp_path / "archive_root"
    wrapped.mkdir()
    repo = wrapped / "sample-repo"
    repo.mkdir()

    assert project_manager.infer_project_root(wrapped) == repo.resolve()


def test_set_and_get_active_project_root(tmp_path):
    managed_root = tmp_path / "managed"
    project_manager.settings.managed_projects_dir = str(managed_root)
    project_manager.settings.active_project_state_file = str(managed_root / "active_project.json")

    repo = tmp_path / "repo"
    repo.mkdir()

    project_manager.set_active_project_root(repo, source="test")

    assert project_manager.get_active_project_root() == repo.resolve()
    metadata = project_manager.get_active_project_metadata()
    assert metadata["active_project_name"] == "repo"
    assert metadata["active_project_source"] == "test"
    assert metadata["active_collection"] == "codebase"


def test_set_active_project_tracks_collection(tmp_path):
    managed_root = tmp_path / "managed"
    project_manager.settings.managed_projects_dir = str(managed_root)
    project_manager.settings.active_project_state_file = str(managed_root / "active_project.json")

    repo = tmp_path / "repo"
    repo.mkdir()

    project_manager.set_active_project(repo, collection_name="frontend_repo", source="upload")

    assert project_manager.get_active_collection_name() == "frontend_repo"
