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
    a_stock_data_enabled: bool
    a_stock_data_base_url: str
    a_stock_data_pool_base_url: str
    a_stock_data_retries: int
    a_stock_data_min_interval_seconds: float


def _positive_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def load_settings() -> Settings:
    raw_enabled = str(os.environ.get("LOCAL_MACRO_ENABLED", "1")).lower()
    raw_astock_enabled = str(os.environ.get("LOCAL_MACRO_A_STOCK_ENABLED", "0")).lower()
    return Settings(
        enabled=raw_enabled not in {"0", "false", "no", "off"},
        niuone_base_url=os.environ.get("LOCAL_MACRO_NIUONE_BASE_URL", "http://dashboard:8787").rstrip("/"),
        data_dir=Path(os.environ.get("LOCAL_MACRO_DATA_DIR", ".local-data/local-ext")),
        api_port=_positive_int("LOCAL_MACRO_API_PORT", 8790, 1, 65535),
        refresh_seconds=_positive_int("LOCAL_MACRO_CONTEXT_REFRESH_SECONDS", 60, 15, 3600),
        timeout_seconds=_bounded_float("LOCAL_MACRO_TIMEOUT_SECONDS", 5.0, 1.0, 30.0),
        a_stock_data_enabled=raw_astock_enabled not in {"0", "false", "no", "off"},
        a_stock_data_base_url=os.environ.get("LOCAL_MACRO_A_STOCK_BASE_URL", "https://push2.eastmoney.com").rstrip("/"),
        a_stock_data_pool_base_url=os.environ.get("LOCAL_MACRO_A_STOCK_POOL_BASE_URL", "https://push2ex.eastmoney.com").rstrip("/"),
        a_stock_data_retries=_positive_int("LOCAL_MACRO_A_STOCK_RETRIES", 1, 0, 2),
        a_stock_data_min_interval_seconds=_bounded_float("LOCAL_MACRO_A_STOCK_MIN_INTERVAL_SECONDS", 1.0, 0.0, 10.0),
    )
