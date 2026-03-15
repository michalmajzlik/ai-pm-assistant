from __future__ import annotations

import os
from pathlib import Path

PRIMARY_RUNTIME_DIRNAME = "AIPMAssistant"
LEGACY_RUNTIME_DIRNAME = "SensoneoAI"


def appdata_dir() -> Path:
    return Path(os.getenv("APPDATA", ""))


def primary_runtime_dir() -> Path:
    return appdata_dir() / PRIMARY_RUNTIME_DIRNAME


def legacy_runtime_dir() -> Path:
    return appdata_dir() / LEGACY_RUNTIME_DIRNAME


def resolve_runtime_dir() -> Path:
    primary = primary_runtime_dir()
    legacy = legacy_runtime_dir()
    if primary.exists():
        return primary
    if legacy.exists():
        return legacy
    return primary


def resolve_runtime_file(*parts: str) -> Path:
    relative = Path(*parts)
    primary = primary_runtime_dir() / relative
    legacy = legacy_runtime_dir() / relative
    if primary.exists() and legacy.exists():
        return primary if primary.stat().st_mtime >= legacy.stat().st_mtime else legacy
    if primary.exists():
        return primary
    if legacy.exists():
        return legacy
    return primary
