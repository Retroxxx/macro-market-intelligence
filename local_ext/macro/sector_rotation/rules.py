from __future__ import annotations

from typing import Any

from local_ext.core.models import NiuOneSnapshot


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def _persistence(flow_1d: float | None, flow_5d: float | None, flow_10d: float | None) -> str:
    if flow_1d is None or flow_5d is None:
        return "UNKNOWN"
    signs = [flow > 0 for flow in (flow_1d, flow_5d) if flow != 0]
    if flow_10d is not None and flow_10d != 0:
        signs.append(flow_10d > 0)
    if signs and all(signs):
        return "PERSISTENT_POSITIVE"
    if signs and not any(signs):
        return "PERSISTENT_NEGATIVE"
    if flow_1d > 0 and flow_5d <= 0:
        return "IMPROVING"
    if flow_1d < 0 and flow_5d >= 0:
        return "DETERIORATING"
    return "MIXED"


def _state(row: dict[str, Any]) -> str:
    change = _number(row.get("change_pct"))
    breadth = _number(row.get("breadth_ratio", row.get("breadth")))
    f1, f5, f10 = (_number(row.get(f"flow_{period}")) for period in ("1d", "5d", "10d"))
    breadth_direction = str(row.get("breadth_direction") or "UNKNOWN").upper()
    if change is None:
        return "UNKNOWN"
    if change > 0 and f1 is not None and f1 > 0 and f5 is not None and f5 <= 0 and (breadth is None or breadth >= 0.5):
        return "STARTING"
    if change > 0 and breadth is not None and breadth >= 0.65 and f1 is not None and f1 > 0 and f5 is not None and f5 > 0 and (f10 is None or f10 > 0):
        return "EXPANDING"
    if change > 0 and breadth is not None and breadth < 0.45:
        return "DIVERGING"
    if change > 0 and f1 is not None and f5 is not None and f1 > 0 and f5 > 0:
        return "TRENDING"
    if change > 0 and breadth_direction == "CONTRACTING":
        return "DIVERGING"
    if change < 0 and breadth is not None and breadth < 0.50 and f1 is not None and f5 is not None and f1 < 0 and f5 < 0:
        return "FADING"
    if change < 0:
        return "WEAK"
    return "UNKNOWN"


def _row_from_snapshot(snapshot: NiuOneSnapshot) -> list[dict[str, Any]]:
    if snapshot.canonical_sectors:
        return [item.as_dict() for item in snapshot.canonical_sectors]
    return [dict(row) for row in snapshot.sectors]


def evaluate(snapshot: NiuOneSnapshot, updated_at: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    canonical_input = bool(snapshot.canonical_sectors)
    for row in _row_from_snapshot(snapshot):
        sector = str(row.get("sector_name") or row.get("name") or row.get("sector") or row.get("industry") or "").strip()
        if not sector:
            continue
        change = _number(row.get("change_pct", row.get("change", row.get("pct"))))
        breadth = _number(row.get("breadth_ratio", row.get("breadth", row.get("advancing_pct"))))
        if breadth is not None and breadth > 1:
            breadth /= 100
        f1, f5, f10 = (_number(row.get(f"flow_{period}")) for period in ("1d", "5d", "10d"))
        persistence = _persistence(f1, f5, f10)
        warnings = list(row.get("warnings") or [])
        if not canonical_input and not row.get("persistence") and persistence == "UNKNOWN":
            warnings.append("persistence_unavailable")
        evidence = []
        for label, value, suffix in (("change_1d", change, "%"), ("breadth", breadth, ""), ("flow_1d", f1, ""), ("flow_5d", f5, ""), ("flow_10d", f10, "")):
            if value is not None:
                evidence.append(f"{label}={value:.2f}{suffix}")
        available = [value for value in (f1, f5, f10) if value is not None]
        alignment = "positive" if len(available) >= 2 and all(value > 0 for value in available) else "negative" if len(available) >= 2 and all(value < 0 for value in available) else "mixed" if len(available) >= 2 else "unknown"
        evidence.append(f"flow_alignment={alignment}")
        evidence.append(f"persistence={persistence}")
        result.append({
            "sector": sector,
            "sector_id": row.get("sector_id"),
            "state": _state({**row, "change_pct": change, "breadth_ratio": breadth}),
            "direction": "UP" if change is not None and change > 0 else "DOWN" if change is not None and change < 0 else "UNKNOWN",
            "relative_strength": change,
            "relative_rank": row.get("relative_rank"),
            "breadth": breadth,
            "breadth_direction": row.get("breadth_direction", "UNKNOWN"),
            "flow_1d": f1,
            "flow_5d": f5,
            "flow_10d": f10,
            "flow_alignment": alignment,
            "capital_flow": f1,
            "persistence": persistence,
            "persistence_value": row.get("persistence_value"),
            "quality": row.get("quality", "UNKNOWN"),
            "evidence": evidence,
            "warnings": list(dict.fromkeys(warnings)),
            "updated_at": updated_at,
            "rules_version": "sector-rotation-v2",
        })
    return result
