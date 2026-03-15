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

from project_config import (
    get_project_value,
    get_report_settings,
    get_section_title,
    get_weekly_status_sections,
    load_project_config,
)

DEFAULT_MEETINGS_PATH = Path(__file__).resolve().parents[1] / "Meetings" / "records"
DEFAULT_PROJECT_CONFIG_PATH = Path(os.getenv("APPDATA", "")) / "SensoneoAI" / "project_report_config.json"


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


def rag_status_line(label: str, value: str, rationale: str) -> str:
    return f"- RAG Status - {label}: {value}\n- Rationale: {rationale}"


def infer_timeline_rag(issues: list[dict[str, Any]], releases: list[dict[str, Any]], meeting_risks: list[dict[str, Any]]) -> tuple[str, str]:
    blocked = [i for i in issues if "block" in str(i.get("status", "")).lower()]
    near_releases = [r for r in releases if not r.get("released") and not r.get("archived")]
    timeline_risk = any("release" in str(r.get("risk", "")).lower() or "migration" in str(r.get("risk", "")).lower() for r in meeting_risks)
    if len(blocked) >= 2 or timeline_risk:
        return "Amber", "Cross-system support topics and release-related risks exist, but no clear milestone miss is confirmed."
    if near_releases:
        return "Green", "Planned releases exist in Jira and current evidence does not show an immediate timeline breach."
    return "Green", "No active timeline warning was detected in the current data window."


def infer_scope_rag(issues: list[dict[str, Any]], meeting_actions: list[dict[str, Any]], meeting_decisions: list[dict[str, Any]]) -> tuple[str, str]:
    backlog = [i for i in issues if str(i.get("status", "")).lower() in {"backlog", "info needed", "selected for development", "in preparation"}]
    scope_changes = sum(
        1
        for item in meeting_actions + meeting_decisions
        if any(token in str(item.get("action", item.get("decision", ""))).lower() for token in ["scope", "descoped", "technical debt", "backlog"])
    )
    if len(backlog) >= 20 or scope_changes >= 2:
        return "Amber", "Scope remains manageable, but backlog cleanup and technical-work visibility indicate continuing scope shaping."
    return "Green", "No major uncontrolled scope growth is visible in the current Jira and meeting inputs."


def infer_budget_rag(issues: list[dict[str, Any]], epic_capacity_issues: list[dict[str, Any]]) -> tuple[str, str]:
    chargeable = [i for i in issues if i.get("chargeable")]
    if not chargeable:
        return "Amber", "Budget signal is limited because live Jira currently returns no reliable chargeable effort in scope."
    overburn = [
        i for i in epic_capacity_issues
        if as_float(i.get("planned_md")) > 0 and (as_float(i.get("consumed_md")) / as_float(i.get("planned_md")) * 100.0) > 115.0
    ]
    if len(overburn) >= 3:
        return "Amber", "Several recently closed epics materially exceeded plan, so budget efficiency should be watched more closely."
    return "Green", "Current available effort data does not indicate a major budget-control issue."


def active_releases_headline(releases: list[dict[str, Any]], limit: int = 3, keywords: list[str] | None = None) -> str:
    active = [r for r in releases if not r.get("released") and not r.get("archived")]
    if keywords:
        lowered = [k.lower() for k in keywords]
        active = [r for r in active if any(k in str(r.get("name", "")).lower() for k in lowered)]
    if not active:
        return "No active Jira releases are currently listed."
    named = []
    for release in sorted(active, key=lambda x: str(x.get("releaseDate") or "9999-12-31"))[:limit]:
        release_date = release.get("releaseDate") or "date not set"
        named.append(f"{release.get('name', 'Unknown')} ({release_date})")
    return "Active Jira releases: " + ", ".join(named) + "."


def capacity_headline(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No recent closed-epic MD history is available for capacity benchmarking."
    planned_total = sum(as_float(i.get("planned_md")) for i in issues)
    consumed_total = sum(as_float(i.get("consumed_md")) for i in issues)
    burn_total = (consumed_total / planned_total * 100.0) if planned_total > 0 else 0.0
    return f"Closed-epic burn over the last 90 days is {burn_total:.1f}% ({consumed_total:.1f} MD consumed vs {planned_total:.1f} MD planned)."


def billing_headline(issues: list[dict[str, Any]]) -> str:
    chargeable = [i for i in issues if i.get("chargeable")]
    if not chargeable:
        return "Billing signal remains weak because no chargeable issues with reliable actual spent data were found in the current Jira scope."
    actual_total = sum(as_float(i.get("actual_spent")) for i in chargeable)
    missing = sum(1 for i in chargeable if as_float(i.get("actual_spent")) <= 0)
    return f"Chargeable Jira scope covers {len(chargeable)} issues with {actual_total:.1f} hours logged; {missing} items still miss usable actual spent data."


def issues_with_keywords(issues: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    if not keywords:
        return []
    lowered = [keyword.lower() for keyword in keywords]
    matches: list[dict[str, Any]] = []
    for issue in issues:
        summary = str(issue.get("summary", "")).lower()
        if any(keyword in summary for keyword in lowered):
            matches.append(issue)
    return matches


def format_issue_change(issue: dict[str, Any]) -> str:
    return f"{issue.get('key', '?')} ({issue.get('status', 'Unknown')}): {issue.get('summary', 'Unknown summary')}"


def prep_scope_count(issues: list[dict[str, Any]]) -> int:
    prep_statuses = {"in preparation", "backlog", "selected for development"}
    return sum(1 for issue in issues if str(issue.get("status", "")).lower() in prep_statuses)


def render_client_signal(emails: dict[str, Any]) -> list[str]:
    if not isinstance(emails, dict):
        return []
    lines: list[str] = []
    escalations = emails.get("escalations", []) if isinstance(emails.get("escalations"), list) else []
    active_threads = emails.get("active_threads", []) if isinstance(emails.get("active_threads"), list) else []

    for item in escalations[:3]:
        subject = item.get("subject", "(no subject)")
        sender = item.get("from_name") or item.get("from_email") or "Unknown sender"
        reasons = ", ".join(item.get("reasons", [])) if isinstance(item.get("reasons"), list) else "signal detected"
        lines.append(f"- Escalation: {subject} | from {sender} | signal: {reasons}")

    for item in active_threads[:3]:
        if item.get("message_count", 0) < 2:
            continue
        participants = ", ".join(item.get("participants", [])[:3]) if isinstance(item.get("participants"), list) else "external participants"
        lines.append(
            f"- Active thread: {item.get('subject', '(no subject)')} | {item.get('message_count', 0)} messages this week | participants: {participants}"
        )

    return lines


def render_weekly_status_section(
    section_cfg: dict[str, Any],
    issues: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    meeting_risks: list[dict[str, Any]],
    epic_capacity_issues: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    name = str(section_cfg.get("name") or "Status")
    kind = str(section_cfg.get("kind") or "delivery_support")

    if kind == "delivery_support":
        matches = issues_with_keywords(issues, list(section_cfg.get("keywords", [])))
        lines: list[str] = []
        if matches:
            lines.append(
                f"- This week {name} work stayed split between planned delivery and production-facing support; latest live items include {format_issue_change(matches[0])}."
            )
        else:
            lines.append(str(section_cfg.get("empty_line") or f"- This week {name} remained stable, with no major new delivery disruption visible in Jira."))
        lines.append(str(section_cfg.get("business_impact") or "- Business impact: support interruptions are still competing with planned feature delivery."))
        if section_cfg.get("include_top_risk") and meeting_risks:
            top_risk = meeting_risks[0]
            lines.append(
                f"- Main cross-team risk raised this week: {top_risk.get('risk', 'Unknown risk')} (impact: {top_risk.get('impact', 'Unknown')})."
            )
        return name, lines

    if kind == "release_delivery":
        lines = [str(section_cfg.get("sentiment_line") or f"- {name} delivery remained stable in the current reporting window.")]
        release_keywords = list(section_cfg.get("release_keywords", []))
        lines.append(f"- Delivery path: {active_releases_headline(releases, keywords=release_keywords or list(section_cfg.get('keywords', [])))}")
        return name, lines

    if kind == "scope_estimation":
        scope_keywords = list(section_cfg.get("scope_keywords", []))
        coordination_keywords = list(section_cfg.get("coordination_keywords", []))
        scope_focus = issues_with_keywords(issues, scope_keywords)
        coordination_focus = issues_with_keywords(issues, coordination_keywords)
        count = prep_scope_count(scope_focus)
        lines = []
        if count:
            template = str(section_cfg.get("scope_line_template") or "Scope shaping remains active, with {count} relevant items currently in backlog/preparation.")
            lines.append(f"- {template.format(count=count)}")
        else:
            lines.append(f"- {section_cfg.get('scope_stable_line') or 'Scope is moving without a clear signal of uncontrolled expansion in the current weekly window.'}")
        if coordination_focus:
            template = str(section_cfg.get("coordination_line_template") or "Coordination overhead remains visible, with ongoing items such as {issue}.")
            lines.append(f"- {template.format(issue=format_issue_change(coordination_focus[0]))}")
        return name, lines

    if kind == "budget":
        lines = [
            f"- Capacity signal: {capacity_headline(epic_capacity_issues)}",
            f"- Commercial signal: {billing_headline(issues)}",
            f"- {section_cfg.get('forward_risk') or 'Forward-looking risk: budget control should be treated with caution while billing evidence remains incomplete.'}",
        ]
        return name, lines

    fallback = str(section_cfg.get("fallback_line") or f"- No renderer is configured for section kind '{kind}'.")
    return name, [fallback]


def build_report(
    report_type: str,
    project_label: str,
    issues: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    meetings: dict[str, Any],
    calendar: dict[str, Any],
    emails: dict[str, Any],
    contract_path: Path,
    report_config: dict[str, Any],
    epic_capacity_issues: list[dict[str, Any]] | None = None,
) -> str:
    rag = infer_rag(issues)
    now = date.today().isoformat()
    meeting_records = meetings.get("items", []) if isinstance(meetings.get("items"), list) else []
    recent_meetings = filter_meetings_for_window(meeting_records, report_type)
    meeting_actions = flatten_meeting_items(recent_meetings, "action_items")
    meeting_risks = flatten_meeting_items(recent_meetings, "risks")
    meeting_decisions = flatten_meeting_items(recent_meetings, "decisions")
    report_settings = get_report_settings(report_config, report_type)

    header_style = str(report_settings.get("header_style") or "standard")
    title = str(report_settings.get("title") or f"{report_type.title()} Report")
    project_label_key = str(report_settings.get("project_label") or "Project")

    if header_style == "compact":
        parts = [
            f"# {title}",
            f"Date: {now}",
            f"{project_label_key}: {project_label}",
            "",
        ]
    else:
        parts = [
            f"# {title} - {project_label}",
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
        parts.append(section(get_section_title(report_settings, "yesterday_completed", "Yesterday completed"), "\n".join(yesterday_lines)))

        today_lines = [f"- {i.get('key')}: {i.get('summary')} ({i.get('status')})" for i in active_today[:8]]
        open_actions = [a for a in meeting_actions if str(a.get("status", "Open")).lower() != "done"]
        for item in open_actions[:5]:
            today_lines.append(f"- Meeting follow-up: {item.get('action', 'Unknown action')} (owner: {item.get('owner', 'Unknown')})")
        if not today_lines:
            today_lines = ["- No active tickets in provided daily scope."]
        parts.append(section(get_section_title(report_settings, "today_plan", "Today plan"), "\n".join(today_lines)))

        risk_lines = [f"- {b.get('key')}: {b.get('summary')} ({b.get('status')})" for b in blockers]
        for risk in meeting_risks[:6]:
            risk_lines.append(f"- Meeting risk: {risk.get('risk', 'Unknown')} (impact: {risk.get('impact', 'Unknown')}, owner: {risk.get('owner', 'Unknown')})")
        if not risk_lines:
            risk_lines = ["- No explicit blocked status or meeting risk found in scope."]
        parts.append(section(get_section_title(report_settings, "blockers_and_risks", "Blockers and risks"), "(Inference)\n" + "\n".join(risk_lines)))
        parts.append(section(get_section_title(report_settings, "release_status", "Release status"), releases_summary(releases)))

        actions = []
        unassigned = [i for i in issues if not i.get("assignee")]
        if blockers:
            actions.append("- Confirm ownership and unblock plan for blocked items.")
        if unassigned:
            actions.append(f"- Assign owners for unassigned items: {', '.join(i.get('key', '?') for i in unassigned[:8])}.")
        if not actions:
            actions.append("- No explicit client action required from current data window.")
        parts.append(section(get_section_title(report_settings, "client_actions_needed", "Client actions needed"), "\n".join(actions)))

    elif report_type == "weekly":
        timeline_rag, timeline_rationale = infer_timeline_rag(issues, releases, meeting_risks)
        scope_rag, scope_rationale = infer_scope_rag(issues, meeting_actions, meeting_decisions)
        budget_rag, budget_rationale = infer_budget_rag(issues, epic_capacity_issues if epic_capacity_issues is not None else [])

        parts.append(section(get_section_title(report_settings, "key_details", "Key details"), "\n".join([
            rag_status_line("Overall", rag, "Overall health is Amber because delivery is under control, but support and data-consistency load are materially consuming attention."),
            rag_status_line("Timeline", timeline_rag, timeline_rationale),
            rag_status_line("Scope", scope_rag, scope_rationale),
            rag_status_line("Budget", budget_rag, budget_rationale),
        ])))

        status_lines: list[str] = []
        for section_cfg in get_weekly_status_sections(report_settings):
            section_name, lines = render_weekly_status_section(
                section_cfg=section_cfg,
                issues=issues,
                releases=releases,
                meeting_risks=meeting_risks,
                epic_capacity_issues=epic_capacity_issues if epic_capacity_issues is not None else [],
            )
            status_lines.extend([section_name, "", *lines, ""])
        parts.append(section(get_section_title(report_settings, "current_project_status", "Current Project Status"), "\n".join(status_lines).strip()))

        client_signal_lines = render_client_signal(emails)
        if client_signal_lines:
            parts.append(section(get_section_title(report_settings, "client_signal", "Client signal"), "\n".join(client_signal_lines)))

        next_step_lines = []
        for action in meeting_actions[:5]:
            next_step_lines.append(f"- {action.get('action', 'Unknown action')} (owner: {action.get('owner', 'Unknown')})")
        if not next_step_lines:
            next_step_lines = [
                "- Reduce blocked and stale items.",
                "- Protect nearest release dates.",
                "- Resolve data-quality gaps for assignee and billing fields.",
            ]
        parts.append(section(get_section_title(report_settings, "project_next_steps", "Project Next Steps"), "\n".join(next_step_lines)))

    else:
        decision_lines = [f"- {d.get('decision', 'Unknown decision')} (owner: {d.get('owner', 'Unknown')})" for d in meeting_decisions[:6]]
        if not decision_lines:
            decision_lines = ["- Confirm scope freeze or defer list for nearest release.", "- Confirm owner for top delivery risks."]
        parts.append(section(get_section_title(report_settings, "overall_project_health", "Overall project health"), f"(Inference) Current health: **{rag}**."))
        parts.append(section(get_section_title(report_settings, "timeline_and_milestones", "Timeline and milestones"), releases_summary(releases)))
        parts.append(section(get_section_title(report_settings, "release_readiness_summary", "Release readiness summary"), "- Readiness derived from blockers, stale items, owner coverage, and meeting risks."))
        parts.append(section(get_section_title(report_settings, "budget_billing_snapshot", "Budget/billing snapshot"), billing_snapshot(issues)))
        parts.append(section(get_section_title(report_settings, "decisions_required", "Decisions required"), "\n".join(decision_lines)))
        parts.append(section(get_section_title(report_settings, "next_period_priorities", "Next period priorities"), "- Stabilize release-critical scope.\n- Reduce dependency risk."))

    parts.append(section(get_section_title(report_settings, "data_quality_issues", "Data quality issues"), data_quality_issues(issues)))
    email_count = 0
    if isinstance(emails.get("items"), list):
        email_count = len(emails.get("items", []))
    elif isinstance(emails.get("email_counts"), dict):
        email_count = int(emails.get("email_counts", {}).get("total", 0))
    parts.append(section(get_section_title(report_settings, "source_notes", "Source notes"), f"Meetings input items: {len(meeting_records)}; calendar input items: {len(calendar.get('items', [])) if isinstance(calendar.get('items'), list) else 0}; email input items: {email_count}."))
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
    parser.add_argument("--project", default="")
    parser.add_argument("--project-key", default="")
    parser.add_argument("--project-config", type=Path, default=DEFAULT_PROJECT_CONFIG_PATH)
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

    project_config = load_project_config(args.project_config)
    project_label = args.project or get_project_value(project_config, "display_name") or get_project_value(project_config, "name")
    project_key = args.project_key or get_project_value(project_config, "key")

    if not project_label or not project_key:
        raise SystemExit("Missing project context. Provide --project/--project-key or configure --project-config.")

    if args.live_jira:
        jira = live_jira_dataset(args.report_type, project_key)
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
        project_label=project_label,
        issues=issues,
        releases=releases,
        meetings=meetings,
        calendar=calendar,
        emails=emails,
        contract_path=args.contract,
        report_config=project_config,
        epic_capacity_issues=epic_capacity_issues,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"OK: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
