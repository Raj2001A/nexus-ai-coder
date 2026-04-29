# Phase 3 Report

## Scope

Phase 3 goal:
replace the Python-only execution assumption with a language-aware runner abstraction and add controlled repo-local verification commands.

## Work completed

### 1. Closed the Phase 2 review issues

Fixed the issues identified in the review pass:

- active project root and indexed collection can no longer drift silently when switching projects
- chat retrieval now uses the active collection rather than assuming the default collection
- temporary inline execution no longer leaves persistent temp scripts in the real project root

Files updated:

- `backend/api/main.py`
- `backend/project_manager.py`
- `backend/rag/retriever.py`
- `backend/graph/state.py`
- `backend/graph/workflow.py`

### 2. Added active collection tracking

The active project state now includes the active collection name.

This allows:

- ingestion to keep project root and retrieval index aligned
- chat and retrieval to operate against the same active collection
- collection metadata to be surfaced consistently

### 3. Introduced a language-aware execution abstraction

Replaced the old execution module with a runtime-aware runner design in:

- `backend/tools/code_runner.py`

Capabilities added:

- runtime normalization by language
- runtime detection by file extension
- shared subprocess execution path
- temp snippet execution with cleanup
- existing-file execution by runtime
- controlled project command execution

### 4. Added JavaScript and TypeScript execution support

Supported runtimes now include:

- Python
- JavaScript via Node.js
- TypeScript via Node.js transform-types support

This support is available for:

- inline snippets
- existing project files

### 5. Added controlled repo-local command execution

Added `run_project_command` with a restrictive allowlist.

Allowed command forms:

- `pytest ...`
- `python -m pytest ...`
- `node <project-file>`
- `npm test`
- `npm run test`
- `npm run build`

Rejected:

- shell chaining
- redirection
- command substitution
- arbitrary Python eval
- arbitrary npm subcommands

### 6. Updated agent tooling

Updated:

- `backend/agents/executor.py`
- `backend/agents/reviewer.py`

Agents can now use:

- `run_python_code`
- `run_javascript_code`
- `run_typescript_code`
- `run_existing_file`
- `run_project_command`

### 7. Expanded tests

Added and updated tests for:

- active collection propagation
- forced re-ingestion when switching projects
- temp snippet cleanup
- JavaScript file execution
- TypeScript file execution
- command allowlist enforcement
- allowed project command execution

Files updated:

- `tests/test_api.py`
- `tests/test_code_runner.py`
- `tests/test_project_manager.py`

## Verification

Verification run:

- command: `.\.venv\Scripts\python -m pytest tests`
- result: `28 passed`

## Technical outcome

At the end of Phase 3:

- execution is no longer Python-only
- the system has a reusable runtime abstraction
- repo-local verification commands are available with policy controls
- the previously reported Phase 2 consistency issues are fixed

## Remaining limitations

Phase 3 intentionally does not solve:

1. frontend inspection of changed files and retrieved chunks
2. patch/diff-oriented editing
3. integrated RAG evaluation flow in the main UX
4. broader runtime coverage beyond Python, JS, and TS

## Review status

Phase 3 can be considered complete.

Reason:

- runtime abstraction is implemented
- JS/TS execution support is in place
- controlled command execution exists
- the Phase 2 review issues were fixed
- tests covering the new paths pass

## Recommendation for next phase

The next high-value phase is UX and trust.

Immediate implementation order:

1. show retrieved context in the UI
2. show changed files or diffs in the UI
3. surface reviewer failure reasons more clearly
4. expose evaluation outputs in a usable form

That is the next step that most improves demo and interview quality.
