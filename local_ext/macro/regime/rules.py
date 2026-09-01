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
    latest = snapshot.breadth.get("latest") if isinstance(snapshot.breadth.get("latest"), dict) else {}
    red = _number(latest.get("red"))
    green = _number(latest.get("green"))
    limit_up = _number(latest.get("limit_up"))
    limit_down = _number(latest.get("limit_down"))
    total = (red or 0) + (green or 0)
    breadth = red / total if red is not None and total else None
    evidence: list[str] = []
    warnings = list(snapshot.errors.values())
    if breadth is None:
        return {"regime": "UNKNOWN", "confidence": 0.0, "evidence": [], "warnings": [*warnings, "breadth_unavailable"], "rules_version": "regime-v1"}
    evidence.append(f"breadth={breadth:.3f}")
    if limit_up is not None and limit_down is not None:
        evidence.append(f"limit_up={limit_up:g},limit_down={limit_down:g}")
    if breadth < 0.20 or (limit_down is not None and limit_up is not None and limit_down > limit_up * 2):
        regime = "PANIC"
    elif breadth < BREADTH_RISK_OFF:
        regime = "RISK_OFF"
    elif breadth >= BREADTH_RISK_ON:
        regime = "RISK_ON_TREND"
    else:
        regime = "RISK_ON_ROTATION"
        warnings.append("index_trend_history_not_available")
    return {
        "regime": regime,
        "confidence": round(min(1.0, max(0.0, abs(breadth - 0.5) * 1.8 + 0.35)), 2),
        "evidence": evidence,
        "warnings": warnings,
        "rules_version": "regime-v1",
    }
