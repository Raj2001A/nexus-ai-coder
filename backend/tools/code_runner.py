"""
code_runner.py
--------------
Language-aware execution tools for the active project root.

Phase 3 goals:
    - introduce a runner abstraction by runtime
    - support Python, JavaScript, and TypeScript execution
    - allow controlled project-local command execution for verification tasks
"""

import logging
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from langchain_core.tools import tool

from backend.project_manager import require_active_project_root
from backend.run_artifacts import record_verification_run

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT = 30
MAX_OUTPUT_LENGTH = 5000

RUNTIME_FILE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
}

INLINE_LANGUAGE_TO_RUNTIME = {
    "python": "python",
    "py": "python",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
}

INLINE_RUNTIME_TO_SUFFIX = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
}


def _get_project_root() -> Path:
    return require_active_project_root()


def _validate_inside_project(file_path: str) -> Path:
    project_root = _get_project_root()
    resolved = (project_root / file_path).resolve()

    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise PermissionError(
            f"Access denied: '{file_path}' is outside the active project root. "
            f"All execution must stay within '{project_root}'"
        ) from exc

    return resolved


def _truncate_output(text: str) -> str:
    if len(text) > MAX_OUTPUT_LENGTH:
        return text[:MAX_OUTPUT_LENGTH] + f"\n\n... [TRUNCATED - {len(text)} total chars]"
    return text


def _runtime_env(project_root: Path) -> dict:
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(project_root) if not python_path else f"{project_root}{os.pathsep}{python_path}"
    return env


def _to_project_relative(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _run_subprocess(command: list[str], cwd: Path) -> dict:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT,
            cwd=str(cwd),
            env=_runtime_env(cwd),
        )
        return {
            "success": result.returncode == 0,
            "stdout": _truncate_output(result.stdout),
            "stderr": _truncate_output(result.stderr),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"EXECUTION TIMEOUT: Process exceeded {EXECUTION_TIMEOUT} second limit.",
            "exit_code": -1,
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"EXECUTION ERROR: {str(exc)}",
            "exit_code": -1,
        }


def _normalize_runtime(language: str) -> str:
    runtime = INLINE_LANGUAGE_TO_RUNTIME.get(language.strip().lower())
    if runtime is None:
        raise ValueError(
            f"Unsupported language '{language}'. Supported values: python, javascript, typescript."
        )
    return runtime


def _detect_runtime_from_path(resolved_path: Path) -> str:
    runtime = RUNTIME_FILE_EXTENSIONS.get(resolved_path.suffix.lower())
    if runtime is None:
        supported = ", ".join(sorted(RUNTIME_FILE_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{resolved_path.suffix}'. Supported extensions: {supported}")
    return runtime


def _build_runtime_command(runtime: str, script_path: Path) -> list[str]:
    if runtime == "python":
        return [sys.executable, str(script_path)]
    if runtime == "javascript":
        return ["node", str(script_path)]
    if runtime == "typescript":
        return ["node", "--experimental-transform-types", str(script_path)]
    raise ValueError(f"Unsupported runtime '{runtime}'")


def _format_execution_result(result: dict, artifact_label: str | None = None) -> str:
    parts = []
    parts.append("EXECUTION SUCCESSFUL" if result["success"] else "EXECUTION FAILED")

    if result["stdout"]:
        parts.append(f"\n--- STDOUT ---\n{result['stdout']}")
    if result["stderr"]:
        parts.append(f"\n--- STDERR ---\n{result['stderr']}")

    parts.append(f"\n[Exit Code: {result['exit_code']}]")
    if artifact_label:
        parts.append(f"[Artifact: {artifact_label}]")
    return "\n".join(parts)


def _record_verification_artifact(kind: str, target: str, result: dict) -> None:
    record_verification_run(
        {
            "kind": kind,
            "target": target,
            "runtime": result.get("runtime"),
            "classification": result.get("classification"),
            "success": result["success"],
            "exit_code": result["exit_code"],
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "temporary": result.get("temporary", False),
            "command": result.get("command"),
        }
    )


def execute_code(code: str, language: str) -> dict:
    """Execute inline code using the runtime for the given language."""
    project_root = _get_project_root()
    runtime = _normalize_runtime(language)
    suffix = INLINE_RUNTIME_TO_SUFFIX[runtime]

    fd, tmp_path = tempfile.mkstemp(prefix="_agent_exec_", suffix=suffix, dir=str(project_root))
    script_path = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(code)

        command = _build_runtime_command(runtime, script_path)
        result = _run_subprocess(command, project_root)
        result["file_path"] = str(script_path)
        result["runtime"] = runtime
        result["temporary"] = True
        result["classification"] = f"{runtime}_inline"
        _record_verification_artifact("inline", f"temporary snippet ({runtime})", result)
        return result
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            logger.warning(f"[CodeRunner] Could not clean up temp script: {script_path}")


def execute_file(file_path: str) -> dict:
    """Execute an existing project file using the runtime inferred from its extension."""
    resolved = _validate_inside_project(file_path)
    project_root = _get_project_root()

    if not resolved.exists():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"File not found: {file_path}",
            "exit_code": -1,
            "file_path": str(resolved),
        }

    runtime = _detect_runtime_from_path(resolved)
    command = _build_runtime_command(runtime, resolved)
    result = _run_subprocess(command, project_root)
    result["file_path"] = str(resolved)
    result["runtime"] = runtime
    result["temporary"] = False
    result["classification"] = f"{runtime}_file"
    _record_verification_artifact("file", _to_project_relative(resolved, project_root), result)
    return result


def _normalize_project_command(command: str) -> dict:
    stripped = command.strip()
    if not stripped:
        raise ValueError("Command must not be empty.")

    forbidden_tokens = ["&&", "||", ";", "|", ">", "<", "`", "$("]
    if any(token in stripped for token in forbidden_tokens):
        raise ValueError("Shell chaining, redirection, and command substitution are not allowed.")

    args = shlex.split(stripped, posix=False)
    if not args:
        raise ValueError("Command must not be empty.")

    command_name = args[0].lower()

    if command_name == "pytest":
        return {
            "command": [sys.executable, "-m", "pytest", *args[1:]],
            "classification": "python_test",
        }

    if command_name in {"python", "python.exe"}:
        if len(args) >= 3 and args[1] == "-m" and args[2] == "pytest":
            return {
                "command": [sys.executable, "-m", "pytest", *args[3:]],
                "classification": "python_test",
            }
        raise ValueError("Only 'python -m pytest ...' is allowed for Python project commands.")

    if command_name == "node":
        if len(args) < 2:
            raise ValueError("Node commands must target an existing project script file.")
        script_path = _validate_inside_project(args[1])
        if not script_path.exists():
            raise ValueError(f"Node script does not exist: {args[1]}")
        if script_path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"}:
            raise ValueError("Node verification scripts must be JavaScript or TypeScript files.")
        safe_tokens = ("test", "verify", "check", "smoke")
        if not any(token in script_path.stem.lower() for token in safe_tokens):
            raise ValueError(
                "Direct node verification scripts must be explicitly verification-oriented "
                "(filename should include test, verify, check, or smoke)."
            )
        return {
            "command": ["node", str(script_path), *args[2:]],
            "classification": "node_verification_script",
        }

    if command_name in {"npm", "npm.cmd"}:
        npm_command = "npm.cmd" if os.name == "nt" else "npm"
        if len(args) == 2 and args[1] == "test":
            return {"command": [npm_command, "test"], "classification": "npm_test"}
        if len(args) == 3 and args[1] == "run" and args[2] in {"test", "build"}:
            return {
                "command": [npm_command, "run", args[2]],
                "classification": f"npm_{args[2]}",
            }
        raise ValueError("Allowed npm commands: 'npm test', 'npm run test', 'npm run build'.")

    raise ValueError(
        "Unsupported project command. Allowed commands: pytest, python -m pytest, "
        "node <project-file>, npm test, npm run test, npm run build."
    )


def execute_project_command(command: str) -> dict:
    """Execute a controlled verification command inside the active project root."""
    project_root = _get_project_root()
    normalized = _normalize_project_command(command)
    normalized_command = normalized["command"]
    result = _run_subprocess(normalized_command, project_root)
    result["command"] = normalized_command
    result["classification"] = normalized["classification"]
    _record_verification_artifact("command", " ".join(normalized_command), result)
    return result


@tool
def run_python_code(code: str) -> str:
    """Execute Python code inside the active project root."""
    logger.info("[CodeRunner Tool] Agent executing Python code.")
    result = execute_code(code, "python")
    return _format_execution_result(result, "temporary python snippet")


@tool
def run_javascript_code(code: str) -> str:
    """Execute JavaScript code inside the active project root using Node.js."""
    logger.info("[CodeRunner Tool] Agent executing JavaScript code.")
    result = execute_code(code, "javascript")
    return _format_execution_result(result, "temporary javascript snippet")


@tool
def run_typescript_code(code: str) -> str:
    """Execute TypeScript code inside the active project root using Node.js transform-types support."""
    logger.info("[CodeRunner Tool] Agent executing TypeScript code.")
    result = execute_code(code, "typescript")
    return _format_execution_result(result, "temporary typescript snippet")


@tool
def run_existing_file(file_path: str) -> str:
    """Execute an existing Python, JavaScript, or TypeScript file from the active project root."""
    logger.info(f"[CodeRunner Tool] Agent running file: {file_path}")
    result = execute_file(file_path)
    return _format_execution_result(result, result.get("file_path"))


@tool
def run_project_command(command: str) -> str:
    """
    Execute a controlled verification command inside the active project root.

    Allowed forms:
    - pytest ...
    - python -m pytest ...
    - node <project-file>
    - npm test
    - npm run test
    - npm run build
    """
    logger.info(f"[CodeRunner Tool] Agent running project command: {command}")
    try:
        result = execute_project_command(command)
    except Exception as exc:
        return f"ERROR {str(exc)}"

    command_display = " ".join(result.get("command", []))
    return _format_execution_result(result, command_display)
