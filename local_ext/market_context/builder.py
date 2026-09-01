from __future__ import annotations

from datetime import datetime
from typing import Any

from local_ext.adapters.niuone import NiuOneAdapter
from local_ext.core.models import CONTEXT_VERSION, MarketContext
from local_ext.core.time import iso, now
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


def build_context(adapter: NiuOneAdapter, moment: datetime | None = None) -> MarketContext:
    current = moment or now()
    snapshot = adapter.snapshot()
    generated = iso(current)
    breadth_latest = _latest(snapshot.breadth)
    red = _number(breadth_latest.get("red"))
    green = _number(breadth_latest.get("green"))
    total = (red or 0) + (green or 0)
    breadth_pct = (red / total * 100) if total and red is not None else None
    flow_latest = snapshot.money_flow.get("latest") if isinstance(snapshot.money_flow.get("latest"), dict) else {}
    source_errors = sorted(snapshot.errors)
    source_count = 4 - len(source_errors)
    return MarketContext(
        timestamp=generated,
        trading_date=current.date().isoformat(),
        market_status=_market_status(current),
        regime=evaluate_regime(snapshot),
        style=evaluate_styles(snapshot),
        sector_rotation=evaluate_sectors(snapshot, generated),
        breadth={
            "advancing": red,
            "declining": green,
            "advancing_pct": round(breadth_pct, 2) if breadth_pct is not None else None,
            "limit_up": breadth_latest.get("limit_up"),
            "limit_down": breadth_latest.get("limit_down"),
            "sample_count": len(snapshot.breadth.get("timeline") or []),
        },
        liquidity={
            "actual_turnover_yi": breadth_latest.get("actual_turnover_yi"),
            "estimated_turnover_yi": breadth_latest.get("estimated_turnover_yi"),
            "total_inflow_yi": flow_latest.get("total_inflow_yi"),
        },
        risk={"limit_down": breadth_latest.get("limit_down"), "source_errors": source_errors},
        data_quality={"sources_ok": source_count, "sources_total": 4, "degraded": bool(source_errors)},
        data_freshness={"official_generated_at": snapshot.breadth.get("generated_at", ""), "local_generated_at": generated},
        source_versions={"niuone": "public-api", "macro_rules": CONTEXT_VERSION},
    )
