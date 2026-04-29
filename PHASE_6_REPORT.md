# Phase 6 Report

## Phase goal

Phase 6 focused on persistence and review workflow maturity:

1. persist run history and verification artifacts
2. add git-aware diff summaries for changed files
3. expose evaluation and trust metrics more explicitly
4. tighten repo-local verification policies with better command classification

This phase moved the project from a single-run interactive demo toward a reviewable engineering tool.

## Work completed

### 1. Persisted completed runs

Added [backend/run_history.py](backend/run_history.py):

- persists completed runs as JSON records
- supports run listing
- supports run detail lookup

Updated configuration:

- [backend/config.py](backend/config.py)
- [.env.example](.env.example)

New setting:

- `RUN_HISTORY_DIR`

Added API endpoints in [backend/api/main.py](backend/api/main.py):

- `GET /runs`
- `GET /runs/{run_id}`

Completed runs now persist:

- task
- final answer
- iterations
- review verdict
- retrieved context
- changed files
- verification runs
- trust metrics
- active project metadata

### 2. Added git-aware change summaries

Added [backend/git_inspector.py](backend/git_inspector.py):

- detects whether the active project is a git repo
- reads branch name when available
- parses porcelain status
- enriches changed files with git status
- adds per-file numstat summaries when available

Updated [backend/api/main.py](backend/api/main.py) to enrich changed-file artifacts before returning and persisting them.

### 3. Exposed explicit trust metrics

Updated [backend/api/main.py](backend/api/main.py):

- computes explicit trust metrics for every run
- includes them in `/chat` responses
- includes them in WebSocket completion payloads
- persists them in run history

Trust metrics currently include:

- retrieved chunk count
- changed file count
- changed file status breakdown
- verification totals
- passed and failed verification counts
- verification counts by kind
- verification counts by classification
- review verdict
- iteration count
- git availability
- git branch
- dirty file count

### 4. Tightened verification command policy

Updated [backend/tools/code_runner.py](backend/tools/code_runner.py):

- repo-local commands now carry explicit classifications
- classifications are recorded in verification artifacts
- direct `node <file>` verification is now restricted to verification-oriented filenames
- npm command classification is explicit (`npm_test`, `npm_build`)
- Python test commands are classified as `python_test`
- inline and file execution now record runtime-specific classifications

This improves both safety and auditability.

### 5. Carried retrieval evidence through the workflow

Updated:

- [backend/graph/state.py](backend/graph/state.py)
- [backend/graph/workflow.py](backend/graph/workflow.py)

The HTTP workflow path now retains structured retrieval items, so persisted run records have consistent evidence whether the user used `/chat` or WebSockets.

### 6. Upgraded the frontend review surface

Updated:

- [frontend/index.html](frontend/index.html)
- [frontend/app.js](frontend/app.js)
- [frontend/style.css](frontend/style.css)

Frontend additions:

- recent persisted run history list
- run detail loading from persisted records
- trust metrics panel
- verification run display with classifications
- git-aware change metadata display in changed files

This gives the project a much stronger interview/demo story: the reviewer can inspect both the current run and previous runs without rerunning the workflow.

### 7. Expanded test coverage

Updated:

- [tests/conftest.py](tests/conftest.py)
- [tests/test_api.py](tests/test_api.py)
- [tests/test_code_runner.py](tests/test_code_runner.py)

Added:

- [tests/test_run_history.py](tests/test_run_history.py)

Coverage added for:

- persisted run listing and retrieval
- trust metric and run ID payloads
- verification command classification
- stricter node verification script rules
- non-git fallback behavior

## Verification

Backend test suite:

```bash
./.venv/Scripts/python -m pytest tests
```

Result:

- `37 passed`

Frontend static check:

```bash
node --check frontend/app.js
```

Result:

- passed

## Current outcome

The project now supports a much more mature review workflow:

- completed runs are persisted
- prior runs can be re-opened and inspected
- changed files carry git-aware metadata when available
- trust metrics are explicit instead of implied
- verification policy is more structured and auditable

This substantially improves both usability and interview credibility.

## Remaining limitations

- run history is local-file persistence only
- there is no user/session model
- git-aware review is summary-level only and does not yet expose full repository workflows
- RAG evaluation still exists separately from the main run trust metrics
- runtime coverage still centers on Python, JavaScript, and TypeScript

## Recommended next phase

Phase 7 should focus on repository-native review and stronger evaluation:

1. add git patch/export workflows
2. surface richer evaluation signals for retrieval and verification quality
3. add session-scoped filtering and browsing for run history
4. broaden runtime and verification support beyond the current language set
