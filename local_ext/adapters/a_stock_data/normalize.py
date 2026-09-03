from __future__ import annotations

from typing import Any

from local_ext.adapters.a_stock_data.errors import AStockSchemaError


def _data(payload: dict[str, Any]) -> dict[str, Any] | None:
    if "data" not in payload:
        raise AStockSchemaError("data_missing")
    value = payload["data"]
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AStockSchemaError("data_not_object")
    return value


def _rows(payload: dict[str, Any], key: str = "diff") -> list[dict[str, Any]]:
    data = _data(payload)
    if data is None:
        return []
    if key not in data:
        raise AStockSchemaError(f"{key}_missing")
    value = data[key]
    if value is None:
        return []
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AStockSchemaError(f"{key}_not_rows")
    return value


def _number(value: Any, *, scale: float = 1.0) -> float | None:
    try:
        result = float(value) / scale
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def normalize_industry(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize EastMoney industry ranking rows without name-only identity."""
    result = []
    for row in _rows(payload):
        code = _text(row.get("f12"))
        name = _text(row.get("f14"))
        if not code or not name:
            continue
        advancing = _integer(row.get("f104"))
        declining = _integer(row.get("f105"))
        total = (advancing or 0) + (declining or 0)
        result.append({
            "sector_id": code,
            "sector_name": name,
            "taxonomy": "industry",
            "change_pct": _number(row.get("f3")),
            "advancing": advancing,
            "declining": declining,
            "flat": None,
            "breadth_ratio": advancing / total if total else None,
            "leader_name": _text(row.get("f140")),
            "leader_change": _number(row.get("f136")),
        })
    return result


_FLOW_FIELDS = {
    "1d": ("f62", "f184", "f3", "f204"),
    "5d": ("f164", "f165", "f109", "f257"),
    "10d": ("f174", "f175", "f160", None),
}


def normalize_board_flow(payload: dict[str, Any], period: str) -> list[dict[str, Any]]:
    if period not in _FLOW_FIELDS:
        raise ValueError(f"unsupported_flow_period:{period}")
    amount_key, ratio_key, change_key, leader_key = _FLOW_FIELDS[period]
    result = []
    for row in _rows(payload):
        code = _text(row.get("f12"))
        name = _text(row.get("f14"))
        if not code or not name:
            continue
        result.append({
            "sector_id": code,
            "sector_name": name,
            "taxonomy": "industry",
            "period": period,
            "flow": _number(row.get(amount_key), scale=1e8),
            "flow_ratio": _number(row.get(ratio_key)),
            "change_pct": _number(row.get(change_key)),
            # f204/f257 are not stable across endpoint revisions; accept text only.
            "leader_name": _text(row.get(leader_key)) if leader_key else None,
        })
    return result


_POOL_ENDPOINTS = {
    "limit_up": "getTopicZTPool",
    "broken_limit": "getTopicZBPool",
    "limit_down": "getTopicDTPool",
    "yesterday_limit_up": "getYesterdayZTPool",
}


def normalize_limit_pool(payload: dict[str, Any], state: str, trading_date: str) -> list[dict[str, Any]]:
    rows = _rows(payload, "pool")
    result = []
    for row in rows:
        item = {
            "code": _text(row.get("c", row.get("code"))),
            "name": _text(row.get("n", row.get("name"))),
            "price": _number(row.get("p", row.get("ztp")), scale=1000),
            "pct": _number(row.get("zdp", row.get("pct"))),
            "amount": _number(row.get("amount")),
            "float_cap": _number(row.get("ltsz")),
            "turnover": _number(row.get("hs")),
            "first_seal": _text(row.get("fbt")),
            "last_seal": _text(row.get("lbt")),
            "seal_fund": _number(row.get("fund")),
            "break_times": _integer(row.get("zbc")),
            "industry": _text(row.get("hybk", row.get("industry"))),
            "amplitude": _number(row.get("zf")),
            "speed": _number(row.get("speed")),
            "state": state,
            "trading_date": trading_date,
        }
        stats = row.get("zttj")
        if isinstance(stats, dict):
            item["limit_days"] = _integer(stats.get("days"))
            item["zt_stat"] = _text(stats.get("ct"))
        else:
            item["limit_days"] = None
            item["zt_stat"] = None
        item["dt_days"] = _integer(row.get("days"))
        item["open_times"] = _integer(row.get("open_times"))
        if item["code"] or item["name"]:
            result.append(item)
    return result
