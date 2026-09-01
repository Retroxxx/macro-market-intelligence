from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    enabled: bool
    niuone_base_url: str
    data_dir: Path
    api_port: int
    refresh_seconds: int
    timeout_seconds: float


def _positive_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def load_settings() -> Settings:
    raw_enabled = str(os.environ.get("LOCAL_MACRO_ENABLED", "1")).lower()
    return Settings(
        enabled=raw_enabled not in {"0", "false", "no", "off"},
        niuone_base_url=os.environ.get("LOCAL_MACRO_NIUONE_BASE_URL", "http://dashboard:8787").rstrip("/"),
        data_dir=Path(os.environ.get("LOCAL_MACRO_DATA_DIR", ".local-data/local-ext")),
        api_port=_positive_int("LOCAL_MACRO_API_PORT", 8790, 1, 65535),
        refresh_seconds=_positive_int("LOCAL_MACRO_CONTEXT_REFRESH_SECONDS", 60, 15, 3600),
        timeout_seconds=max(1.0, min(30.0, float(os.environ.get("LOCAL_MACRO_TIMEOUT_SECONDS", "5")))),
    )
