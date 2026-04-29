"""
run_analytics.py
----------------
Aggregate persisted run history into review metrics and self-improvement
recommendations for the assistant project itself.
"""

from __future__ import annotations

from collections import Counter

from backend.run_history import list_full_run_records


def _matches_scope(record: dict, active_project_name: str | None, active_project_dir: str | None) -> bool:
    if active_project_dir and record.get("active_project_dir") == active_project_dir:
        return True
    if active_project_name and record.get("active_project_name") == active_project_name:
        return True
    return active_project_name is None and active_project_dir is None


def _top_changed_paths(records: list[dict], limit: int = 5) -> list[dict]:
    counter: Counter[str] = Counter()
    for record in records:
        for file_info in record.get("changed_files", []):
            path = file_info.get("path")
            if path:
                counter[path] += 1
    return [{"path": path, "count": count} for path, count in counter.most_common(limit)]


def _top_failed_classifications(records: list[dict], limit: int = 5) -> list[dict]:
    counter: Counter[str] = Counter()
    for record in records:
        for run in record.get("verification_runs", []):
            if run.get("success") is False:
                classification = run.get("classification") or run.get("kind") or "unknown"
                counter[classification] += 1
    return [{"classification": item, "count": count} for item, count in counter.most_common(limit)]


def _build_improvement_insights(
    records: list[dict],
    pass_rate: float,
    avg_iterations: float,
    failed_classifications: list[dict],
    top_changed_paths: list[dict],
) -> list[dict]:
    insights: list[dict] = []

    if not records:
        return insights

    if pass_rate < 0.75:
        insights.append(
            {
                "category": "review_quality",
                "severity": "high",
                "title": "Approval rate is below target",
                "reason": f"Only {pass_rate:.0%} of recent runs passed review.",
                "recommended_action": (
                    "Tighten executor verification before handoff and add more direct project-specific "
                    "verification commands to reduce reviewer rejections."
                ),
            }
        )

    if avg_iterations > 1.5:
        insights.append(
            {
                "category": "iteration_cost",
                "severity": "medium",
                "title": "Runs require multiple review loops",
                "reason": f"Recent runs average {avg_iterations:.1f} iteration(s).",
                "recommended_action": (
                    "Improve first-pass execution quality by expanding targeted edit usage and making "
                    "reviewer feedback patterns part of executor guidance."
                ),
            }
        )

    if failed_classifications:
        top = failed_classifications[0]
        insights.append(
            {
                "category": "verification_policy",
                "severity": "medium",
                "title": "A verification class fails repeatedly",
                "reason": f"{top['classification']} is the most common failed verification class.",
                "recommended_action": (
                    "Add stack-specific verification helpers or clearer command policy around this "
                    "classification before expanding broader runtime coverage."
                ),
            }
        )

    if top_changed_paths:
        top = top_changed_paths[0]
        insights.append(
            {
                "category": "hotspot",
                "severity": "low",
                "title": "A small set of files changes repeatedly",
                "reason": f"{top['path']} appears in {top['count']} recent runs.",
                "recommended_action": (
                    "Review whether this area needs stronger abstraction, better tests, or clearer API "
                    "boundaries to reduce repetitive edits."
                ),
            }
        )

    return insights


def summarize_run_history(
    *,
    limit: int = 50,
    active_project_name: str | None = None,
    active_project_dir: str | None = None,
) -> dict:
    records = [
        record
        for record in list_full_run_records(limit=limit)
        if _matches_scope(record, active_project_name, active_project_dir)
    ]

    total_runs = len(records)
    passed_runs = sum(1 for record in records if record.get("review_passed"))
    pass_rate = (passed_runs / total_runs) if total_runs else 0.0
    avg_iterations = (
        sum(record.get("iterations", 0) for record in records) / total_runs if total_runs else 0.0
    )
    avg_changed_files = (
        sum(len(record.get("changed_files", [])) for record in records) / total_runs if total_runs else 0.0
    )
    avg_verifications = (
        sum(len(record.get("verification_runs", [])) for record in records) / total_runs if total_runs else 0.0
    )

    failed_classifications = _top_failed_classifications(records)
    top_changed_paths = _top_changed_paths(records)
    insights = _build_improvement_insights(
        records,
        pass_rate,
        avg_iterations,
        failed_classifications,
        top_changed_paths,
    )

    return {
        "scope": {
            "active_project_name": active_project_name,
            "active_project_dir": active_project_dir,
        },
        "summary": {
            "total_runs": total_runs,
            "passed_runs": passed_runs,
            "failed_runs": total_runs - passed_runs,
            "pass_rate": pass_rate,
            "avg_iterations": avg_iterations,
            "avg_changed_files": avg_changed_files,
            "avg_verifications": avg_verifications,
        },
        "top_changed_paths": top_changed_paths,
        "failed_verification_classes": failed_classifications,
        "improvement_insights": insights,
    }
