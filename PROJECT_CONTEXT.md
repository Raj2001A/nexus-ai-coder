# Project Context and Next Steps

## What this project is

This repo is building an AI coding assistant with a multi-agent workflow for software tasks. The intended experience is:

1. Ingest a codebase into a RAG index.
2. Accept a user coding request.
3. Retrieve relevant code context.
4. Plan the work with a planner agent.
5. Execute the plan with a tool-using executor agent.
6. Review the result with a reviewer agent.
7. Loop until the reviewer passes or retry limits are hit.

At a high level, this is a portfolio-grade "autonomous coding assistant" project with a FastAPI backend, a simple browser UI, LangGraph orchestration, CrewAI agents, Gemini models, and Chroma-backed retrieval.

## What is currently in the repo

### Backend

- `backend/api/main.py`
  - FastAPI app.
  - Serves the frontend.
  - Provides ingestion endpoints:
    - `POST /ingest/directory`
    - `POST /ingest/upload`
  - Provides search and chat endpoints:
    - `POST /search`
    - `POST /chat`
  - Provides a WebSocket stream at `WS /ws/chat`.

- `backend/graph/workflow.py`
  - Core LangGraph orchestration.
  - Flow is `rag_retrieve -> planner -> executor -> reviewer -> finalize`.
  - Includes retry routing from reviewer back to executor.

- `backend/graph/state.py`
  - Shared typed state for the LangGraph workflow.

- `backend/agents/`
  - `planner.py`: creates the planning agent.
  - `executor.py`: creates the execution agent with tools.
  - `reviewer.py`: creates the review agent and parses `PASS` / `FAIL`.

- `backend/rag/`
  - `ingestion.py`: loads files, chunks them by language, embeds them, stores them in Chroma.
  - `retriever.py`: hybrid retrieval layer with vector search plus a simple keyword path.
  - `evaluator.py`: evaluation pipeline for RAG quality. Present, but not wired into the app flow or UI.

- `backend/tools/`
  - `file_ops.py`: sandboxed file read/write/list/search tools.
  - `code_runner.py`: sandboxed Python execution with timeout.
  - `doc_search.py`: docs/web lookup with Tavily first and DuckDuckGo fallback.

### Frontend

- `frontend/index.html`
  - Three-column UI:
    - codebase ingestion
    - central chat
    - agent trace panel

- `frontend/app.js`
  - WebSocket client for live agent updates.
  - Calls ingestion endpoints.
  - Updates pipeline status and chat output.

- `frontend/style.css`
  - Styling for the UI shell.

### Ops / local setup

- `requirements.txt`
  - Python dependencies for LangChain, LangGraph, CrewAI, FastAPI, Chroma, Gemini, and testing.

- `Dockerfile`
  - Containerized app setup.

- `docker-compose.yml`
  - Single-service compose config with persistent volumes for:
    - `chroma_db`
    - `workspace`

- `.env.example`
  - Expected environment variables.

## What the project appears to be optimized for

This looks designed for:

- a real demo or portfolio project
- interview storytelling
- showing multi-agent orchestration, not just single-prompt generation
- demonstrating RAG over codebases
- demonstrating an execution/review loop

There are strong "interview talking point" comments throughout the backend, which suggests the project is not just meant to work, but to clearly communicate architecture decisions.

## What seems complete already

- Clear separation between API, graph orchestration, agents, RAG, and tools.
- Ingestion pipeline exists and supports both local directories and ZIP uploads.
- Retrieval pipeline exists and is reusable from both API and agents.
- Frontend is already shaped around the intended workflow.
- WebSocket streaming path exists for a more live, agentic feel.
- Docker setup exists, which is a good sign for demoability.

## What seems incomplete or still rough

### 1. The app is structured well, but not yet fully production-hardened

The architecture is solid, but this still reads like a strong prototype / showcase build rather than a finished product.

### 2. No test suite is present in the repo

`pytest` and `httpx` are listed in dependencies, but there are no actual test files yet. That means the important flows are not validated in a repeatable way.

### 3. The executor writes to an internal `workspace/`, not the ingested codebase

This is an important product decision:

- RAG reads an external or uploaded codebase.
- agent tools write only inside `workspace/`.

That is good for safety, but it means the assistant currently analyzes one codebase while modifying a different sandbox area. If the goal is "edit my real project," this will need another design pass.

### 4. Evaluation exists but is not surfaced

`backend/rag/evaluator.py` is present, but there is no UI or API workflow around it yet. Right now it looks like a useful internal capability that has not been integrated into the product.

### 5. The repo currently looks light on operational polish

From this pass, I did not find:

- API tests
- frontend tests
- integration tests
- startup/run scripts beyond Docker and manual Python execution
- a richer README with setup and usage steps

### 6. There is no git metadata in this workspace snapshot

This folder currently is not a git working tree, so this looks like a copied/exported project folder rather than an active cloned repo.

### 7. Secret handling needs care

A populated `.env` file exists locally. That is fine for development, but it should stay out of version control and should be treated as sensitive.

## My current read on what we are making

We are making a developer-facing AI assistant that can:

- understand an existing codebase through RAG
- reason about requested changes using a planner
- attempt implementation with tools
- self-check through a reviewer loop
- show its progress in a simple visual interface

In other words, this is not just "chat over code." It is aiming to be a small autonomous engineering system with observable steps.

## Resolved product decisions

The product direction is now:

1. The assistant should modify the target project directly.
2. The primary goal should be interview and portfolio strength, with a narrow workflow that is still genuinely usable.
3. Execution should move toward multi-language support rather than staying Python-only.
4. RAG should represent one active codebase at a time.

## What these decisions mean in practice

### Direct project modification

This is the right choice for project credibility. A coding assistant that only edits an isolated sandbox is less convincing in interviews because it avoids the hard part: operating against a real repo safely.

The consequence is that the current `workspace/`-only tool model is now a temporary implementation detail and should be replaced with a direct project root model plus guardrails.

### Portfolio-first, but usable

For your target outcome, this is the correct balance.

If you optimize only for demo polish, interviewers may see it as surface-level.
If you optimize only for broad production utility, the project scope will expand too far.

The stronger approach is:

- keep the user path simple
- make the architecture explainable
- make one workflow work well end to end
- show disciplined tradeoffs

### Multi-language execution

Yes, this should move beyond Python.

Reason:

- a coding assistant that claims codebase-level usefulness should not be locked to one runtime forever
- multi-language support is a strong signal for AI full stack interviews
- but it should be implemented in phases, not all at once

The correct engineering move is to introduce an execution abstraction first, then add language runners incrementally.

### One codebase at a time

This is the right simplification.

It keeps:

- the mental model simple
- the UI simpler
- the retrieval model cleaner
- the interview explanation tighter

There is no need to introduce multi-project complexity in this version.

## Recommended next steps

### Phase 1: Stabilize and document the current build

1. Add a proper setup/run guide to `README.md`.
2. Add backend smoke tests for:
   - `/health`
   - `/collections`
   - `/search`
   - `/chat` with mocked agent calls
3. Add unit tests for:
   - path validation in `file_ops.py`
   - retry routing in `workflow.py`
   - verdict parsing in `reviewer.py`
4. Verify the Docker path end-to-end.

### Phase 2: Replace sandbox editing with direct project editing

1. Introduce a single active project root for tool operations.
2. Make ingestion and execution point at the same project.
3. Keep path validation, but validate against the active project root instead of `workspace/`.
4. Preserve guardrails against traversal and accidental edits outside the target project.

### Phase 3: Add a multi-language execution layer

1. Define a runner abstraction by language.
2. Keep Python first, then add JavaScript/TypeScript support.
3. Choose execution behavior based on file type or detected project stack.
4. Add controlled command execution for repo-local tests.

### Phase 4: Improve the user experience

1. Show richer agent outputs in the trace panel.
2. Display ingestion errors and collection state more clearly.
3. Add a way to inspect retrieved files/chunks from the UI.
4. Add session history or saved runs.

### Phase 5: Improve trust and evaluation

1. Wire `backend/rag/evaluator.py` into an internal evaluation command or endpoint.
2. Capture benchmark runs and save results for comparison.
3. Add clearer review failure reasons and retry visibility.

### Phase 6: Move toward a stronger assistant

1. Support direct file diffs instead of only summary output.
2. Add safer patch-oriented editing primitives.
3. Add support for running repo-local tests/commands under policy controls.
4. Consider replacing or extending the current agent stack depending on reliability.

## Suggested immediate plan for us

If we continue from here, my recommended order is:

1. Improve the README so the project can be run cleanly.
2. Add a minimal backend test suite.
3. Refactor tools from `workspace/` to an active project root model.
4. Add the first multi-language execution extension.
5. Then tighten the UI around the actual supported workflow.

That sequence gives us a project that is easier to demo, easier to reason about, and much easier to evolve without guessing.
