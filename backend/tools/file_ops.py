"""
file_ops.py
-----------
Secure file operations tool for agents.

All operations are confined to the active project root via path validation.
This prevents the agent from modifying files outside the target repository.
"""

import os
import tempfile
import logging
import difflib
from pathlib import Path

from langchain_core.tools import tool

from backend.project_manager import require_active_project_root

logger = logging.getLogger(__name__)

MAX_READ_SIZE = 100_000
MAX_DISPLAY_LINES = 200
MAX_DIFF_PREVIEW_LINES = 120


def _get_project_root() -> Path:
    """Return the currently active project root."""
    return require_active_project_root()


def _validate_path(target: str) -> Path:
    """
    Validate that a path is inside the active project root.
    Prevents path traversal attacks (../../etc/passwd).
    """
    project_root = _get_project_root()
    resolved = (project_root / target).resolve()

    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise PermissionError(
            f"ACCESS DENIED: Path '{target}' resolves outside the active project. "
            f"All file operations must stay within '{project_root}'"
        ) from exc

    return resolved


def read_file_content(file_path: str) -> dict:
    """Read a file from the active project root with line numbers."""
    resolved = _validate_path(file_path)

    if not resolved.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    if not resolved.is_file():
        return {"success": False, "error": f"Not a file: {file_path}"}

    size = resolved.stat().st_size
    if size > MAX_READ_SIZE:
        return {
            "success": False,
            "error": f"File too large ({size:,} bytes). Max is {MAX_READ_SIZE:,} bytes.",
        }

    try:
        content = resolved.read_text(encoding="utf-8")
        lines = content.splitlines()
        numbered_lines = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]

        if len(numbered_lines) > MAX_DISPLAY_LINES:
            display = "\n".join(numbered_lines[:MAX_DISPLAY_LINES])
            display += f"\n\n... [{len(lines) - MAX_DISPLAY_LINES} more lines not shown]"
        else:
            display = "\n".join(numbered_lines)

        return {
            "success": True,
            "content": display,
            "raw_content": content,
            "line_count": len(lines),
            "file_path": str(resolved.relative_to(_get_project_root())),
        }
    except UnicodeDecodeError:
        return {"success": False, "error": f"Cannot read binary file: {file_path}"}


def _read_existing_text(resolved: Path) -> str | None:
    if not resolved.exists() or not resolved.is_file():
        return None
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _atomic_write(resolved: Path, content: str) -> None:
    resolved.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(resolved.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, str(resolved))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _build_diff_preview(file_path: str, before_text: str | None, after_text: str | None) -> str | None:
    if before_text == after_text:
        return None

    before_lines = [] if before_text is None else before_text.splitlines()
    after_lines = [] if after_text is None else after_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )

    if not diff_lines:
        return None

    if len(diff_lines) > MAX_DIFF_PREVIEW_LINES:
        diff_lines = diff_lines[:MAX_DIFF_PREVIEW_LINES]
        diff_lines.append("... diff truncated ...")

    return "\n".join(diff_lines)


def write_file_content(file_path: str, content: str) -> dict:
    """Write content to a file in the active project root using atomic writes."""
    resolved = _validate_path(file_path)

    try:
        before_text = _read_existing_text(resolved)
        _atomic_write(resolved, content)

        line_count = len(content.splitlines())
        logger.info(f"[FileOps] Wrote {line_count} lines to {file_path}")

        return {
            "success": True,
            "file_path": str(resolved.relative_to(_get_project_root())),
            "line_count": line_count,
            "size_bytes": resolved.stat().st_size,
            "operation": "rewrite" if before_text is not None else "create",
            "diff_preview": _build_diff_preview(file_path, before_text, content),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def replace_file_content(
    file_path: str,
    old_text: str,
    new_text: str,
    expected_occurrences: int = 1,
) -> dict:
    """
    Replace an exact text block inside an existing file.

    This is safer than a full rewrite when modifying an existing file because
    it fails if the expected snippet is missing or appears an unexpected number
    of times.
    """
    resolved = _validate_path(file_path)

    if expected_occurrences < 1:
        return {"success": False, "error": "expected_occurrences must be at least 1."}

    if not resolved.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    if not resolved.is_file():
        return {"success": False, "error": f"Not a file: {file_path}"}

    try:
        original = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"success": False, "error": f"Cannot edit binary file: {file_path}"}

    occurrences = original.count(old_text)
    if occurrences == 0:
        return {"success": False, "error": "Target text not found in file."}
    if occurrences != expected_occurrences:
        return {
            "success": False,
            "error": (
                f"Expected {expected_occurrences} occurrence(s) of target text, "
                f"but found {occurrences}."
            ),
        }

    updated = original.replace(old_text, new_text, expected_occurrences)
    _atomic_write(resolved, updated)
    return {
        "success": True,
        "file_path": str(resolved.relative_to(_get_project_root())),
        "occurrences_replaced": expected_occurrences,
        "line_count": len(updated.splitlines()),
        "size_bytes": resolved.stat().st_size,
        "operation": "patch_replace",
        "diff_preview": _build_diff_preview(file_path, original, updated),
    }


def replace_file_lines(file_path: str, start_line: int, end_line: int, new_text: str) -> dict:
    """Replace an inclusive line range inside an existing text file."""
    resolved = _validate_path(file_path)

    if start_line < 1 or end_line < start_line:
        return {"success": False, "error": "Invalid line range."}

    if not resolved.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    if not resolved.is_file():
        return {"success": False, "error": f"Not a file: {file_path}"}

    try:
        original = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"success": False, "error": f"Cannot edit binary file: {file_path}"}

    lines = original.splitlines()
    if end_line > len(lines):
        return {
            "success": False,
            "error": f"Line range {start_line}-{end_line} exceeds file length ({len(lines)} lines).",
        }

    replacement_lines = new_text.splitlines()
    updated_lines = lines[: start_line - 1] + replacement_lines + lines[end_line:]
    updated = "\n".join(updated_lines)
    if original.endswith("\n"):
        updated += "\n"

    _atomic_write(resolved, updated)
    return {
        "success": True,
        "file_path": str(resolved.relative_to(_get_project_root())),
        "line_range": [start_line, end_line],
        "line_count": len(updated.splitlines()),
        "size_bytes": resolved.stat().st_size,
        "operation": "patch_lines",
        "diff_preview": _build_diff_preview(file_path, original, updated),
    }


def list_project_files(subdirectory: str = ".") -> dict:
    """List files in the active project root or a subdirectory."""
    resolved = _validate_path(subdirectory)

    if not resolved.exists():
        return {"success": False, "error": f"Directory not found: {subdirectory}"}

    if not resolved.is_dir():
        return {"success": False, "error": f"Not a directory: {subdirectory}"}

    project_root = _get_project_root()
    files = []
    dirs = []

    try:
        for item in sorted(resolved.rglob("*")):
            rel = str(item.relative_to(project_root))
            if item.is_file():
                files.append({
                    "path": rel,
                    "size": item.stat().st_size,
                    "extension": item.suffix,
                })
            elif item.is_dir():
                dirs.append(rel)

        return {
            "success": True,
            "directory": str(resolved.relative_to(project_root)),
            "total_files": len(files),
            "total_dirs": len(dirs),
            "files": files[:50],
            "directories": dirs[:20],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def search_in_files(search_term: str, file_extension: str = "") -> dict:
    """Search for a string across all files in the active project root."""
    project_root = _get_project_root()
    matches = []
    files_searched = 0

    for file_path in project_root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_extension and file_path.suffix != file_extension:
            continue
        if file_path.stat().st_size > MAX_READ_SIZE:
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
            files_searched += 1

            for line_num, line in enumerate(content.splitlines(), 1):
                if search_term.lower() in line.lower():
                    matches.append({
                        "file": str(file_path.relative_to(project_root)),
                        "line": line_num,
                        "content": line.strip()[:200],
                    })
                    if len(matches) >= 30:
                        return {
                            "success": True,
                            "matches": matches,
                            "files_searched": files_searched,
                            "truncated": True,
                        }
        except (UnicodeDecodeError, PermissionError):
            continue

    return {
        "success": True,
        "matches": matches,
        "files_searched": files_searched,
        "truncated": False,
    }


@tool
def read_code(file_path: str) -> str:
    """Read a file from the active project root with line numbers."""
    result = read_file_content(file_path)
    if result["success"]:
        return (
            f"FILE {result['file_path']} ({result['line_count']} lines)\n"
            f"{'-' * 50}\n"
            f"{result['content']}"
        )
    return f"ERROR {result['error']}"


@tool
def save_code(file_path: str, content: str) -> str:
    """Write a complete file in the active project root. Prefer patch tools for existing files."""
    result = write_file_content(file_path, content)
    if result["success"]:
        return (
            f"File saved via {result['operation']}: {result['file_path']} "
            f"({result['line_count']} lines, {result['size_bytes']} bytes)\n"
            f"{result.get('diff_preview') or 'No diff preview available.'}"
        )
    return f"ERROR {result['error']}"


@tool
def replace_code_block(file_path: str, old_text: str, new_text: str, expected_occurrences: int = 1) -> str:
    """Replace an exact code block inside an existing file."""
    result = replace_file_content(file_path, old_text, new_text, expected_occurrences)
    if result["success"]:
        return (
            f"Patched file via exact replacement: {result['file_path']} "
            f"({result['occurrences_replaced']} occurrence updated)\n"
            f"{result.get('diff_preview') or 'No diff preview available.'}"
        )
    return f"ERROR {result['error']}"


@tool
def replace_code_lines(file_path: str, start_line: int, end_line: int, new_text: str) -> str:
    """Replace an inclusive line range inside an existing file."""
    result = replace_file_lines(file_path, start_line, end_line, new_text)
    if result["success"]:
        return (
            f"Patched file via line replacement: {result['file_path']} "
            f"(lines {start_line}-{end_line})\n"
            f"{result.get('diff_preview') or 'No diff preview available.'}"
        )
    return f"ERROR {result['error']}"


@tool
def list_files(directory: str = ".") -> str:
    """List all files in the active project root or a subdirectory."""
    result = list_project_files(directory)
    if not result["success"]:
        return f"ERROR {result['error']}"

    lines = [f"Project: {result['directory']} ({result['total_files']} files)\n"]
    for file_info in result["files"]:
        size_kb = file_info["size"] / 1024
        lines.append(f"  {file_info['path']} ({size_kb:.1f} KB)")

    if result["total_files"] > 50:
        lines.append(f"\n  ... and {result['total_files'] - 50} more files")

    return "\n".join(lines)


@tool
def search_workspace(search_term: str) -> str:
    """
    Search for a string across all files in the active project root.

    Kept under the existing tool name to avoid prompt/tool contract churn.
    """
    result = search_in_files(search_term)
    if not result["success"]:
        return f"ERROR {result.get('error', 'Search failed')}"

    if not result["matches"]:
        return f"No matches found for '{search_term}' in {result['files_searched']} files."

    lines = [f"Found {len(result['matches'])} matches for '{search_term}':\n"]
    for match in result["matches"]:
        lines.append(f"  {match['file']}:{match['line']} -> {match['content']}")

    if result.get("truncated"):
        lines.append("\n  ... [results truncated at 30 matches]")

    return "\n".join(lines)
