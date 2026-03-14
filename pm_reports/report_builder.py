#!/usr/bin/env python3
"""Generate PM reports aligned to REPORT_CONTRACT.md with optional live Jira ingestion."""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MEETINGS_PATH = Path(__file__).resolve().parents[1] / "Meetings" / "records"


def load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"items": data}


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if path.is_dir():
        items: list[dict[str, Any]] = []
        for file_path in sorted(path.rglob("*.json")):
            payload = load_json_file(file_path)
            if not payload:
                continue
            if isinstance(payload.get("items"), list):
                for item in payload["items"]:
                    if isinstance(item, dict):
                        items.append(item)
            else:
                items.append(payload)
        return {"items": items}
    return load_json_file(path)


def parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
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
        "resolutiondate",
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
        issue_type = f.get("issuetype") or {}

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
                "resolutiondate": f.get("resolutiondate"),
                "issue_type": issue_type.get("name"),
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
        if upd and (now - upd).days >= 7 and "done" not in str(i.get("status", "")).lower() and "closed" not in str(i.get("status", "")).lower():
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
    if not issues:
        return "No closed Epics found in the last 3 months for capacity tracking."

    planned_total = sum(as_float(i.get("planned_md")) for i in issues)
    consumed_total = sum(as_float(i.get("consumed_md")) for i in issues)
    burn_total = (consumed_total / planned_total * 100.0) if planned_total > 0 else 0.0

    missing_planned = [i.get("key", "?") for i in issues if as_float(i.get("planned_md")) <= 0]
    missing_consumed = [i.get("key", "?") for i in issues if as_float(i.get("consumed_md")) <= 0]

    rows = [
        "| Epic | Ticket name | Status | Refined Estimation MDs (Planned) | Time Spent MDs (Consumed) | Burn % |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]

    for i in issues:
        planned = as_float(i.get("planned_md"))
        consumed = as_float(i.get("consumed_md"))
        burn = (consumed / planned * 100.0) if planned > 0 else 0.0
        rows.append(
            f"| {i.get('key', '?')} | {i.get('summary', 'Unknown')} | {i.get('status', 'Unknown')} | {planned:.2f} | {consumed:.2f} | {burn:.1f}% |"
        )

    summary = [
        "(Inference) Scope: Epic issues (issuetype = Epic) in status Closed and status changed to Closed in the last 90 days.",
        f"Summary: Planned MD = {planned_total:.2f}, Consumed MD = {consumed_total:.2f}, Burn = {burn_total:.1f}%.",
    ]

    if missing_planned:
        summary.append(f"Data quality: Missing/zero Refined Estimation MDs on {len(missing_planned)} epics ({', '.join(missing_planned[:8])}).")
    if missing_consumed:
        summary.append(f"Data quality: Missing/zero Time Spent MDs on {len(missing_consumed)} epics ({', '.join(missing_consumed[:8])}).")

    return "\n".join(summary + ["", *rows])


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


def meeting_record_date(record: dict[str, Any]) -> datetime | None:
    return parse_iso_date(record.get("meeting_date") or record.get("date"))


def filter_meetings_for_window(records: list[dict[str, Any]], report_type: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    days = 1 if report_type == "daily" else 7 if report_type == "weekly" else 30
    out = []
    for record in records:
        dt = meeting_record_date(record)
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if (now - dt).days <= days:
            out.append(record)
    return out


def flatten_meeting_items(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        payload = record.get(key, [])
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    item = dict(item)
                    item["meeting_title"] = record.get("meeting_title", "Unknown")
                    item["meeting_date"] = record.get("meeting_date", "Unknown")
                    items.append(item)
    return items


def meeting_summary_lines(records: list[dict[str, Any]], limit: int = 6) -> list[str]:
    lines: list[str] = []
    for record in records[:limit]:
        title = str(record.get("meeting_title") or "Unknown meeting")
        bullets = record.get("summary", [])
        if isinstance(bullets, list) and bullets:
            lines.append(f"- {title}: {bullets[0]}")
    return lines


def section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"


def build_report(
    report_type: str,
    project_label: str,
    issues: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    meetings: dict[str, Any],
    calendar: dict[str, Any],
    emails: dict[str, Any],
    contract_path: Path,
    epic_capacity_issues: list[dict[str, Any]] | None = None,
) -> str:
    rag = infer_rag(issues)
    now = date.today().isoformat()
    meeting_records = meetings.get("items", []) if isinstance(meetings.get("items"), list) else []
    recent_meetings = filter_meetings_for_window(meeting_records, report_type)
    meeting_actions = flatten_meeting_items(recent_meetings, "action_items")
    meeting_risks = flatten_meeting_items(recent_meetings, "risks")
    meeting_decisions = flatten_meeting_items(recent_meetings, "decisions")

    parts = [
        f"# {report_type.title()} Report - {project_label}",
        f"Date: {now}",
        "Language: EN",
        f"Contract source: {contract_path}",
        f"(Inference) Overall RAG via v1 heuristic: **{rag}**.",
        "",
    ]

    if report_type == "daily":
        done_yesterday = [i for i in issues if "done" in str(i.get("status", "")).lower() or "closed" in str(i.get("status", "")).lower()]
        active_today = [i for i in issues if any(x in str(i.get("status", "")).lower() for x in ["progress", "new", "open", "backlog", "review"])]
        blockers = [i for i in issues if "block" in str(i.get("status", "")).lower()][:10]

        yesterday_lines = [f"- Completed/closed Jira items in scope: {len(done_yesterday)}."]
        yesterday_lines.extend(meeting_summary_lines(recent_meetings, limit=4))
        parts.append(section("Yesterday completed", "\n".join(yesterday_lines)))

        today_lines = [f"- {i.get('key')}: {i.get('summary')} ({i.get('status')})" for i in active_today[:8]]
        open_actions = [a for a in meeting_actions if str(a.get("status", "Open")).lower() != "done"]
        for item in open_actions[:5]:
            today_lines.append(f"- Meeting follow-up: {item.get('action', 'Unknown action')} (owner: {item.get('owner', 'Unknown')})")
        if not today_lines:
            today_lines = ["- No active tickets in provided daily scope."]
        parts.append(section("Today plan", "\n".join(today_lines)))

        risk_lines = [f"- {b.get('key')}: {b.get('summary')} ({b.get('status')})" for b in blockers]
        for risk in meeting_risks[:6]:
            risk_lines.append(f"- Meeting risk: {risk.get('risk', 'Unknown')} (impact: {risk.get('impact', 'Unknown')}, owner: {risk.get('owner', 'Unknown')})")
        if not risk_lines:
            risk_lines = ["- No explicit blocked status or meeting risk found in scope."]
        parts.append(section("Blockers and risks", "(Inference)\n" + "\n".join(risk_lines)))
        parts.append(section("Release status", releases_summary(releases)))

        actions = []
        unassigned = [i for i in issues if not i.get("assignee")]
        if blockers:
            actions.append("- Confirm ownership and unblock plan for blocked items.")
        if unassigned:
            actions.append(f"- Assign owners for unassigned items: {', '.join(i.get('key', '?') for i in unassigned[:8])}.")
        if not actions:
            actions.append("- No explicit client action required from current data window.")
        parts.append(section("Client actions needed", "\n".join(actions)))

    elif report_type == "weekly":
        parts.append(section("Executive summary (RAG)", f"(Inference) Weekly delivery health: **{rag}** based on blockers, stale items, issue distribution, and {len(recent_meetings)} meeting records."))
        delivery_lines = [f"Issue count in weekly scope: {len(issues)}. Status split: {summarize_status_split(issues)}."]
        delivery_lines.extend(meeting_summary_lines(recent_meetings, limit=5))
        parts.append(section("Delivery status", "\n".join(delivery_lines)))

        stale_lines = []
        now_dt = datetime.now(timezone.utc)
        for i in issues:
            upd = parse_iso_date(i.get("updated"))
            if upd and (now_dt - upd).days >= 7 and "done" not in str(i.get("status", "")).lower() and "closed" not in str(i.get("status", "")).lower():
                stale_lines.append(f"- {i.get('key')}: stale {(now_dt - upd).days} days ({i.get('status')})")
        for risk in meeting_risks[:6]:
            stale_lines.append(f"- Meeting risk: {risk.get('risk', 'Unknown')} (impact: {risk.get('impact', 'Unknown')}, likelihood: {risk.get('likelihood', 'Unknown')})")
        deps = "\n".join(stale_lines[:10]) if stale_lines else "- No stale open issues >= 7 days or explicit meeting risks in scope."
        parts.append(section("Internal issues and dependencies", deps))

        capacity_scope = epic_capacity_issues if epic_capacity_issues is not None else []
        parts.append(section("Capacity and workload (MD)", capacity_snapshot(capacity_scope)))

        client_lines = []
        for issue in issues:
            if "client" in str(issue.get("summary", "")).lower():
                client_lines.append(f"- Jira: {issue.get('key')}: {issue.get('summary')}")
        for action in meeting_actions[:6]:
            action_text = str(action.get("action", "")).lower()
            if any(token in action_text for token in ["client", "service request", "incident", "returo"]):
                client_lines.append(f"- Meeting follow-up: {action.get('action')} (owner: {action.get('owner', 'Unknown')})")
        if not client_lines:
            client_lines.append("- No explicit client-tagged issues detected by current heuristics.")
        parts.append(section("Client-side issues/escalations", "(Inference)\n" + "\n".join(client_lines[:10])))

        parts.append(section("Billing snapshot", billing_snapshot(issues)))

        focus_lines = ["- Reduce blocked/stale items.", "- Protect nearest release dates.", "- Resolve data-quality gaps for assignee and billing fields."]
        for action in meeting_actions[:5]:
            focus_lines.append(f"- Meeting action: {action.get('action', 'Unknown action')} (owner: {action.get('owner', 'Unknown')})")
        parts.append(section("Focus for next week", "\n".join(focus_lines)))

    else:
        decision_lines = [f"- {d.get('decision', 'Unknown decision')} (owner: {d.get('owner', 'Unknown')})" for d in meeting_decisions[:6]]
        if not decision_lines:
            decision_lines = ["- Confirm scope freeze or defer list for nearest release.", "- Confirm owner for top delivery risks."]
        parts.append(section("Overall project health", f"(Inference) Current health: **{rag}**."))
        parts.append(section("Timeline and milestones", releases_summary(releases)))
        parts.append(section("Release readiness summary", "- Readiness derived from blockers, stale items, owner coverage, and meeting risks."))
        parts.append(section("Budget/billing snapshot", billing_snapshot(issues)))
        parts.append(section("Decisions required", "\n".join(decision_lines)))
        parts.append(section("Next period priorities", "- Stabilize release-critical scope.\n- Reduce dependency risk."))

    parts.append(section("Data quality issues", data_quality_issues(issues)))
    parts.append(section("Source notes", f"Meetings input items: {len(meeting_records)}; calendar input items: {len(calendar.get('items', [])) if isinstance(calendar.get('items'), list) else 0}; email input items: {len(emails.get('items', [])) if isinstance(emails.get('items'), list) else 0}."))
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

    epic_capacity_issues: list[dict[str, Any]] = []
    if report_type == "weekly":
        epic_jql = (
            f"project = {project_key} AND issuetype = Epic AND status = Closed "
            "AND status CHANGED TO Closed AFTER -90d ORDER BY updated DESC"
        )
        epic_capacity_issues = fetch_issues(base_url, auth_header, epic_jql, field_ids, limit=250)

    return {"issues": issues, "releases": releases, "epic_capacity_issues": epic_capacity_issues}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PM report drafts aligned to REPORT_CONTRACT.md")
    parser.add_argument("--report-type", choices=["daily", "weekly", "steering"], required=True)
    parser.add_argument("--project", default="<project-name>")
    parser.add_argument("--project-key", default="<project-key>")
    parser.add_argument("--live-jira", action="store_true")
    parser.add_argument("--jira", type=Path)
    parser.add_argument("--meetings", type=Path, default=DEFAULT_MEETINGS_PATH)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--emails", type=Path)
    parser.add_argument("--contract", type=Path, default=Path(__file__).resolve().parents[1] / "REPORT_CONTRACT.md")
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
    epic_capacity_issues = jira.get("epic_capacity_issues", []) if isinstance(jira.get("epic_capacity_issues"), list) else []

    report = build_report(
        report_type=args.report_type,
        project_label=args.project,
        issues=issues,
        releases=releases,
        meetings=meetings,
        calendar=calendar,
        emails=emails,
        contract_path=args.contract,
        epic_capacity_issues=epic_capacity_issues,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"OK: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
