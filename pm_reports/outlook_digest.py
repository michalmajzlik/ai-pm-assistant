#!/usr/bin/env python3
"""Build Outlook weekly digest for PM reporting."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime_paths import resolve_runtime_dir, resolve_runtime_file

CONFIG_PATH = resolve_runtime_file("m365_config.json")
TOKEN_PATH = resolve_runtime_file("m365_token.json")
DEFAULT_OUTPUT = resolve_runtime_file("cache", "outlook_weekly_digest.json")
RUNTIME_DIR = DEFAULT_OUTPUT.parent.parent
NOISY_SUBJECT_PREFIXES = ("accepted:", "declined:", "tentative:", "canceled:")
ESCALATION_KEYWORDS = {
    "issue",
    "problem",
    "incident",
    "blocking",
    "blocker",
    "delay",
    "urgent",
    "failed",
    "failure",
    "error",
    "escalat",
    "deadline",
}


def load_runtime_config() -> dict[str, Any]:
    data = load_json(CONFIG_PATH)
    return data if isinstance(data, dict) else {}


def load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def oauth_post(url: str, data: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, method="POST", data=encoded, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_config() -> dict[str, str]:
    data = load_runtime_config()
    return {
        "client_id": str(data.get("client_id", "")).strip(),
        "tenant_id": str(data.get("tenant_id", "")).strip(),
        "scopes": str(data.get("scopes", "offline_access openid profile User.Read Mail.Read")).strip(),
    }


def load_token() -> dict[str, Any]:
    return load_json(TOKEN_PATH)


def refresh_token(client_id: str, tenant_id: str, refresh_token_value: str, scopes: str) -> dict[str, Any]:
    base = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0"
    token = oauth_post(
        base + "/token",
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token_value,
            "scope": scopes,
        },
    )
    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600))
    return token


def ensure_access_token() -> str:
    cfg = load_config()
    token = load_token()
    if token.get("access_token") and int(token.get("expires_at", 0)) > int(time.time()) + 120:
        return str(token["access_token"])
    refresh = str(token.get("refresh_token", "")).strip()
    if refresh and cfg["client_id"] and cfg["tenant_id"]:
        new_token = refresh_token(cfg["client_id"], cfg["tenant_id"], refresh, cfg["scopes"])
        save_json(TOKEN_PATH, new_token)
        return str(new_token["access_token"])
    raise RuntimeError("Missing/expired M365 token. Run setup_m365_auth.ps1 first.")


def graph_get(path: str, query: dict[str, Any]) -> dict[str, Any]:
    token = ensure_access_token()
    url = f"https://graph.microsoft.com/v1.0{path}?" + urllib.parse.urlencode(query, doseq=True)
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "ConsistencyLevel": "eventual",
            "Prefer": 'outlook.timezone="Europe/Bratislava"',
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_addresses(items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items or []:
        email = (item or {}).get("emailAddress") or {}
        address = str(email.get("address", "")).strip()
        name = str(email.get("name", "")).strip()
        if address:
            out.append({"name": name, "address": address})
    return out


def message_timestamp(message: dict[str, Any]) -> str:
    return str(message.get("receivedDateTime") or message.get("sentDateTime") or "")


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def default_internal_domains(messages: list[dict[str, Any]]) -> set[str]:
    domains: set[str] = set()
    for message in messages:
        if message.get("folder") != "sentitems":
            continue
        sender = message.get("from") or {}
        address = str(sender.get("address", "")).strip().lower()
        if "@" in address:
            domains.add(address.split("@", 1)[1])
    return domains


def load_internal_domains(messages: list[dict[str, Any]]) -> set[str]:
    config = load_runtime_config()
    domains = config.get("internal_domains", [])
    if isinstance(domains, list):
        normalized = {str(item).strip().lower() for item in domains if str(item).strip()}
        if normalized:
            return normalized
    return default_internal_domains(messages)


def load_excluded_addresses() -> set[str]:
    config = load_runtime_config()
    addresses = config.get("excluded_external_addresses", [])
    if isinstance(addresses, list):
        return {str(item).strip().lower() for item in addresses if str(item).strip()}
    return set()


def is_noise_sender(address: str, excluded_addresses: set[str]) -> bool:
    normalized = address.strip().lower()
    if not normalized:
        return False
    if normalized in excluded_addresses:
        return True
    local_part, _, domain = normalized.partition("@")
    if local_part in {"jira", "noreply", "no-reply", "notification", "notifications"}:
        return True
    if "atlassian.net" in domain and local_part in {"jira", "noreply", "no-reply"}:
        return True
    return False


def is_external(address: str, internal_domains: set[str]) -> bool:
    domain = address.split("@")[-1].lower() if "@" in address else ""
    return bool(domain) and domain not in internal_domains


def fetch_folder_messages(folder: str, dt_field: str, since_iso: str, top: int = 80) -> list[dict[str, Any]]:
    data = graph_get(
        f"/me/mailFolders/{folder}/messages",
        {
            "$top": top,
            "$orderby": f"{dt_field} DESC",
            "$filter": f"{dt_field} ge {since_iso}",
            "$select": "subject,receivedDateTime,sentDateTime,from,toRecipients,ccRecipients,conversationId,bodyPreview,importance,webLink,isRead",
        },
    )
    messages: list[dict[str, Any]] = []
    for item in data.get("value", []):
        frm = ((item.get("from") or {}).get("emailAddress") or {})
        messages.append(
            {
                "folder": folder,
                "subject": item.get("subject") or "(no subject)",
                "receivedDateTime": item.get("receivedDateTime"),
                "sentDateTime": item.get("sentDateTime"),
                "timestamp": message_timestamp(item),
                "from": {"name": frm.get("name"), "address": frm.get("address")},
                "to": normalize_addresses(item.get("toRecipients")),
                "cc": normalize_addresses(item.get("ccRecipients")),
                "conversationId": item.get("conversationId") or "",
                "bodyPreview": item.get("bodyPreview") or "",
                "importance": item.get("importance") or "normal",
                "webLink": item.get("webLink") or "",
                "isRead": bool(item.get("isRead")),
            }
        )
    return messages


def message_keywords(message: dict[str, Any]) -> list[str]:
    haystack = f"{message.get('subject', '')} {message.get('bodyPreview', '')}".lower()
    return sorted(keyword for keyword in ESCALATION_KEYWORDS if keyword in haystack)


def external_participants(message: dict[str, Any], internal_domains: set[str], excluded_addresses: set[str]) -> list[str]:
    participants = []
    for bucket in [message.get("from") or {}, *(message.get("to") or []), *(message.get("cc") or [])]:
        address = str(bucket.get("address", "")).strip().lower()
        if address and is_external(address, internal_domains) and not is_noise_sender(address, excluded_addresses):
            participants.append(address)
    return sorted(set(participants))


def build_escalations(
    messages: list[dict[str, Any]],
    internal_domains: set[str],
    excluded_addresses: set[str],
    limit: int = 3,
) -> list[dict[str, Any]]:
    candidates = []
    for message in messages:
        if message.get("folder") != "inbox":
            continue
        externals = external_participants(message, internal_domains, excluded_addresses)
        sender_addr = str((message.get("from") or {}).get("address", "")).strip().lower()
        if is_noise_sender(sender_addr, excluded_addresses):
            continue
        if not externals:
            continue
        keywords = message_keywords(message)
        high = str(message.get("importance", "")).lower() == "high"
        score = len(keywords) + (2 if high else 0)
        if score <= 0:
            continue
        candidates.append((score, parse_dt(message["timestamp"]), message, keywords, externals, high))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    out = []
    for score, _, message, keywords, externals, high in candidates[:limit]:
        reasons = list(keywords)
        if high:
            reasons.append("high-importance")
        out.append(
            {
                "subject": message.get("subject"),
                "timestamp": message.get("timestamp"),
                "from_name": (message.get("from") or {}).get("name"),
                "from_email": (message.get("from") or {}).get("address"),
                "external_participants": externals,
                "score": score,
                "reasons": reasons,
                "bodyPreview": message.get("bodyPreview"),
                "webLink": message.get("webLink"),
            }
        )
    return out


def build_active_threads(
    messages: list[dict[str, Any]],
    internal_domains: set[str],
    excluded_addresses: set[str],
    limit: int = 3,
) -> list[dict[str, Any]]:
    threads: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in messages:
        if not message.get("conversationId"):
            continue
        if not external_participants(message, internal_domains, excluded_addresses):
            continue
        if str(message.get("subject", "")).strip().lower().startswith(NOISY_SUBJECT_PREFIXES):
            continue
        threads[str(message.get("conversationId"))].append(message)

    ranked = []
    for conversation_id, items in threads.items():
        items.sort(key=lambda entry: parse_dt(entry["timestamp"]))
        if len(items) < 2:
            continue
        participants = sorted({addr for item in items for addr in external_participants(item, internal_domains, excluded_addresses)})
        ranked.append(
            {
                "conversationId": conversation_id,
                "message_count": len(items),
                "last_activity": items[-1]["timestamp"],
                "subject": items[-1].get("subject"),
                "participants": participants,
                "latest_webLink": items[-1].get("webLink"),
            }
        )
    ranked.sort(key=lambda item: (item["message_count"], item["last_activity"]), reverse=True)
    return ranked[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Outlook weekly digest for PM reporting")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        days = max(1, min(args.days, 30))
        since = datetime.now(timezone.utc) - timedelta(days=days)
        since_iso = since.isoformat().replace("+00:00", "Z")

        inbox = fetch_folder_messages("inbox", "receivedDateTime", since_iso)
        sent = fetch_folder_messages("sentitems", "sentDateTime", since_iso)
        all_messages = sorted(inbox + sent, key=lambda item: item["timestamp"], reverse=True)
        internal_domains = load_internal_domains(all_messages)
        excluded_addresses = load_excluded_addresses()

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "window_days": days,
            "runtime_dir": str(RUNTIME_DIR),
            "internal_domains": sorted(internal_domains),
            "email_counts": {
                "inbox": len(inbox),
                "sent": len(sent),
                "total": len(all_messages),
            },
            "escalations": build_escalations(all_messages, internal_domains, excluded_addresses),
            "active_threads": build_active_threads(all_messages, internal_domains, excluded_addresses),
        }
        save_json(args.output, payload)
        print(f"OK: {args.output}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
