"""
run_artifacts.py
----------------
Collect per-run verification artifacts so the API and UI can show what was
actually executed during implementation and review.
"""

from __future__ import annotations

from contextvars import ContextVar


_verification_runs: ContextVar[list[dict]] = ContextVar("verification_runs", default=[])


def reset_verification_runs() -> None:
    _verification_runs.set([])


def record_verification_run(artifact: dict) -> None:
    runs = list(_verification_runs.get())
    runs.append(artifact)
    _verification_runs.set(runs)


def get_verification_runs() -> list[dict]:
    return list(_verification_runs.get())
