from __future__ import annotations

from typing import Any

from local_ext.core.models import NiuOneSnapshot

STYLE_PROXIES = {
    "Large": ("沪深300", "上证指数", "上证"),
    "Small": ("中证1000", "中证2000", "国证2000"),
    "Growth": ("创业板指", "创业板", "科创50"),
    "Value": ("上证50", "红利", "沪深300"),
    "Technology": ("科创50", "创业板指", "创业板"),
    "Cyclical": ("周期", "有色", "资源"),
    "Defensive": ("红利", "消费", "医药"),
    "Dividend": ("红利", "红利低波"),
}


def _change(row: dict[str, Any]) -> float | None:
    for key in ("change_pct", "change", "pct", "涨跌幅"):
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            continue
        if value == value and abs(value) != float("inf"):
            return value
    return None


def evaluate(snapshot: NiuOneSnapshot) -> list[dict[str, Any]]:
    rows = [(str(row.get("name") or row.get("code") or ""), _change(row)) for row in snapshot.indices]
    result = []
    for style, proxies in STYLE_PROXIES.items():
        match = next(((name, change) for name, change in rows if any(proxy in name for proxy in proxies) and change is not None), None)
        if match is None:
            result.append({"style_name": style, "state": "UNKNOWN", "direction": "UNKNOWN", "strength": None, "evidence": [], "warnings": ["style_proxy_unavailable"], "rules_version": "style-v1"})
            continue
        name, change = match
        direction = "UP" if change > 0 else "DOWN" if change < 0 else "FLAT"
        state = "STRONG" if abs(change) >= 2 else "IMPROVING" if change > 0 else "WEAK" if change < -2 else "NEUTRAL"
        result.append({"style_name": style, "state": state, "direction": direction, "strength": round(abs(change), 2), "evidence": [f"proxy={name}", f"change_pct={change:.2f}"], "warnings": ["style_history_not_available"], "rules_version": "style-v1"})
    return result
