"""
run_history.py
--------------
Persist completed assistant runs to disk for later review.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.config import settings


def _history_dir() -> Path:
    path = Path(settings.run_history_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_path(run_id: str) -> Path:
    return _history_dir() / f"{run_id}.json"


def persist_run_record(record: dict) -> dict:
    run_id = record.get("run_id") or f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    payload = {
        **record,
        "run_id": run_id,
        "created_at": record.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    _run_path(run_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_run_record(run_id: str) -> dict | None:
    path = _run_path(run_id)
    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def list_run_records(limit: int = 20) -> list[dict]:
    records: list[dict] = []
    for path in sorted(_history_dir().glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        records.append(
            {
                "run_id": payload.get("run_id"),
                "created_at": payload.get("created_at"),
                "task": payload.get("task"),
                "review_passed": payload.get("review_passed"),
                "iterations": payload.get("iterations"),
                "trust_metrics": payload.get("trust_metrics", {}),
                "active_project_name": payload.get("active_project_name"),
            }
        )

        if len(records) >= limit:
            break

    return records


def list_full_run_records(limit: int = 50) -> list[dict]:
    records: list[dict] = []
    for path in sorted(_history_dir().glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        records.append(payload)
        if len(records) >= limit:
            break

    return records
