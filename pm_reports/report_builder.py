#!/usr/bin/env python3
"""Generate PM reports using REPORT_CONTRACT.md as the source of truth."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = {
    "daily": [
        "Yesterday completed",
        "Today plan",
        "Blockers and risks",
        "Release status",
        "Client actions needed",
    ],
    "weekly": [
        "Executive summary (RAG)",
        "Delivery status",
        "Internal issues and dependencies",
        "Capacity and workload (MD)",
        "Client-side issues/escalations",
        "Billing snapshot",
        "Focus for next week",
    ],
    "steering": [
        "Overall project health",
        "Timeline and milestones",
        "Release readiness summary",
        "Budget/billing snapshot",
        "Decisions required",
        "Next period priorities",
    ],
}


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"items": data}


def infer_rag(issues: list[dict[str, Any]]) -> str:
    statuses = {str(i.get("status", "")).lower() for i in issues}
    blocked = [i for i in issues if "block" in str(i.get("status", "")).lower()]
    if len(blocked) >= 2:
        return "Red"
    if len(blocked) == 1 or "at risk" in statuses:
        return "Amber"
    return "Green"


def summarize_issues(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No Jira issues were provided in input."
    status_counts = Counter(str(i.get("status", "Unknown")) for i in issues)
    top = ", ".join(f"{k}: {v}" for k, v in status_counts.most_common(6))
    return f"Issue volume: {len(issues)}. Status split: {top}."


def billing_snapshot(issues: list[dict[str, Any]]) -> str:
    chargeable = [i for i in issues if bool(i.get("chargeable", False))]
    spent = sum(float(i.get("actual_spent", 0) or 0) for i in chargeable)
    missing = [i.get("key", "?") for i in chargeable if i.get("actual_spent") in (None, "")]
    missing_text = ", ".join(missing[:10]) if missing else "None"
    return (
        f"Chargeable issues: {len(chargeable)}. "
        f"Actual spent total: {spent:.2f}. "
        f"Missing actual_spent fields: {missing_text}."
    )


def releases_summary(releases: list[dict[str, Any]]) -> str:
    active = [r for r in releases if not r.get("released") and not r.get("archived")]
    if not active:
        return "No active releases in input data."
    rows = []
    for r in active:
        rows.append(f"- {r.get('name', 'Unknown')} (releaseDate: {r.get('releaseDate', 'Unknown')})")
    return "\n".join(rows)


def data_quality_issues(issues: list[dict[str, Any]]) -> str:
    missing_owner = [i.get("key", "?") for i in issues if not i.get("assignee")]
    missing_status = [i.get("key", "?") for i in issues if not i.get("status")]
    lines = []
    if missing_owner:
        lines.append(f"- Missing assignee: {', '.join(missing_owner[:10])}")
    if missing_status:
        lines.append(f"- Missing status: {', '.join(missing_status[:10])}")
    return "\n".join(lines) if lines else "- No critical data-quality gaps detected in provided input."


def section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"


def build_report(report_type: str, project_name: str, jira: dict[str, Any], meetings: dict[str, Any], calendar: dict[str, Any], emails: dict[str, Any], contract_path: Path) -> str:
    issues = jira.get("issues", []) if isinstance(jira.get("issues", []), list) else []
    releases = jira.get("releases", []) if isinstance(jira.get("releases", []), list) else []
    rag = infer_rag(issues)

    parts = [
        f"# {report_type.title()} Report - {project_name}",
        f"Date: {date.today().isoformat()}",
        "Language: EN",
        f"Contract source: {contract_path}",
        f"(Inference) Overall RAG generated via v1 heuristic: **{rag}**.",
        "",
    ]

    if report_type == "daily":
        parts.append(section("Yesterday completed", summarize_issues(issues)))
        parts.append(section("Today plan", "- Continue delivery on active tickets.\n- Prioritize blocked items and release-critical work."))
        parts.append(section("Blockers and risks", "(Inference) Blocker candidates identified from issue statuses containing 'Block'."))
        parts.append(section("Release status", releases_summary(releases)))
        parts.append(section("Client actions needed", "- Confirm any pending dependencies highlighted in blockers section."))

    elif report_type == "weekly":
        parts.append(section("Executive summary (RAG)", f"(Inference) Weekly health: **{rag}** based on Jira state distribution and blockers."))
        parts.append(section("Delivery status", summarize_issues(issues)))
        parts.append(section("Internal issues and dependencies", "(Inference) Review blocked/in-progress clusters and unresolved ownership."))
        parts.append(section("Capacity and workload (MD)", "Capacity tracking unit: MD.\n(Inference) Planned vs consumed MD should be computed once Tempo feed is connected."))
        parts.append(section("Client-side issues/escalations", "- Include communication blockers extracted from meetings/emails."))
        parts.append(section("Billing snapshot", billing_snapshot(issues)))
        parts.append(section("Focus for next week", "- Close high-risk blockers.\n- De-risk nearest planned releases."))

    else:
        parts.append(section("Overall project health", f"(Inference) Current RAG: **{rag}**. Include top 3 risks and mitigation owners."))
        parts.append(section("Timeline and milestones", releases_summary(releases)))
        parts.append(section("Release readiness summary", "- Provide plan vs actual for each near-term release."))
        parts.append(section("Budget/billing snapshot", billing_snapshot(issues)))
        parts.append(section("Decisions required", "- Decision 1: Release scope cut/freeze.\n- Decision 2: Dependency escalation ownership."))
        parts.append(section("Next period priorities", "- Stabilization, dependency closure, release confidence uplift."))

    parts.append(section("Data quality issues", data_quality_issues(issues)))
    parts.append(section("Source notes", "Meetings, calendar, and emails were accepted as inputs; enrich parsing iteratively with domain-specific rules."))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PM report drafts aligned to REPORT_CONTRACT.md")
    parser.add_argument("--report-type", choices=["daily", "weekly", "steering"], required=True)
    parser.add_argument("--project", default="RetuRO")
    parser.add_argument("--jira", type=Path)
    parser.add_argument("--meetings", type=Path)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--emails", type=Path)
    parser.add_argument("--contract", type=Path, default=Path("C:/Sensoneo AI/REPORT_CONTRACT.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.contract.exists():
        raise SystemExit(f"Contract file not found: {args.contract}")

    jira = load_json(args.jira)
    meetings = load_json(args.meetings)
    calendar = load_json(args.calendar)
    emails = load_json(args.emails)

    report = build_report(
        report_type=args.report_type,
        project_name=args.project,
        jira=jira,
        meetings=meetings,
        calendar=calendar,
        emails=emails,
        contract_path=args.contract,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"OK: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
