from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from local_ext.core.models import NiuOneSnapshot


class NiuOneAdapter:
    """HTTP-only boundary around public NiuOne read APIs."""

    ENDPOINTS = {
        "indices": "/api/indices",
        "breadth": "/api/market_breadth",
        "sectors": "/api/sectors",
        "money_flow": "/api/money_flow",
    }

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _get(self, path: str) -> dict[str, Any]:
        request = Request(f"{self.base_url}{path}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("upstream_payload_not_object")
        return payload

    def snapshot(self) -> NiuOneSnapshot:
        values: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        # Four bounded requests run concurrently; total wait is roughly one timeout.
        with ThreadPoolExecutor(max_workers=len(self.ENDPOINTS)) as pool:
            futures = {pool.submit(self._get, path): name for name, path in self.ENDPOINTS.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    values[name] = future.result()
                except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
                    errors[name] = type(exc).__name__
                    values[name] = {}
        money_flow = values.get("money_flow", {})
        return NiuOneSnapshot(
            indices=self._rows(values.get("indices", {}), "items"),
            breadth=values.get("breadth", {}),
            sectors=self._merge_flow(
                self._sector_rows(values.get("sectors", {})),
                self._rows(money_flow, "inflow") + self._rows(money_flow, "outflow"),
            ),
            money_flow=money_flow,
            errors=errors,
        )

    @staticmethod
    def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        return [row for row in payload.get(key, []) if isinstance(row, dict)]

    @classmethod
    def _sector_rows(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in ("sectors", "items", "gain_top", "loss_top"):
            for row in cls._rows(payload, key):
                if row not in rows:
                    rows.append(dict(row))
        return rows

    @staticmethod
    def _merge_flow(sectors: list[dict[str, Any]], flow_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flow_by_name = {
            str(row.get("name") or row.get("sector") or row.get("industry") or "").strip(): row
            for row in flow_rows
        }
        result = [dict(row) for row in sectors]
        for row in result:
            name = str(row.get("name") or row.get("sector") or row.get("industry") or "").strip()
            flow = flow_by_name.get(name)
            if flow is not None and not any(key in row for key in ("net_flow_yi", "capital_flow", "主力净流入")):
                row["net_flow_yi"] = flow.get("net_flow_yi", flow.get("net_flow"))
        return result
