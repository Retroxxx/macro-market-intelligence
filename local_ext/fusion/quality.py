from __future__ import annotations

from typing import Any


VALID_STATUSES = {"VALID", "VALID_EMPTY"}


def provider_quality(status: str) -> str:
    return {
        "VALID": "GOOD",
        "VALID_EMPTY": "DEGRADED",
        "DISABLED": "UNKNOWN",
        "STALE_DATA": "STALE",
        "SOURCE_ERROR": "FAILED",
        "SCHEMA_ERROR": "FAILED",
    }.get(status, "UNKNOWN")


def merge_warnings(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            values_to_add = [value]
        elif isinstance(value, (list, tuple, set)):
            values_to_add = [str(item) for item in value]
        else:
            values_to_add = []
        for item in values_to_add:
            if item and item not in result:
                result.append(item)
    return result


def choose_value(
    field: str,
    niuone_value: Any,
    astock_value: Any,
    *,
    niuone_fresh: bool = True,
    conflict_delta: float | None = None,
) -> tuple[Any, dict[str, Any], list[str]]:
    """Field-level arbitration; returns selected value, lineage, warnings."""
    warnings: list[str] = []
    conflict = False
    if niuone_value is not None and astock_value is not None and conflict_delta is not None:
        try:
            conflict = abs(float(niuone_value) - float(astock_value)) > conflict_delta
        except (TypeError, ValueError):
            conflict = niuone_value != astock_value
    if conflict:
        warnings.append(f"SOURCE_CONFLICT:{field}")
    if niuone_value is not None and niuone_fresh:
        selected, selected_source = niuone_value, "niuone"
    elif astock_value is not None:
        selected, selected_source = astock_value, "a_stock_data"
        warnings.append(f"fallback:{field}:a_stock_data")
    else:
        selected, selected_source = None, None
    return selected, {
        "selected_source": selected_source,
        "niuone_value": niuone_value,
        "astock_value": astock_value,
        "conflict": conflict,
    }, warnings
