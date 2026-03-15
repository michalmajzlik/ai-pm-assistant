#!/usr/bin/env python3
"""Publish generated reports into Jira issues."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from project_config import get_publish_settings, load_project_config
from runtime_paths import resolve_runtime_file

DEFAULT_PROJECT_CONFIG_PATH = resolve_runtime_file("project_report_config.json")
DEFAULT_PROJECT_STATUS_FIELD_MAPPING = {
    "rag_overall": "customfield_10272",
    "rag_timeline": "customfield_10273",
    "rag_scope": "customfield_10274",
    "rag_budget": "customfield_10275",
    "current_project_status": "customfield_10276",
    "project_next_steps": "customfield_10277",
}


def get_auth_context() -> tuple[str, str]:
    base_url = os.getenv("JIRA_BASE_URL", "").strip()
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    if not base_url or not email or not token:
        raise RuntimeError("Missing JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN environment variables.")

    raw = f"{email}:{token}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(raw).decode("ascii")
    return base_url.rstrip("/"), auth_header


def jira_request(base_url: str, auth_header: str, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read()
        if not body:
            return None
        return json.loads(body.decode("utf-8"))


def text_node(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def paragraph_node(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [text_node(text)]}


def heading_node(level: int, text: str) -> dict[str, Any]:
    return {"type": "heading", "attrs": {"level": level}, "content": [text_node(text)]}


def bullet_list_node(items: list[str]) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [{"type": "paragraph", "content": [text_node(item)]}],
            }
            for item in items
        ],
    }


def markdown_to_adf(markdown: str) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    bullet_buffer: list[str] = []

    def flush_bullets() -> None:
        nonlocal bullet_buffer
        if bullet_buffer:
            blocks.append(bullet_list_node(bullet_buffer))
            bullet_buffer = []

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            flush_bullets()
            continue

        bullet_match = re.match(r"^-\s+(.*)$", stripped)
        if bullet_match:
            bullet_buffer.append(bullet_match.group(1).strip())
            continue

        flush_bullets()
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            level = min(len(heading_match.group(1)), 6)
            blocks.append(heading_node(level, heading_match.group(2).strip()))
            continue

        blocks.append(paragraph_node(stripped))

    flush_bullets()
    return {"version": 1, "type": "doc", "content": blocks}


def split_markdown_sections(markdown: str) -> tuple[list[str], dict[str, str]]:
    lines = markdown.splitlines()
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in lines:
        heading_match = re.match(r"^##\s+(.*)$", line.strip())
        if heading_match:
            current = heading_match.group(1).strip()
            sections[current] = []
            continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)

    return preamble, {name: "\n".join(body).strip() for name, body in sections.items()}


def extract_project_label(preamble: list[str]) -> str:
    for line in preamble:
        match = re.match(r"^Project:\s*(.*)$", line.strip())
        if match:
            return match.group(1).strip()
    return ""


def extract_rag_values(key_details_body: str) -> dict[str, str]:
    rag_values: dict[str, str] = {}
    lines = [line.strip() for line in key_details_body.splitlines() if line.strip()]
    for line in lines:
        match = re.match(r"^- RAG Status - ([^:]+):\s*(.+)$", line)
        if match:
            label = match.group(1).strip().lower().replace(" ", "_")
            rag_values[label] = match.group(2).strip()
    return rag_values


def build_project_status_markdown(sections: dict[str, str]) -> str:
    ordered = [
        ("Key details", sections.get("Key details", "")),
        ("Current Project Status", sections.get("Current Project Status", "")),
        ("Client signal", sections.get("Client signal", "")),
        ("Source notes", sections.get("Source notes", "")),
    ]
    chunks: list[str] = []
    for title, body in ordered:
        if not body:
            continue
        chunks.append(f"## {title}\n{body.strip()}")
    return "\n\n".join(chunks).strip()


def get_editmeta(base_url: str, auth_header: str, issue_key: str) -> dict[str, Any]:
    payload = jira_request(base_url, auth_header, f"/rest/api/3/issue/{issue_key}/editmeta")
    return payload if isinstance(payload, dict) else {}


def option_id_for_value(editmeta: dict[str, Any], field_id: str, wanted_value: str) -> str:
    fields = editmeta.get("fields", {}) if isinstance(editmeta, dict) else {}
    field_meta = fields.get(field_id, {}) if isinstance(fields, dict) else {}
    allowed = field_meta.get("allowedValues", []) if isinstance(field_meta, dict) else []
    for option in allowed:
        if str(option.get("value", "")).strip().lower() == wanted_value.strip().lower():
            return str(option.get("id", ""))
    raise KeyError(f"Option '{wanted_value}' not found for field {field_id}")


def update_issue_fields(base_url: str, auth_header: str, issue_key: str, fields_payload: dict[str, Any]) -> None:
    jira_request(
        base_url,
        auth_header,
        f"/rest/api/3/issue/{issue_key}",
        method="PUT",
        payload={"fields": fields_payload},
    )


def publish_description_mode(base_url: str, auth_header: str, issue_key: str, report_text: str) -> None:
    update_issue_fields(
        base_url,
        auth_header,
        issue_key,
        {"description": markdown_to_adf(report_text)},
    )


def publish_project_status_fields(
    base_url: str,
    auth_header: str,
    issue_key: str,
    report_text: str,
    field_mapping: dict[str, str],
) -> None:
    preamble, sections = split_markdown_sections(report_text)
    key_details = sections.get("Key details", "")
    next_steps = sections.get("Project Next Steps", "")
    if not key_details:
        raise SystemExit("Weekly report is missing 'Key details' section.")
    if not next_steps:
        raise SystemExit("Weekly report is missing 'Project Next Steps' section.")

    project_label = extract_project_label(preamble)
    rag_values = extract_rag_values(key_details)
    current_project_status_markdown = build_project_status_markdown(sections)
    editmeta = get_editmeta(base_url, auth_header, issue_key)

    overall_field = field_mapping["rag_overall"]
    timeline_field = field_mapping["rag_timeline"]
    scope_field = field_mapping["rag_scope"]
    budget_field = field_mapping["rag_budget"]
    current_status_field = field_mapping["current_project_status"]
    next_steps_field = field_mapping["project_next_steps"]

    overall_value = rag_values.get("overall")
    timeline_value = rag_values.get("timeline")
    scope_value = rag_values.get("scope")
    budget_value = rag_values.get("budget")
    if not all([overall_value, timeline_value, scope_value, budget_value]):
        raise SystemExit("Could not parse all RAG values from the weekly report.")

    fields_payload: dict[str, Any] = {
        overall_field: {"id": option_id_for_value(editmeta, overall_field, overall_value)},
        timeline_field: {"id": option_id_for_value(editmeta, timeline_field, timeline_value)},
        scope_field: {"id": option_id_for_value(editmeta, scope_field, scope_value)},
        budget_field: {"id": option_id_for_value(editmeta, budget_field, budget_value)},
        current_status_field: markdown_to_adf(current_project_status_markdown),
        next_steps_field: markdown_to_adf(next_steps),
    }

    if project_label:
        fields_payload["summary"] = f"{project_label} - project status"

    update_issue_fields(base_url, auth_header, issue_key, fields_payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a generated PM report to a Jira issue.")
    parser.add_argument("--report-type", required=True, choices=["daily", "weekly", "steering"])
    parser.add_argument("--report-file", type=Path, required=True)
    parser.add_argument("--project-config", type=Path, default=DEFAULT_PROJECT_CONFIG_PATH)
    parser.add_argument("--issue-key", default="")
    args = parser.parse_args()

    report_text = args.report_file.read_text(encoding="utf-8")
    config = load_project_config(args.project_config)
    publish_settings = get_publish_settings(config, args.report_type)

    issue_key = (args.issue_key or str(publish_settings.get("jira_issue_key") or "")).strip()
    enabled = bool(publish_settings.get("enabled")) or bool(args.issue_key)
    mode = str(publish_settings.get("mode") or "overwrite_description").strip()

    if not enabled:
        print(f"SKIP: publishing disabled for {args.report_type}")
        return 0
    if not issue_key:
        raise SystemExit(f"Missing jira_issue_key for {args.report_type} publishing.")

    base_url, auth_header = get_auth_context()
    try:
        if mode == "overwrite_description":
            publish_description_mode(base_url, auth_header, issue_key, report_text)
        elif mode == "project_status_fields":
            custom_mapping = publish_settings.get("field_mapping", {})
            field_mapping = dict(DEFAULT_PROJECT_STATUS_FIELD_MAPPING)
            if isinstance(custom_mapping, dict):
                field_mapping.update({str(k): str(v) for k, v in custom_mapping.items() if v})
            publish_project_status_fields(base_url, auth_header, issue_key, report_text, field_mapping)
        else:
            raise SystemExit(f"Unsupported publish mode: {mode}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Failed to update Jira issue {issue_key}: HTTP {exc.code} {body}") from exc

    print(f"OK: updated Jira issue {issue_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
