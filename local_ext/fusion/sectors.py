from __future__ import annotations

from typing import Any

from local_ext.adapters.a_stock_data.models import AStockSnapshot
from local_ext.core.models import CanonicalSector, NiuOneSnapshot
from local_ext.fusion.quality import choose_value, merge_warnings


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def _name(row: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("sector") or row.get("industry") or "").strip()


def _match(astock_rows: list[dict[str, Any]], niuone: dict[str, Any]) -> dict[str, Any] | None:
    code = str(niuone.get("sector_id") or niuone.get("code") or "").strip()
    if code:
        for row in astock_rows:
            if str(row.get("sector_id") or "").strip() == code:
                return row
    name = _name(niuone)
    matches = [row for row in astock_rows if row.get("sector_name") == name and row.get("taxonomy") == "industry"]
    return matches[0] if len(matches) == 1 else None


def _flow(rows: list[dict[str, Any]], sector_id: str, sector_name: str, period: str) -> dict[str, Any] | None:
    matches = [
        row for row in rows
        if row.get("period") == period and (
            str(row.get("sector_id") or "") == sector_id
            or row.get("sector_name") == sector_name
        )
    ]
    return matches[0] if len(matches) == 1 else None


def fuse_sectors(niuone: NiuOneSnapshot, astock: AStockSnapshot, updated_at: str) -> list[CanonicalSector]:
    ranking = astock.results.get("industry_ranking")
    astock_rows = ranking.data if ranking and ranking.status in {"VALID", "VALID_EMPTY"} and isinstance(ranking.data, list) else []
    flow_rows: list[dict[str, Any]] = []
    for capability in ("flow_1d", "flow_5d", "flow_10d"):
        result = astock.results.get(capability)
        if result and result.status in {"VALID", "VALID_EMPTY"} and isinstance(result.data, list):
            flow_rows.extend(result.data)

    rows: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    seen: set[str] = set()
    for source_row in astock_rows:
        key = str(source_row.get("sector_id") or source_row.get("sector_name"))
        if key not in seen:
            seen.add(key)
            rows.append((source_row, next((r for r in niuone.sectors if _match([source_row], r)), None)))
    for source_row in niuone.sectors:
        if not _match(astock_rows, source_row):
            key = _name(source_row)
            if key and key not in seen:
                seen.add(key)
                rows.append(({}, source_row))

    result: list[CanonicalSector] = []
    for astock_row, niuone_row in rows:
        niuone_row = niuone_row or {}
        sector_id = str(astock_row.get("sector_id") or niuone_row.get("sector_id") or _name(niuone_row)).strip()
        sector_name = str(astock_row.get("sector_name") or _name(niuone_row)).strip()
        if not sector_name:
            continue
        warnings: list[str] = []
        lineage: dict[str, Any] = {}

        def pick(field: str, nvalue: Any, avalue: Any, delta: float | None = None) -> Any:
            selected, trace, field_warnings = choose_value(field, nvalue, avalue, conflict_delta=delta)
            lineage[field] = trace
            warnings.extend(field_warnings)
            return selected

        change = pick("change_pct", _number(niuone_row.get("change_pct", niuone_row.get("change"))), _number(astock_row.get("change_pct")), 1.0)
        advancing = pick("advancing", niuone_row.get("advancing"), astock_row.get("advancing"))
        declining = pick("declining", niuone_row.get("declining"), astock_row.get("declining"))
        breadth = pick("breadth_ratio", _number(niuone_row.get("breadth")), _number(astock_row.get("breadth_ratio")), 0.15)
        leader = pick("leader_name", niuone_row.get("leader_name"), astock_row.get("leader_name"))
        leader_change = pick("leader_change", _number(niuone_row.get("leader_change")), _number(astock_row.get("leader_change")), 1.0)
        flows: dict[str, Any] = {}
        ratios: dict[str, Any] = {}
        for period in ("1d", "5d", "10d"):
            row = _flow(flow_rows, sector_id, sector_name, period) or {}
            nflow = _number(niuone_row.get("net_flow_yi", niuone_row.get("capital_flow"))) if period == "1d" else None
            flows[period] = pick(f"flow_{period}", nflow, _number(row.get("flow")), 2.0)
            ratios[period] = pick(f"flow_ratio_{period}", _number(niuone_row.get("flow_ratio")) if period == "1d" else None, _number(row.get("flow_ratio")), 2.0)
        sources = tuple(dict.fromkeys((["niuone"] if niuone_row else []) + (["a_stock_data"] if astock_row else [])))
        if not sources:
            sources = ("unknown",)
        quality = "DEGRADED" if warnings or (not astock_row and not niuone_row) else "GOOD"
        result.append(CanonicalSector(
            sector_id=sector_id,
            sector_name=sector_name,
            taxonomy="industry" if astock_row else "unknown",
            change_pct=change,
            advancing=int(advancing) if advancing is not None else None,
            declining=int(declining) if declining is not None else None,
            breadth_ratio=breadth,
            leader_name=leader,
            leader_change=leader_change,
            flow_1d=flows["1d"], flow_5d=flows["5d"], flow_10d=flows["10d"],
            flow_ratio_1d=ratios["1d"], flow_ratio_5d=ratios["5d"], flow_ratio_10d=ratios["10d"],
            relative_rank=next((i + 1 for i, row in enumerate(astock_rows) if row is astock_row), None),
            updated_at=updated_at,
            sources=sources,
            quality=quality,
            warnings=tuple(merge_warnings(warnings)),
            lineage=lineage,
        ))
    return result
