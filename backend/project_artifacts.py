"""
project_artifacts.py
--------------------
Capture project snapshots and derive human-reviewable change artifacts.

This phase uses artifacts for UI trust features:
    - changed file listing
    - diff previews for modified text files
    - deterministic post-run change summaries
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path


MAX_TEXT_FILE_BYTES = 100_000
MAX_DIFF_LINES = 160
IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
}


def _should_ignore(path: Path, project_root: Path) -> bool:
    rel_parts = path.relative_to(project_root).parts
    return any(part in IGNORED_DIR_NAMES for part in rel_parts)


def _read_text_if_safe(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _language_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix.startswith("."):
        return suffix[1:]
    return ""


def capture_project_snapshot(project_root: Path) -> dict[str, dict]:
    """
    Capture file state for later diffing.

    The snapshot is intentionally limited to files that are small enough to
    safely render text diffs for in the UI.
    """
    snapshot: dict[str, dict] = {}
    root = project_root.resolve()

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_ignore(path, root):
            continue

        rel_path = path.relative_to(root).as_posix()
        content_bytes = path.read_bytes()
        text_content = _read_text_if_safe(path)
        snapshot[rel_path] = {
            "sha1": hashlib.sha1(content_bytes).hexdigest(),
            "size_bytes": len(content_bytes),
            "text": text_content,
        }

    return snapshot


def _build_diff_preview(
    path: str,
    before_text: str | None,
    after_text: str | None,
) -> str | None:
    if before_text is None and after_text is None:
        return None

    before_lines = [] if before_text is None else before_text.splitlines()
    after_lines = [] if after_text is None else after_text.splitlines()

    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )

    if not diff_lines:
        return None

    if len(diff_lines) > MAX_DIFF_LINES:
        diff_lines = diff_lines[:MAX_DIFF_LINES]
        diff_lines.append("... diff truncated ...")

    return "\n".join(diff_lines)


def build_changed_files(before: dict[str, dict], after: dict[str, dict]) -> list[dict]:
    """Build structured changed-file artifacts from two snapshots."""
    changed_files: list[dict] = []

    for path in sorted(set(before) | set(after)):
        before_entry = before.get(path)
        after_entry = after.get(path)

        if before_entry is None:
            status = "created"
        elif after_entry is None:
            status = "deleted"
        elif before_entry["sha1"] != after_entry["sha1"]:
            status = "modified"
        else:
            continue

        reference_entry = after_entry or before_entry
        changed_files.append(
            {
                "path": path,
                "status": status,
                "language": _language_from_path(path),
                "size_bytes": reference_entry["size_bytes"],
                "diff_preview": _build_diff_preview(
                    path,
                    None if before_entry is None else before_entry["text"],
                    None if after_entry is None else after_entry["text"],
                ),
            }
        )

    return changed_files
