#!/usr/bin/env python3
"""Generate PM reports aligned to REPORT_CONTRACT.md with optional live Jira ingestion."""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"items": data}


def parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    # Jira often returns +0100 without colon
    if len(value) > 5 and (value[-5] in ["+", "-"]) and value[-3] != ":":
        value = value[:-2] + ":" + value[-2:]
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "yes", "y", "1", "billable"}


def jira_request(base_url: str, auth_header: str, path: str, query: dict[str, Any] | None = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        params = urllib.parse.urlencode(query, doseq=True)
        url = f"{url}?{params}"
    req = urllib.request.Request(url, headers={"Authorization": auth_header, "Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_field_ids(base_url: str, auth_header: str) -> dict[str, str]:
    fields = jira_request(base_url, auth_header, "/rest/api/3/field")
    mapping: dict[str, str] = {}

    def pick(name_key: str, predicate) -> None:
        if name_key in mapping:
            return
        for f in fields:
            name = str(f.get("name", "")).strip().lower()
            if predicate(name):
                mapping[name_key] = str(f.get("id"))
                return

    pick("chargeable", lambda n: n == "chargeable" or "chargeable" in n)
    pick("actual_spent", lambda n: "actual spent" in n)
    pick("time_spent_mds", lambda n: "time spent mds" in n)
    pick("refined_mds", lambda n: "refined estimation mds" in n)
    pick("calculated_mds", lambda n: "calculated estimation mds" in n)
    pick("initial_mds", lambda n: "initial estimation mds" in n)
    return mapping


def fetch_releases(base_url: str, auth_header: str, project_key: str) -> list[dict[str, Any]]:
    releases = jira_request(base_url, auth_header, f"/rest/api/3/project/{project_key}/versions")
    out = []
    for r in releases:
        out.append(
            {
                "name": r.get("name"),
                "releaseDate": r.get("releaseDate"),
                "released": bool(r.get("released")),
                "archived": bool(r.get("archived")),
            }
        )
    return out


def fetch_issues(base_url: str, auth_header: str, jql: str, field_ids: dict[str, str], limit: int = 200) -> list[dict[str, Any]]:
    selected = [
        "summary",
        "status",
        "assignee",
        "created",
        "updated",
        "issuetype",
        "priority",
        "timespent",
        "timeestimate",
        "timeoriginalestimate",
    ]
    for v in field_ids.values():
        if v and v not in selected:
            selected.append(v)

    payload = jira_request(
        base_url,
        auth_header,
        "/rest/api/3/search/jql",
        {
            "jql": jql,
            "maxResults": limit,
            "fields": ",".join(selected),
        },
    )

    issues = []
    for item in payload.get("issues", []):
        f = item.get("fields", {})
        assignee = f.get("assignee") or {}
        status = f.get("status") or {}

        raw_chargeable = f.get(field_ids.get("chargeable", ""), False) if field_ids.get("chargeable") else False
        raw_actual_spent = f.get(field_ids.get("actual_spent", "")) if field_ids.get("actual_spent") else None
        raw_time_spent_mds = f.get(field_ids.get("time_spent_mds", "")) if field_ids.get("time_spent_mds") else None

        refined = as_float(f.get(field_ids.get("refined_mds", ""))) if field_ids.get("refined_mds") else 0.0
        calculated = as_float(f.get(field_ids.get("calculated_mds", ""))) if field_ids.get("calculated_mds") else 0.0
        initial = as_float(f.get(field_ids.get("initial_mds", ""))) if field_ids.get("initial_mds") else 0.0

        planned_md = refined or calculated or initial
        timespent_seconds = as_float(f.get("timespent"))
        consumed_md_fallback = timespent_seconds / 28800.0 if timespent_seconds else 0.0

        actual_spent = as_float(raw_actual_spent)
        consumed_md = as_float(raw_time_spent_mds) or (actual_spent / 8.0 if actual_spent else consumed_md_fallback)

        issues.append(
            {
                "key": item.get("key"),
                "summary": f.get("summary"),
                "status": status.get("name"),
                "assignee": assignee.get("displayName"),
                "created": f.get("created"),
                "updated": f.get("updated"),
                "chargeable": as_bool(raw_chargeable),
                "actual_spent": actual_spent,
                "planned_md": planned_md,
                "consumed_md": consumed_md,
            }
        )
    return issues


def infer_rag(issues: list[dict[str, Any]]) -> str:
    blocked = [i for i in issues if "block" in str(i.get("status", "")).lower()]
    stale = 0
    now = datetime.now(timezone.utc)
    for i in issues:
        upd = parse_iso_date(i.get("updated"))
        if upd and (now - upd).days >= 7 and "done" not in str(i.get("status", "")).lower():
            stale += 1

    if len(blocked) >= 2 or stale >= 10:
        return "Red"
    if len(blocked) == 1 or stale >= 3:
        return "Amber"
    return "Green"


def summarize_status_split(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No Jira issues in scope."
    c = Counter(str(i.get("status") or "Unknown") for i in issues)
    return ", ".join(f"{k}: {v}" for k, v in c.most_common())


def releases_summary(releases: list[dict[str, Any]]) -> str:
    active = [r for r in releases if not r.get("released") and not r.get("archived")]
    if not active:
        return "No active releases found."
    rows = []
    for r in sorted(active, key=lambda x: str(x.get("releaseDate") or "9999-12-31")):
        rd = r.get("releaseDate") or "Unknown"
        rows.append(f"- {r.get('name', 'Unknown')} (releaseDate: {rd})")
    return "\n".join(rows)


def billing_snapshot(issues: list[dict[str, Any]]) -> str:
    chargeable = [i for i in issues if i.get("chargeable")]
    actual_total = sum(as_float(i.get("actual_spent")) for i in chargeable)
    missing = [i.get("key", "?") for i in chargeable if as_float(i.get("actual_spent")) <= 0]
    return (
        f"Chargeable issues in scope: {len(chargeable)}. "
        f"Total actual_spent: {actual_total:.2f} hours. "
        f"Missing/zero actual_spent: {', '.join(missing[:10]) if missing else 'None'}."
    )


def capacity_snapshot(issues: list[dict[str, Any]]) -> str:
    planned = sum(as_float(i.get("planned_md")) for i in issues)
    consumed = sum(as_float(i.get("consumed_md")) for i in issues)
    remaining = planned - consumed

    by_assignee: dict[str, float] = defaultdict(float)
    for i in issues:
        by_assignee[i.get("assignee") or "Unassigned"] += as_float(i.get("planned_md"))
    top = sorted(by_assignee.items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = ", ".join(f"{k}: {v:.2f} MD" for k, v in top) if top else "None"

    return (
        f"Planned MD: {planned:.2f}. Consumed MD: {consumed:.2f}. Remaining MD: {remaining:.2f}. "
        f"Top planned load: {top_text}."
    )


def data_quality_issues(issues: list[dict[str, Any]]) -> str:
    missing_assignee = [i.get("key", "?") for i in issues if not i.get("assignee")]
    missing_status = [i.get("key", "?") for i in issues if not i.get("status")]
    lines = []
    if missing_assignee:
        lines.append(f"- Missing assignee: {', '.join(missing_assignee[:10])}")
    if missing_status:
        lines.append(f"- Missing status: {', '.join(missing_status[:10])}")
    if not lines:
        lines.append("- No critical data-quality gaps detected in Jira scope.")
    return "\n".join(lines)


def section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"


def build_report(report_type: str, project_label: str, issues: list[dict[str, Any]], releases: list[dict[str, Any]], meetings: dict[str, Any], calendar: dict[str, Any], emails: dict[str, Any], contract_path: Path) -> str:
    rag = infer_rag(issues)
    now = date.today().isoformat()

    parts = [
        f"# {report_type.title()} Report - {project_label}",
        f"Date: {now}",
        "Language: EN",
        f"Contract source: {contract_path}",
        f"(Inference) Overall RAG via v1 heuristic: **{rag}**.",
        "",
    ]

    if report_type == "daily":
        done_yesterday = [
            i for i in issues if "done" in str(i.get("status", "")).lower() or "closed" in str(i.get("status", "")).lower()
        ]
        active_today = [
            i for i in issues if any(x in str(i.get("status", "")).lower() for x in ["progress", "new", "open", "backlog", "review"])
        ][:8]
        blockers = [i for i in issues if "block" in str(i.get("status", "")).lower()][:10]

        parts.append(section("Yesterday completed", f"Completed/closed items in scope: {len(done_yesterday)}. Status split: {summarize_status_split(issues)}."))
        if active_today:
            lines = "\n".join(f"- {i.get('key')}: {i.get('summary')} ({i.get('status')})" for i in active_today)
        else:
            lines = "- No active tickets in provided daily scope."
        parts.append(section("Today plan", lines))

        if blockers:
            btxt = "\n".join(f"- {b.get('key')}: {b.get('summary')} ({b.get('status')})" for b in blockers)
        else:
            btxt = "- No explicit blocked status found in scope."
        parts.append(section("Blockers and risks", "(Inference)\n" + btxt))
        parts.append(section("Release status", releases_summary(releases)))

        actions = []
        if blockers:
            actions.append("- Confirm ownership and unblock plan for blocked items.")
        unassigned = [i for i in issues if not i.get("assignee")]
        if unassigned:
            actions.append(f"- Assign owners for unassigned items: {', '.join(i.get('key', '?') for i in unassigned[:8])}.")
        if not actions:
            actions.append("- No explicit client action required from current data window.")
        parts.append(section("Client actions needed", "\n".join(actions)))

    elif report_type == "weekly":
        parts.append(section("Executive summary (RAG)", f"(Inference) Weekly delivery health: **{rag}** based on blockers, stale items, and issue distribution."))
        parts.append(section("Delivery status", f"Issue count in weekly scope: {len(issues)}. Status split: {summarize_status_split(issues)}."))

        stale_lines = []
        now_dt = datetime.now(timezone.utc)
        for i in issues:
            upd = parse_iso_date(i.get("updated"))
            if upd and (now_dt - upd).days >= 7 and "done" not in str(i.get("status", "")).lower():
                stale_lines.append(f"- {i.get('key')}: stale {(now_dt - upd).days} days ({i.get('status')})")
        deps = "\n".join(stale_lines[:10]) if stale_lines else "- No stale open issues >= 7 days in scope."
        parts.append(section("Internal issues and dependencies", deps))

        parts.append(section("Capacity and workload (MD)", capacity_snapshot(issues)))

        client_items = [i for i in issues if "client" in str(i.get("summary", "")).lower()]
        client_text = "\n".join(f"- {i.get('key')}: {i.get('summary')}" for i in client_items[:8]) if client_items else "- No explicit client-tagged issues detected by summary keyword heuristic."
        parts.append(section("Client-side issues/escalations", "(Inference)\n" + client_text))

        parts.append(section("Billing snapshot", billing_snapshot(issues)))
        parts.append(section("Focus for next week", "- Reduce blocked/stale items.\n- Protect nearest release dates.\n- Resolve data-quality gaps for assignee and billing fields."))

    else:
        parts.append(section("Overall project health", f"(Inference) Current health: **{rag}**."))
        parts.append(section("Timeline and milestones", releases_summary(releases)))
        parts.append(section("Release readiness summary", "- Readiness derived from blockers, stale items, and owner coverage."))
        parts.append(section("Budget/billing snapshot", billing_snapshot(issues)))
        parts.append(section("Decisions required", "- Confirm scope freeze or defer list for nearest release.\n- Confirm owner for top delivery risks."))
        parts.append(section("Next period priorities", "- Stabilize release-critical scope.\n- Reduce dependency risk."))

    parts.append(section("Data quality issues", data_quality_issues(issues)))
    parts.append(section("Source notes", f"Meetings input items: {len(meetings.get('items', [])) if isinstance(meetings.get('items'), list) else 0}; calendar input items: {len(calendar.get('items', [])) if isinstance(calendar.get('items'), list) else 0}; email input items: {len(emails.get('items', [])) if isinstance(emails.get('items'), list) else 0}."))
    return "\n".join(parts)


def get_auth_header_from_env() -> tuple[str, str]:
    base_url = os.getenv("JIRA_BASE_URL", "").strip()
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    if not base_url or not email or not token:
        raise RuntimeError("Missing JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN environment variables for --live-jira mode.")

    import base64

    raw = f"{email}:{token}".encode("utf-8")
    return base_url.rstrip("/"), "Basic " + base64.b64encode(raw).decode("ascii")


def live_jira_dataset(report_type: str, project_key: str) -> dict[str, Any]:
    base_url, auth_header = get_auth_header_from_env()
    field_ids = discover_field_ids(base_url, auth_header)

    if report_type == "daily":
        jql = f"project = {project_key} AND updated >= -1d ORDER BY updated DESC"
    elif report_type == "weekly":
        jql = f"project = {project_key} AND updated >= -7d ORDER BY updated DESC"
    else:
        jql = f"project = {project_key} ORDER BY updated DESC"

    issues = fetch_issues(base_url, auth_header, jql, field_ids, limit=250)
    releases = fetch_releases(base_url, auth_header, project_key)
    return {"issues": issues, "releases": releases}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PM report drafts aligned to REPORT_CONTRACT.md")
    parser.add_argument("--report-type", choices=["daily", "weekly", "steering"], required=True)
    parser.add_argument("--project", default="RetuRO")
    parser.add_argument("--project-key", default="RET")
    parser.add_argument("--live-jira", action="store_true")
    parser.add_argument("--jira", type=Path)
    parser.add_argument("--meetings", type=Path)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--emails", type=Path)
    parser.add_argument("--contract", type=Path, default=Path("C:/Sensoneo AI/REPORT_CONTRACT.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.contract.exists():
        raise SystemExit(f"Contract file not found: {args.contract}")

    if args.live_jira:
        jira = live_jira_dataset(args.report_type, args.project_key)
    else:
        jira = load_json(args.jira)

    meetings = load_json(args.meetings)
    calendar = load_json(args.calendar)
    emails = load_json(args.emails)

    issues = jira.get("issues", []) if isinstance(jira.get("issues"), list) else []
    releases = jira.get("releases", []) if isinstance(jira.get("releases"), list) else []

    report = build_report(
        report_type=args.report_type,
        project_label=args.project,
        issues=issues,
        releases=releases,
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
