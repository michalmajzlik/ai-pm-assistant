from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULT_WEEKLY_STATUS_SECTIONS = [
    {
        "name": "Delivery",
        "kind": "delivery_support",
        "keywords": ["release", "migration", "integration", "support", "incident"],
        "business_impact": "Business impact: delivery quality is mainly driven by how well support interruptions are contained against planned work.",
        "include_top_risk": True,
    },
    {
        "name": "Scope and estimation",
        "kind": "scope_estimation",
        "scope_keywords": ["story", "feature", "enhancement", "integration", "report", "backlog", "refinement"],
        "coordination_keywords": ["pmo", "client meeting", "internal project meetings", "refinement"],
        "scope_line_template": "Scope shaping remains active, with {count} relevant items currently in backlog/preparation; this keeps the pipeline full, but part of near-term scope is still being refined rather than executed.",
        "scope_stable_line": "Scope is moving without a clear signal of uncontrolled expansion in the current weekly window.",
        "coordination_line_template": "Coordination overhead remains visible in project-management and client-facing work, with ongoing items such as {issue}.",
    },
    {
        "name": "Budget",
        "kind": "budget",
        "forward_risk": "Forward-looking risk: until billing fields become reliable, budget control can only be assessed partially and should be treated with caution.",
    },
]

DEFAULT_PROJECT_CONFIG = {
    "schema_version": 1,
    "profile": "software_delivery",
    "project": {
        "name": "<project-name>",
        "key": "<project-key>",
        "display_name": "<project-display-name>",
    },
    "reports": {
        "daily": {
            "header_style": "standard",
            "title": "Daily Report",
            "project_label": "Project",
            "section_titles": {
                "yesterday_completed": "Yesterday completed",
                "today_plan": "Today plan",
                "blockers_and_risks": "Blockers and risks",
                "release_status": "Release status",
                "client_actions_needed": "Client actions needed",
                "data_quality_issues": "Data quality issues",
                "source_notes": "Source notes",
            },
        },
        "weekly": {
            "header_style": "compact",
            "title": "Weekly Report",
            "project_label": "Project",
            "section_titles": {
                "key_details": "Key details",
                "current_project_status": "Current Project Status",
                "project_next_steps": "Project Next Steps",
                "client_signal": "Client signal",
                "data_quality_issues": "Data quality issues",
                "source_notes": "Source notes",
            },
            "status_sections": copy.deepcopy(DEFAULT_WEEKLY_STATUS_SECTIONS),
        },
        "steering": {
            "header_style": "standard",
            "title": "Steering Report",
            "project_label": "Project",
            "section_titles": {
                "overall_project_health": "Overall project health",
                "timeline_and_milestones": "Timeline and milestones",
                "release_readiness_summary": "Release readiness summary",
                "budget_billing_snapshot": "Budget/billing snapshot",
                "decisions_required": "Decisions required",
                "next_period_priorities": "Next period priorities",
                "data_quality_issues": "Data quality issues",
                "source_notes": "Source notes",
            },
        },
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_project_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open('r', encoding='utf-8-sig') as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def get_project_value(config: dict[str, Any], key: str, default: str = '') -> str:
    project = config.get('project', {}) if isinstance(config, dict) else {}
    value = project.get(key, default) if isinstance(project, dict) else default
    return str(value or default)


def get_report_settings(config: dict[str, Any], report_type: str) -> dict[str, Any]:
    base = DEFAULT_PROJECT_CONFIG['reports'].get(report_type, {})
    override = {}
    if isinstance(config, dict):
        reports = config.get('reports', {})
        if isinstance(reports, dict):
            override = reports.get(report_type, {}) if isinstance(reports.get(report_type, {}), dict) else {}
    return deep_merge(base, override)


def get_section_title(report_settings: dict[str, Any], key: str, default: str) -> str:
    titles = report_settings.get('section_titles', {}) if isinstance(report_settings, dict) else {}
    if isinstance(titles, dict):
        value = titles.get(key)
        if value:
            return str(value)
    return default


def get_weekly_status_sections(report_settings: dict[str, Any]) -> list[dict[str, Any]]:
    sections = report_settings.get('status_sections', []) if isinstance(report_settings, dict) else []
    if isinstance(sections, list) and sections:
        return sections
    return copy.deepcopy(DEFAULT_WEEKLY_STATUS_SECTIONS)
