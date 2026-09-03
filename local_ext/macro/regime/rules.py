from __future__ import annotations

from typing import Any

from local_ext.core.models import NiuOneSnapshot

BREADTH_RISK_OFF = 0.40
BREADTH_RISK_ON = 0.65


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def evaluate(snapshot: NiuOneSnapshot) -> dict[str, Any]:
    canonical = snapshot.canonical_breadth
    latest = snapshot.breadth.get("latest") if isinstance(snapshot.breadth.get("latest"), dict) else {}
    breadth = _number(canonical.advance_ratio) if canonical else None
    if breadth is None:
        red = _number(latest.get("red"))
        green = _number(latest.get("green"))
        total = (red or 0) + (green or 0)
        breadth = red / total if red is not None and total else None
    limit_up = _number(canonical.limit_up if canonical else latest.get("limit_up"))
    limit_down = _number(canonical.limit_down if canonical else latest.get("limit_down"))
    broken_rate = _number(canonical.broken_rate if canonical else snapshot.market_internals.get("broken_limit_rate"))
    continuation = _number(canonical.yesterday_limit_up_success_rate if canonical else snapshot.market_internals.get("yesterday_limit_up_continuation"))
    evidence: list[str] = []
    warnings = list(snapshot.errors)
    if canonical:
        warnings.extend(canonical.warnings)
    if breadth is None:
        return {"regime": "UNKNOWN", "confidence": 0.0, "evidence": [], "warnings": [*warnings, "breadth_unavailable"], "rules_version": "regime-v2"}
    evidence.append(f"breadth={breadth:.3f}")
    if limit_up is not None and limit_down is not None:
        evidence.append(f"limit_up={limit_up:g},limit_down={limit_down:g}")
    if broken_rate is not None:
        evidence.append(f"broken_rate={broken_rate:.3f}")
    if continuation is not None:
        evidence.append(f"yesterday_limit_up_success_rate={continuation:.3f}")
    imbalance = limit_down is not None and limit_up is not None and limit_down > limit_up * 2
    if breadth < 0.20 or imbalance or (broken_rate is not None and broken_rate >= 0.35):
        regime = "PANIC"
    elif breadth < BREADTH_RISK_OFF or (broken_rate is not None and broken_rate >= 0.20):
        regime = "RISK_OFF"
    elif breadth >= BREADTH_RISK_ON and (broken_rate is None or broken_rate < 0.20):
        regime = "RISK_ON_TREND" if continuation is None or continuation >= 0.5 else "RISK_ON_ROTATION"
    elif breadth >= 0.50 and continuation is not None and continuation >= 0.5:
        regime = "RECOVERY"
    else:
        regime = "RISK_ON_ROTATION"
        warnings.append("index_trend_history_not_available")
    return {
        "regime": regime,
        "confidence": round(min(1.0, max(0.0, abs(breadth - 0.5) * 1.8 + 0.35)), 2),
        "evidence": evidence,
        "warnings": list(dict.fromkeys(warnings)),
        "rules_version": "regime-v2",
    }
