"""
git_inspector.py
----------------
Best-effort git-aware summaries for changed files and active project state.

The assistant can work on non-git projects, so every helper here degrades
gracefully when git metadata is unavailable.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _is_git_repo(project_root: Path) -> bool:
    try:
        result = _run_git(project_root, "rev-parse", "--is-inside-work-tree")
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False


def _parse_status_map(project_root: Path) -> dict[str, str]:
    result = _run_git(project_root, "status", "--porcelain=v1", "--untracked-files=all")
    if result.returncode != 0:
        return {}

    status_map: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:].strip().replace("\\", "/")
        status_map[path] = status
    return status_map


def _get_branch_name(project_root: Path) -> str | None:
    result = _run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _get_numstat(project_root: Path, relative_path: str) -> dict | None:
    result = _run_git(project_root, "diff", "--numstat", "--", relative_path)
    if result.returncode != 0:
        return None

    line = next((line for line in result.stdout.splitlines() if line.strip()), "")
    if not line:
        return None

    parts = line.split("\t")
    if len(parts) < 3:
        return None

    insertions, deletions = parts[0], parts[1]
    return {
        "insertions": None if insertions == "-" else int(insertions),
        "deletions": None if deletions == "-" else int(deletions),
    }


def get_git_patch(project_root: Path, paths: list[str] | None = None, max_chars: int = 50_000) -> dict:
    """
    Return a best-effort git diff patch for the current project state.

    This only works for git repositories and reflects the current working tree,
    not a historical run snapshot.
    """
    if not _is_git_repo(project_root):
        return {
            "git_available": False,
            "patch": "",
            "truncated": False,
            "paths": paths or [],
        }

    command = ["diff", "--no-ext-diff", "--", *(paths or [])]
    result = _run_git(project_root, *command)
    if result.returncode != 0:
        return {
            "git_available": True,
            "patch": "",
            "truncated": False,
            "paths": paths or [],
            "error": result.stderr.strip(),
        }

    patch = result.stdout
    truncated = False
    if len(patch) > max_chars:
        patch = patch[:max_chars] + "\n\n... [patch truncated]"
        truncated = True

    return {
        "git_available": True,
        "patch": patch,
        "truncated": truncated,
        "paths": paths or [],
    }


def inspect_git_state(project_root: Path, changed_files: list[dict]) -> tuple[list[dict], dict]:
    """
    Enrich changed files with git metadata and return a project-level summary.
    """
    if not _is_git_repo(project_root):
        return changed_files, {
            "git_available": False,
            "branch": None,
            "dirty_files": 0,
        }

    status_map = _parse_status_map(project_root)
    branch = _get_branch_name(project_root)
    enriched: list[dict] = []

    for file_info in changed_files:
        relative_path = file_info["path"]
        git_status = status_map.get(relative_path)
        diff_stats = _get_numstat(project_root, relative_path)
        updated = {
            **file_info,
            "git_tracked": git_status != "??" if git_status is not None else None,
            "git_status": git_status,
            "git_diff_summary": diff_stats,
        }
        enriched.append(updated)

    return enriched, {
        "git_available": True,
        "branch": branch,
        "dirty_files": len(status_map),
    }
