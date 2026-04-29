# Phase 2 Report

## Scope

Phase 2 goal:
replace the old sandbox `workspace/` editing model with a single active project root model so ingestion, editing, and execution operate against the same codebase.

## Work completed

### 1. Added active project state management

Created:

- `backend/project_manager.py`

This module now handles:

- managed project storage for uploaded ZIPs
- active project root persistence
- active project metadata lookup
- wrapper-directory inference for extracted archives

### 2. Refactored file tools to use the active project root

Updated:

- `backend/tools/file_ops.py`

Changes:

- all path validation now resolves against the active project root
- read/write/list/search operations now target the active project instead of `workspace/`
- traversal protection remains in place

### 3. Refactored code execution to use the active project root

Updated:

- `backend/tools/code_runner.py`

Changes:

- code execution now runs inside the active project root
- file execution now runs the actual project file path instead of rewriting nested files into a temporary top-level copy
- path boundary enforcement remains in place

### 4. Connected ingestion to the active project model

Updated:

- `backend/api/main.py`

Changes:

- local directory ingestion now sets that directory as the active project root
- ZIP uploads are now extracted into managed persistent storage instead of a temporary directory that is immediately deleted
- safe ZIP extraction was added to block path traversal in uploaded archives
- `/collections` now returns active project metadata
- `/chat` and WebSocket chat now require an active project before execution begins

### 5. Updated agent definitions

Updated:

- `backend/agents/executor.py`
- `backend/agents/reviewer.py`

Changes:

- prompts and tool expectations now reflect active project editing rather than workspace-only editing

### 6. Expanded automated tests

Added or updated:

- `tests/conftest.py`
- `tests/test_api.py`
- `tests/test_file_ops.py`
- `tests/test_project_manager.py`

Coverage added in this phase:

- active project state handling
- ingestion setting the active project root
- ZIP upload setting the active project root
- ZIP upload rejecting unsafe archive paths
- chat refusing to run without an active project
- file tools validating against the active project
- project-root metadata behavior

## Verification

Verification run:

- command: `.\.venv\Scripts\python -m pytest tests`
- result: `21 passed`

## Technical outcome

At the end of Phase 2:

- ingestion and editing now point at the same project root
- the system has one active codebase at a time
- direct local directory editing is supported
- uploaded ZIPs remain editable through managed extracted storage
- the project boundary is enforced in both file operations and execution

## Remaining limitations

Phase 2 intentionally does not solve:

1. multi-language execution
2. patch/diff-oriented edits
3. richer frontend inspection for retrieved context and changed files
4. integrated RAG evaluation in the UI/API path

## Review status

Phase 2 can be considered complete.

Reason:

- the old `workspace/` editing model has been removed from the backend execution path
- ingestion, file operations, and execution now share the same active project model
- tests covering the new boundary behavior pass

## Recommendation for next phase

Phase 3 should introduce a language-aware execution abstraction.

Immediate implementation order:

1. define a runner interface
2. keep Python as the first runner
3. add JavaScript/TypeScript runner support
4. add controlled repo-local command execution for tests

That is the next highest-value step for interview credibility.
