"""Bounded connectivity checks for non-model market-data sources."""

from __future__ import annotations

import time
from typing import Any, Mapping

from market_data.fmp_ratings import (
    DEFAULT_BASE_URL as FMP_DEFAULT_BASE_URL,
    FmpRatingsError,
    fetch_latest_grades,
)


FMP_TEST_ID = "fmp-ratings"
FMP_TEST_FIELD_NAMES = frozenset({"FMP_API_BASE_URL", "FMP_API_KEY"})


def data_source_test_metadata() -> list[dict[str, Any]]:
    return [
        {
            "id": FMP_TEST_ID,
            "group_slug": "us-market",
            "label": "Financial Modeling Prep",
            "description": "验证 FMP API Key、套餐权限与最新机构评级接口。",
            "field_names": sorted(FMP_TEST_FIELD_NAMES),
        }
    ]


def data_source_test_override_names(target_id: str) -> set[str]:
    return set(FMP_TEST_FIELD_NAMES) if str(target_id or "").strip() == FMP_TEST_ID else set()


def test_data_source_connection(
    target_id: str,
    values: Mapping[str, Any],
    *,
    timeout: float = 20,
    opener=None,
    monotonic=time.monotonic,
) -> dict[str, Any]:
    target = str(target_id or "").strip()
    if target != FMP_TEST_ID:
        return {"ok": False, "target": "", "error": "不支持的数据源测试目标"}
    base_url = str(values.get("FMP_API_BASE_URL") or FMP_DEFAULT_BASE_URL).strip()
    api_key = str(values.get("FMP_API_KEY") or "").strip()
    if not api_key:
        return {"ok": False, "target": target, "error": "请先配置 FMP API Key"}
    kwargs: dict[str, Any] = {
        "limit": 1,
        "timeout": max(3.0, min(30.0, float(timeout))),
        "max_retries": 0,
    }
    if opener is not None:
        kwargs["opener"] = opener
    started = monotonic()
    try:
        events = fetch_latest_grades(base_url, api_key, **kwargs)
    except FmpRatingsError as exc:
        return {"ok": False, "target": target, "error": str(exc)}
    except Exception as exc:
        return {
            "ok": False,
            "target": target,
            "error": f"FMP 连接测试失败（{type(exc).__name__}）",
        }
    elapsed_ms = max(0, round((monotonic() - started) * 1000))
    return {
        "ok": True,
        "target": target,
        "elapsed_ms": elapsed_ms,
        "record_count": len(events),
        "message": f"FMP 已接通，最新评级接口可用（{elapsed_ms} ms）",
    }
