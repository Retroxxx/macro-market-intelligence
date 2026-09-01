from __future__ import annotations

from typing import Any

from local_ext.core.models import NiuOneSnapshot


def _number(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            continue
        if value == value and abs(value) != float("inf"):
            return value
    return None


def _state(change: float | None, persistence: float | None) -> str:
    if change is None or persistence is None:
        return "UNKNOWN"
    if persistence >= 0.75 and change > 0:
        return "TRENDING"
    if persistence >= 0.50 and change > 0:
        return "EXPANDING"
    if persistence >= 0.50 and change < 0:
        return "FADING"
    return "DIVERGING" if change < 0 else "DISCOVERY"


def evaluate(snapshot: NiuOneSnapshot, updated_at: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in snapshot.sectors:
        sector = str(row.get("name") or row.get("sector") or row.get("industry") or "").strip()
        if not sector:
            continue
        change = _number(row, ("change_pct", "change", "pct", "涨跌幅"))
        breadth = _number(row, ("breadth", "advancing_pct", "up_ratio", "上涨广度"))
        flow = _number(row, ("net_flow_yi", "capital_flow", "主力净流入"))
        persistence = _number(row, ("persistence", "persistence_score", "持续性"))
        warnings = [] if persistence is not None else ["persistence_unavailable"]
        result.append({
            "sector": sector,
            "state": _state(change, persistence),
            "direction": "UP" if change is not None and change > 0 else "DOWN" if change is not None and change < 0 else "UNKNOWN",
            "relative_strength": change,
            "breadth": breadth,
            "capital_flow": flow,
            "persistence": persistence,
            "evidence": ([f"change_pct={change:.2f}"] if change is not None else []),
            "warnings": warnings,
            "updated_at": updated_at,
            "rules_version": "sector-rotation-v1",
        })
    return result
