from __future__ import annotations

from datetime import datetime
from typing import Any

from local_ext.adapters.a_stock_data.provider import AStockDataAdapter
from local_ext.adapters.niuone import NiuOneAdapter
from local_ext.core.models import CONTEXT_VERSION, MarketContext
from local_ext.core.time import iso, now
from local_ext.fusion.market import fuse_snapshot
from local_ext.macro.regime.rules import evaluate as evaluate_regime
from local_ext.macro.sector_rotation.rules import evaluate as evaluate_sectors
from local_ext.macro.style.rules import evaluate as evaluate_styles


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _market_status(moment: datetime) -> str:
    minute = moment.hour * 60 + moment.minute
    open_session = moment.weekday() < 5 and (570 <= minute <= 690 or 780 <= minute <= 900)
    return "OPEN" if open_session else "CLOSED"


def _latest(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("latest")
    return value if isinstance(value, dict) else {}


def build_context(
    adapter: NiuOneAdapter,
    moment: datetime | None = None,
    supplemental: AStockDataAdapter | None = None,
) -> MarketContext:
    current = moment or now()
    generated = iso(current)
    snapshot = adapter.snapshot()
    if supplemental is not None:
        snapshot = fuse_snapshot(snapshot, supplemental.snapshot(current.date().isoformat()), generated)
    breadth_latest = _latest(snapshot.breadth)
    canonical = snapshot.canonical_breadth
    red = _number(canonical.advancing if canonical else breadth_latest.get("red"))
    green = _number(canonical.declining if canonical else breadth_latest.get("green"))
    total = (red or 0) + (green or 0)
    breadth_pct = (red / total * 100) if total and red is not None else None
    flow_latest = snapshot.money_flow.get("latest") if isinstance(snapshot.money_flow.get("latest"), dict) else {}
    source_errors = sorted(snapshot.errors)
    provider_count = 1 + (1 if supplemental is not None else 0)
    official_failed = any(not key.startswith("a_stock_data.") for key in source_errors)
    source_count = provider_count - int(official_failed)
    breadth_value = canonical.as_dict() if canonical else {
        "advancing": red,
        "declining": green,
        "advance_ratio": red / total if total and red is not None else None,
        "limit_up": breadth_latest.get("limit_up"),
        "limit_down": breadth_latest.get("limit_down"),
        "updated_at": breadth_latest.get("updated_at"),
        "quality": "GOOD" if not source_errors else "DEGRADED",
        "warnings": source_errors,
    }
    breadth_value.update({"advancing_pct": round(breadth_pct, 2) if breadth_pct is not None else None, "sample_count": len(snapshot.breadth.get("timeline") or [])})
    health = snapshot.provider_health or {"niuone": {"status": "VALID" if not source_errors else "FAILED"}}
    freshness: dict[str, Any] = {"official_generated_at": snapshot.breadth.get("generated_at", ""), "local_generated_at": generated, "providers": health}
    return MarketContext(
        timestamp=generated,
        trading_date=current.date().isoformat(),
        market_status=_market_status(current),
        regime=evaluate_regime(snapshot),
        style=evaluate_styles(snapshot),
        sector_rotation=evaluate_sectors(snapshot, generated),
        breadth=breadth_value,
        liquidity={
            "actual_turnover_yi": breadth_latest.get("actual_turnover_yi"),
            "estimated_turnover_yi": breadth_latest.get("estimated_turnover_yi"),
            "total_inflow_yi": flow_latest.get("total_inflow_yi"),
        },
        risk={
            "limit_down": breadth_value.get("limit_down"),
            "broken_limit_rate": snapshot.market_internals.get("broken_limit_rate"),
            "yesterday_limit_up_continuation": snapshot.market_internals.get("yesterday_limit_up_continuation"),
            "source_errors": source_errors,
        },
        data_quality={
            "sources_ok": source_count,
            "sources_total": provider_count,
            "degraded": bool(source_errors) or breadth_value.get("quality") not in {None, "GOOD"},
            "providers": health,
            "reasons": breadth_value.get("warnings", []),
        },
        data_freshness=freshness,
        source_versions={**snapshot.source_versions, "macro_rules": CONTEXT_VERSION},
    )
