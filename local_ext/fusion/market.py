from __future__ import annotations

from typing import Any

from local_ext.adapters.a_stock_data.models import AStockSnapshot
from local_ext.core.models import MarketBreadthSnapshot, NiuOneSnapshot
from local_ext.fusion.quality import choose_value, merge_warnings, provider_quality
from local_ext.fusion.sectors import fuse_sectors


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def _integer(value: Any) -> int | None:
    value = _number(value)
    return int(value) if value is not None else None


def _latest(niuone: NiuOneSnapshot) -> dict[str, Any]:
    value = niuone.breadth.get("latest")
    return value if isinstance(value, dict) else {}


def _pool_count(astock: AStockSnapshot, capability: str) -> int | None:
    result = astock.results.get(capability)
    if not result or result.status not in {"VALID", "VALID_EMPTY"}:
        return None
    return len(result.data) if isinstance(result.data, list) else None


def fuse_snapshot(niuone: NiuOneSnapshot, astock: AStockSnapshot, updated_at: str) -> NiuOneSnapshot:
    latest = _latest(niuone)
    astock_up = _pool_count(astock, "limit_up")
    astock_broken = _pool_count(astock, "broken_limit")
    astock_down = _pool_count(astock, "limit_down")
    yesterday = astock.results.get("yesterday_limit_up")
    yesterday_rows = yesterday.data if yesterday and yesterday.status in {"VALID", "VALID_EMPTY"} and isinstance(yesterday.data, list) else None
    yesterday_positive = sum(1 for row in yesterday_rows or [] if (_number(row.get("pct")) or 0) > 0) if yesterday_rows is not None else None
    yesterday_negative = sum(1 for row in yesterday_rows or [] if (_number(row.get("pct")) or 0) < 0) if yesterday_rows is not None else None
    yesterday_count = len(yesterday_rows) if yesterday_rows is not None else None
    yesterday_success = yesterday_positive / yesterday_count if yesterday_count else None

    breadth_values: dict[str, Any] = {}
    lineage: dict[str, Any] = {}
    warnings: list[str] = []
    for field, official, supplemental in (
        ("advancing", _integer(latest.get("red")), None),
        ("declining", _integer(latest.get("green")), None),
        ("limit_up", _integer(latest.get("limit_up")), astock_up),
        ("limit_down", _integer(latest.get("limit_down")), astock_down),
        ("broken_limit", None, astock_broken),
        ("yesterday_limit_up_count", None, yesterday_count),
        ("yesterday_limit_up_positive", None, yesterday_positive),
        ("yesterday_limit_up_negative", None, yesterday_negative),
        ("yesterday_limit_up_success_rate", None, yesterday_success),
        ("turnover", _number(latest.get("actual_turnover_yi")), None),
        ("turnover_change", _number(latest.get("turnover_change")), None),
    ):
        selected, trace, field_warnings = choose_value(field, official, supplemental, conflict_delta=1.0 if field in {"limit_up", "limit_down"} else None)
        breadth_values[field] = selected
        lineage[field] = trace
        warnings.extend(field_warnings)
    advancing, declining = breadth_values["advancing"], breadth_values["declining"]
    total = (advancing or 0) + (declining or 0)
    breadth_values["flat"] = _integer(latest.get("flat"))
    breadth_values["advance_ratio"] = advancing / total if total and advancing is not None else None
    denominator = (breadth_values["limit_up"] or 0) + (breadth_values["broken_limit"] or 0)
    breadth_values["broken_rate"] = breadth_values["broken_limit"] / denominator if denominator else None
    warnings.extend(merge_warnings(niuone.errors))
    warnings.extend(
        f"stale_cache:{name}"
        for name, endpoint in niuone.provider_health.get("niuone", {}).get("endpoints", {}).items()
        if endpoint.get("stale_cache")
    )
    warnings.extend(merge_warnings(*(result.metadata.warnings for result in astock.results.values() if result.status not in {"VALID", "VALID_EMPTY", "DISABLED"})))
    official_ok = "breadth" not in niuone.errors and bool(latest)
    astock_ok = any(result.status in {"VALID", "VALID_EMPTY"} for result in astock.results.values())
    astock_degraded = any(result.status == "VALID_EMPTY" for result in astock.results.values())
    quality = "GOOD" if official_ok and not warnings and not astock_degraded else "DEGRADED" if official_ok or astock_ok else "FAILED"
    canonical = MarketBreadthSnapshot(
        advancing=breadth_values["advancing"], declining=breadth_values["declining"], flat=breadth_values["flat"],
        advance_ratio=breadth_values["advance_ratio"], limit_up=breadth_values["limit_up"],
        limit_down=breadth_values["limit_down"], broken_limit=breadth_values["broken_limit"],
        broken_rate=breadth_values["broken_rate"], yesterday_limit_up_count=breadth_values["yesterday_limit_up_count"],
        yesterday_limit_up_positive=breadth_values["yesterday_limit_up_positive"],
        yesterday_limit_up_negative=breadth_values["yesterday_limit_up_negative"],
        yesterday_limit_up_success_rate=breadth_values["yesterday_limit_up_success_rate"],
        turnover=breadth_values["turnover"], turnover_change=breadth_values["turnover_change"],
        updated_at=updated_at, sources=tuple(source for source, present in (("niuone", official_ok), ("a_stock_data", astock_ok)) if present),
        quality=quality, warnings=tuple(merge_warnings(warnings)), lineage=lineage,
    )
    astock_statuses = {result.status for result in astock.results.values()}
    astock_health_status = (
        "VALID" if "VALID" in astock_statuses
        else "STALE" if "STALE_DATA" in astock_statuses
        else "VALID_EMPTY" if "VALID_EMPTY" in astock_statuses
        else "DISABLED" if astock_statuses and astock_statuses <= {"DISABLED"}
        else "FAILED" if astock_statuses else "DISABLED"
    )
    official_health = niuone.provider_health.get("niuone", {})
    health = {
        "niuone": {
            "enabled": True,
            "status": "FAILED" if niuone.errors else official_health.get("status", "VALID"),
            "errors": dict(niuone.errors),
            "endpoints": official_health.get("endpoints", {}),
        },
        "a_stock_data": {
            "enabled": bool(astock_statuses - {"DISABLED"}),
            "status": astock_health_status,
            "capabilities": {name: {"status": r.status, "quality": provider_quality(r.status), "error": r.error, "retrieved_at": r.metadata.retrieved_at, "freshness_seconds": r.metadata.freshness_seconds} for name, r in astock.results.items()},
        },
    }
    errors = dict(niuone.errors)
    errors.update({f"a_stock_data.{name}": result.error or result.status for name, result in astock.results.items() if result.status not in {"VALID", "VALID_EMPTY", "DISABLED"}})
    return NiuOneSnapshot(
        indices=niuone.indices, breadth=niuone.breadth, sectors=niuone.sectors, money_flow=niuone.money_flow,
        errors=errors, canonical_breadth=canonical, canonical_sectors=fuse_sectors(niuone, astock, updated_at),
        market_internals={
            "broken_limit_rate": breadth_values["broken_rate"],
            "yesterday_limit_up_continuation": breadth_values["yesterday_limit_up_success_rate"],
            "limit_up_down_imbalance": (breadth_values["limit_up"] / breadth_values["limit_down"] if breadth_values["limit_up"] is not None and breadth_values["limit_down"] else None),
            "limit_pools": {name: (result.data if result else None) for name, result in astock.results.items() if name in {"limit_up", "broken_limit", "limit_down", "yesterday_limit_up"}},
        },
        provider_health=health,
        source_versions={"niuone": "public-api", "a_stock_data": "3.7.2@3a599d09dfa5f15c6e171e96febdb693664455e6", "fusion": "fusion-v1"},
    )
