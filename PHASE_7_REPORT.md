# Phase 7 Report

## Phase goal

Phase 7 focused on repository-native review and a scoped self-improvement loop for the assistant itself.

The self-improvement direction here is intentional:

- not "the assistant silently rewrites itself"
- but "the assistant learns from persisted run outcomes and surfaces concrete engineering improvements"

That is the stronger interview story because it is measurable, reviewable, and defensible.

## Work completed

### 1. Added self-improvement analytics over persisted runs

Added [backend/run_analytics.py](backend/run_analytics.py):

- aggregates persisted run history
- computes pass/fail trends
- computes average iteration cost
- identifies repeated changed-file hotspots
- identifies repeated failed verification classes
- generates concrete improvement insights for the assistant project

This is the new self-improvement feature. It does not mutate code automatically. It turns historical run evidence into prioritized engineering recommendations.

### 2. Extended run history access for analytics

Updated [backend/run_history.py](backend/run_history.py):

- added full-record listing for analytics use

### 3. Added repository-native git patch review

Updated [backend/git_inspector.py](backend/git_inspector.py):

- added current-worktree patch retrieval
- keeps graceful fallback for non-git projects

This enables review flows that are closer to how real engineers inspect changes.

### 4. Added backend APIs for analytics and git review

Updated [backend/api/main.py](backend/api/main.py):

- added `GET /analytics/summary`
- added `GET /review/git-patch`

The analytics endpoint supports active-project-scoped review of the assistant's historical performance.

### 5. Upgraded the frontend review workflow

Updated:

- [frontend/index.html](frontend/index.html)
- [frontend/app.js](frontend/app.js)
- [frontend/style.css](frontend/style.css)

Frontend additions:

- assistant insights panel
- current git patch panel
- analytics refresh after completed runs
- persisted-run review still works alongside the new analytics layer

### 6. Expanded test coverage

Added:

- [tests/test_run_analytics.py](tests/test_run_analytics.py)

Updated:

- [tests/test_api.py](tests/test_api.py)

Coverage added for:

- analytics endpoint
- git patch endpoint
- run analytics insight generation

## Verification

Backend tests:

```bash
./.venv/Scripts/python -m pytest tests
```

Result:

- `40 passed`

Frontend static check:

```bash
node --check frontend/app.js
```

Result:

- passed

## Current outcome

The project now has three strong interview-level traits:

1. persistent run evidence
2. repository-native review surfaces
3. a scoped self-improvement loop backed by actual historical outcomes

That is materially better than a generic "AI agent" demo because it shows:

- system design
- observability
- evaluation thinking
- review maturity
- product judgment

## Remaining limitations

- self-improvement insights are heuristic, not model-generated
- git patch review reflects current repository state, not historical snapshots
- run history is local only
- analytics are not yet fed back into agent prompts or routing decisions
- runtime coverage still centers on Python, JavaScript, and TypeScript

## Recommended next phase

Phase 8 should focus on turning evaluation into closed-loop behavior:

1. feed analytics-derived guidance into planner/executor prompts
2. add richer retrieval and verification evaluation metrics
3. add historical patch snapshots for exact run-time review
4. add user/session-aware filtering for run history and insights
