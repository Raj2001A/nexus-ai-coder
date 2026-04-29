# Phase 4 Report

## Phase goal

Phase 4 focused on trust and reviewability in the browser UI.

The backend already had multi-agent execution, direct project editing, and runtime-aware verification. What it lacked was a clear way for a reviewer to answer two basic questions:

1. What code context did the system retrieve before acting?
2. What files did the system actually change?

This phase closed that gap.

## Work completed

### 1. Added project change artifacts

Created [backend/project_artifacts.py](backend/project_artifacts.py) to support deterministic post-run inspection:

- capture project snapshots
- ignore common generated/vendor directories
- derive changed-file summaries
- generate truncated unified diff previews for text files
- normalize artifact paths to POSIX-style for stable UI/test behavior

### 2. Extended retrieval output for UI use

Updated [backend/rag/retriever.py](backend/rag/retriever.py):

- kept existing prompt formatting for agents
- added `serialize_results(...)` for API/UI consumption
- added preview extraction for retrieved chunks

### 3. Extended API and WebSocket responses

Updated [backend/api/main.py](backend/api/main.py):

- `/search` now returns `structured_results`
- `/chat` now returns `changed_files`
- `WS /ws/chat` now streams:
  - structured retrieval items for the RAG step
  - changed-file artifacts in the final `complete` payload
- snapshots are captured before and after execution to produce review artifacts

### 4. Upgraded the frontend trust surface

Updated:

- [frontend/index.html](frontend/index.html)
- [frontend/app.js](frontend/app.js)
- [frontend/style.css](frontend/style.css)

Frontend improvements:

- active project metadata is visible
- retrieved code context is listed with file path, language, and chunk info
- changed files are listed with status, file size, and diff previews
- WebSocket handling now renders structured inspection data instead of relying only on trace text
- output rendering is safer because trace and inspection content is HTML-escaped before insertion
- WebSocket URL selection now supports both `ws://` and `wss://`

### 5. Added test coverage for the new contracts

Updated [tests/test_api.py](tests/test_api.py):

- search endpoint structured results
- chat endpoint changed-file payload
- WebSocket retrieval/change artifact streaming

Added [tests/test_project_artifacts.py](tests/test_project_artifacts.py):

- ignored directory behavior
- diff preview generation

## Verification

Test command:

```bash
./.venv/Scripts/python -m pytest tests
```

Result:

- `31 passed`

Additional sanity check:

- verified the FastAPI app starts successfully with `uvicorn` in foreground mode on local port `8010`

## Issues found during the phase

One real portability issue showed up during testing:

- changed-file artifact paths used platform-native separators
- fixed by normalizing snapshot paths to POSIX-style

That fix is now covered by tests.

## Current outcome

The project now has a substantially better interview/demo surface:

- a reviewer can see the active project
- a reviewer can inspect retrieved context
- a reviewer can inspect changed files and diff previews
- the UI is closer to a usable engineering tool instead of a black-box demo

## Remaining limitations

- diff previews are only shown for smaller UTF-8 text files
- the graph result still does not expose deeper evaluation metrics
- ZIP-based projects still operate on the managed extracted copy
- execution artifacts are shown per run, but there is no persistent run history yet

## Recommended next phase

Phase 5 should focus on edit quality and verification credibility:

1. move from whole-file write behavior toward patch-oriented edits where possible
2. make verification outputs first-class review artifacts
3. tighten command policy and runtime detection around repo-local test/build execution
4. add persistent run history so interview reviewers can inspect previous task executions
