# Next Phase Plan

## Product decisions

These are the settled decisions for the next build phase:

1. The assistant should modify the target project directly.
2. The project should optimize for interview impact first, with a narrow but real workflow.
3. Execution should expand to multiple languages over time.
4. The system should operate on one active codebase at a time.

## Why this direction is correct for interviews

For AI full stack interviews, the strongest signal is not maximum feature count. The strongest signal is a system that has:

- a clear architecture
- real constraints
- defensible tradeoffs
- evidence that it works

That means the correct target is:

- not a toy demo
- not a massive platform
- a focused assistant with real repo interaction, real retrieval, and real workflow control

## Implementation strategy

We should execute in this order.

### Phase 1: Stabilize the current project

Goal:
Make the current implementation runnable, understandable, and testable.

Deliverables:

1. Better `README.md`
2. Backend smoke tests
3. Core unit tests for workflow and tool safety
4. Verified local run path

Exit criteria:

- A reviewer can clone, configure, and run the app
- The main API flow has basic automated coverage
- Safety-sensitive logic has tests

### Phase 2: Direct project editing

Goal:
Make ingestion and execution operate against the same real project.

Deliverables:

1. Introduce an `active_project_dir` concept
2. Update file tools to resolve paths against that directory
3. Update code execution to run inside that directory
4. Preserve path traversal protection
5. Add tests for path safety and project-root enforcement

Exit criteria:

- The assistant reads and writes against the same target project
- It cannot escape the configured project root

### Phase 3: Multi-language execution foundation

Goal:
Replace Python-only execution assumptions with a small execution abstraction.

Deliverables:

1. Define runner interface by language/runtime
2. Keep Python runner
3. Add JavaScript/TypeScript runner support
4. Add repo-local test command execution with restrictions

Exit criteria:

- The system can choose an execution path based on project type
- At least Python and JS/TS have a defined route

### Phase 4: UX credibility

Goal:
Make the product easier to inspect during a demo.

Deliverables:

1. Better trace visibility
2. Clearer ingestion state
3. Retrieved context inspection
4. Better final output formatting

Exit criteria:

- An interviewer can see what the agents did without guessing

### Phase 5: Trust and evaluation

Goal:
Add evidence, not just claims.

Deliverables:

1. Expose RAG evaluation
2. Save benchmark outputs
3. Show retry and reviewer outcomes more clearly

Exit criteria:

- You can discuss measured quality, not only architecture

## Immediate execution plan

The immediate plan for the next working cycle is:

1. Finish documentation cleanup
2. Add backend tests
3. Refactor tool roots from `workspace/` to a real project root

This is the correct order because changing the editing model before adding basic tests would make the refactor harder to validate.

## What to say in interviews

The concise version is:

"I built a multi-agent coding assistant that ingests a codebase, retrieves relevant context, plans changes, attempts implementation, and reviews itself in a controlled loop. I kept the first version focused on one active codebase, then moved the design toward direct project editing with explicit safety boundaries and testable workflow control."
