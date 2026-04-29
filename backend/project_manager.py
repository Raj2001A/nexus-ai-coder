"""
project_manager.py
------------------
Manage the single active project root used by ingestion, editing, and execution.

Phase 2 design:
    - one active codebase at a time
    - local directory ingestion points directly at the real project root
    - ZIP uploads are extracted into a managed projects directory
    - tools and runners operate only inside the active project root
"""

import json
import logging
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)


def _state_file() -> Path:
    path = Path(settings.active_project_state_file).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_managed_projects_dir() -> Path:
    path = Path(settings.managed_projects_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def infer_project_root(base_dir: str | Path) -> Path:
    """
    Infer the effective project root.

    If extraction produced a single wrapper directory, use that directory so
    file paths remain clean and match typical repository layouts.
    """
    root = Path(base_dir).resolve()
    children = list(root.iterdir())
    visible_children = [child for child in children if child.name not in {"__MACOSX"}]

    if len(visible_children) == 1 and visible_children[0].is_dir():
        return visible_children[0].resolve()

    return root


def set_active_project_root(project_root: str | Path, source: str = "directory") -> Path:
    return set_active_project(project_root, collection_name="codebase", source=source)


def set_active_project(
    project_root: str | Path,
    collection_name: str = "codebase",
    source: str = "directory",
) -> Path:
    root = Path(project_root).resolve()

    if not root.exists():
        raise FileNotFoundError(f"Project root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Project root is not a directory: {root}")

    state = {
        "active_project_dir": str(root),
        "active_collection": collection_name,
        "source": source,
    }
    _state_file().write_text(json.dumps(state, indent=2), encoding="utf-8")
    logger.info(f"[ProjectManager] Active project set to: {root}")
    return root


def get_active_project_root() -> Path | None:
    state_path = _state_file()
    if not state_path.exists():
        return None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("[ProjectManager] Active project state file is invalid JSON.")
        return None

    raw_path = state.get("active_project_dir")
    if not raw_path:
        return None

    root = Path(raw_path).resolve()
    if not root.exists() or not root.is_dir():
        logger.warning(f"[ProjectManager] Active project path is unavailable: {root}")
        return None

    return root


def require_active_project_root() -> Path:
    root = get_active_project_root()
    if root is None:
        raise RuntimeError(
            "No active project is configured. Ingest a local directory or upload a ZIP first."
        )
    return root


def get_active_collection_name(default: str | None = None) -> str | None:
    state_path = _state_file()
    if not state_path.exists():
        return default

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("[ProjectManager] Active project state file is invalid JSON.")
        return default

    return state.get("active_collection", default)


def require_active_collection_name() -> str:
    collection_name = get_active_collection_name()
    if not collection_name:
        raise RuntimeError(
            "No active collection is configured. Ingest a local directory or upload a ZIP first."
        )
    return collection_name


def get_active_project_metadata() -> dict:
    root = get_active_project_root()
    if root is None:
        return {
            "active_project_dir": None,
            "active_project_name": None,
            "active_project_source": None,
            "active_collection": None,
        }

    source = None
    collection_name = None
    state_path = _state_file()
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            source = state.get("source")
            collection_name = state.get("active_collection")
        except json.JSONDecodeError:
            source = None
            collection_name = None

    return {
        "active_project_dir": str(root),
        "active_project_name": root.name,
        "active_project_source": source,
        "active_collection": collection_name,
    }
