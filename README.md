# AI Multi-Agent Coding Assistant

An interview-focused AI full stack project that demonstrates:

- codebase RAG over a real project
- multi-agent orchestration with planning, execution, and review
- backend streaming with FastAPI + WebSockets
- a browser UI for ingestion, chat, and live agent tracing

The target outcome is not a generic chatbot. It is a developer-facing coding assistant that can inspect a codebase, reason about requested changes, modify that project directly, and show its working steps.

## Positioning

For interview value, this project optimizes for:

1. clear system design
2. credible implementation depth
3. observable agent behavior
4. defensible engineering tradeoffs

The product target is:

- portfolio/demo first
- but with a narrow, real, usable workflow

That is a better interview project than either a toy demo or an over-scoped platform.

## Current capabilities

- Ingest a local directory into a Chroma-backed code index
- Ingest a ZIP file into managed project storage and make it the active project
- Track one active codebase and active collection at a time
- Retrieve relevant code context with hybrid search
- Run a LangGraph workflow:
  - RAG retrieval
  - planner agent
  - executor agent
  - reviewer agent
  - retry loop
- Stream agent progress to the frontend over WebSockets
- Persist completed runs for later review
- Surface active project metadata, retrieved context, changed-file diff previews, verification runs, trust metrics, and assistant improvement insights in the frontend
- Aggregate persisted runs into self-improvement recommendations for the assistant project
- Provide agent tools for:
  - direct project file operations
  - targeted patch-style edits for existing files
  - Python, JavaScript, and TypeScript execution inside the active project
  - controlled repo-local verification commands with explicit classification
  - documentation lookup
- Enforce active-project path boundaries for edits and execution
- Include a backend test suite that covers API flow, project state, path safety, and runtimes

## Current limitations

- Runtime coverage currently focuses on Python, JavaScript, and TypeScript only
- RAG evaluation exists in code, but is not exposed in the UI or API flow
- ZIP uploads are editable after extraction, but they operate on the managed extracted copy rather than an original external repo
- Run history is persisted locally, but there is not yet a multi-user/session model
- Git patch review is current-worktree based and not tied to historical run snapshots

## Target product direction

The current design direction for this project is:

- direct project editing with guardrails
- one active codebase at a time
- broaden runtime coverage over time
- keep the architecture simple enough to explain in interviews

## Tech stack

- Orchestration: LangGraph
- Agents: CrewAI
- LLM: Gemini
- RAG: ChromaDB + Gemini embeddings
- Backend: FastAPI + WebSockets
- Frontend: HTML, CSS, vanilla JavaScript

## Repository structure

```text
backend/
  agents/      planner, executor, reviewer
  api/         FastAPI app and websocket endpoints
  graph/       LangGraph state + workflow
  rag/         ingestion, retrieval, evaluation
  tools/       file ops, code runner, doc search
  project_manager.py
frontend/
  index.html
  app.js
  style.css
tests/
Dockerfile
docker-compose.yml
requirements.txt
```

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 24+
- A Gemini API key
- Optional: Tavily API key for improved documentation search

### Environment

Create `.env` from `.env.example` and set:

```env
GOOGLE_API_KEY=your_key_here
TAVILY_API_KEY=
CHROMA_PERSIST_DIR=./chroma_db
MANAGED_PROJECTS_DIR=./managed_projects
ACTIVE_PROJECT_STATE_FILE=./managed_projects/active_project.json
RUN_HISTORY_DIR=./managed_projects/run_history
DEBUG=True
```

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the API server from the repo root:

```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000
```

## Run with Docker

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

## API surface

- `GET /health`
- `GET /collections`
- `POST /ingest/directory`
- `POST /ingest/upload`
- `POST /search`
- `POST /chat`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /analytics/summary`
- `GET /review/git-patch`
- `WS /ws/chat`

## Architecture summary

1. A codebase is ingested into Chroma with language-aware chunking.
2. That codebase becomes the single active project root and active collection.
3. A user sends a coding request.
4. The retriever fetches relevant code context.
5. The planner generates an implementation plan.
6. The executor attempts the implementation against the active project.
7. Verification can use runtime-aware file execution or controlled project commands.
8. The reviewer evaluates the result.
9. The graph retries until pass or max iteration limit.

## Verification

Backend verification currently includes:

- API tests
- runtime execution tests
- file tool path safety tests
- workflow routing tests
- reviewer verdict parsing tests
- config parsing tests
- active project and active collection state tests

Run:

```bash
python -m pytest tests
```

## Next implementation priorities

1. Add deeper evaluation signals and use them inside planning/review decisions
2. Add repository-native patch export and apply workflows
3. Broaden runtime coverage and repo-local verification policies
4. Add a multi-session or user-aware review history model

## Notes

- This workspace snapshot is not currently a git checkout.
- The local `.env` contains a populated API key and should be treated as sensitive.
