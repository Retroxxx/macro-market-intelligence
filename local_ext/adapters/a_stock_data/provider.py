from __future__ import annotations

from datetime import date
from typing import Any, Callable

from local_ext.adapters.a_stock_data.client import AStockDataClient
from local_ext.adapters.a_stock_data.errors import AStockDataError, AStockSchemaError, AStockStaleData
from local_ext.adapters.a_stock_data.models import AStockSnapshot
from local_ext.adapters.a_stock_data.normalize import normalize_board_flow, normalize_industry, normalize_limit_pool
from local_ext.core.models import A_STOCK_DATA_VERSION, ProviderResult, SourceMetadata
from local_ext.core.time import iso, now


class AStockDataAdapter:
    """P0 supplemental provider; it never imports or writes NiuOne internals."""

    INDUSTRY_PATH = "/api/qt/clist/get"
    POOL_PATHS = {
        "limit_up": "/getTopicZTPool",
        "broken_limit": "/getTopicZBPool",
        "limit_down": "/getTopicDTPool",
        "yesterday_limit_up": "/getYesterdayZTPool",
    }
    SOURCE = "a_stock_data"
    SOURCE_VERSION = A_STOCK_DATA_VERSION

    def __init__(
        self,
        enabled: bool = True,
        client: AStockDataClient | None = None,
        pool_client: AStockDataClient | None = None,
        top_n: int = 20,
        clock: Callable[[], Any] = now,
    ) -> None:
        self.enabled = enabled
        self.client = client or AStockDataClient()
        self.pool_client = pool_client or AStockDataClient(base_url="https://push2ex.eastmoney.com")
        self.top_n = max(1, min(200, top_n))
        self.clock = clock

    def snapshot(self, trading_date: str | None = None) -> AStockSnapshot:
        moment = self.clock()
        day = trading_date or moment.date().isoformat()
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("trading_date_must_be_yyyy_mm_dd") from exc
        if not self.enabled:
            return AStockSnapshot({
                name: self._result(name, "DISABLED", [], day, moment, "provider_disabled")
                for name in self.capabilities
            })
        results: dict[str, ProviderResult] = {}
        for capability in self.capabilities:
            results[capability] = self._fetch(capability, day, moment)
        return AStockSnapshot(results)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("industry_ranking", "flow_1d", "flow_5d", "flow_10d", *self.POOL_PATHS)

    def _fetch(self, capability: str, day: str, moment: Any) -> ProviderResult:
        try:
            data = self._fetch_data(capability, day)
            status = "VALID" if data else "VALID_EMPTY"
            return self._result(capability, status, data, day, moment)
        except AStockStaleData as exc:
            try:
                data = self._normalize(capability, exc.payload, day)
            except (AStockSchemaError, KeyError, TypeError, ValueError) as schema_exc:
                return self._result(capability, "SCHEMA_ERROR", [], day, moment, str(schema_exc))
            return self._result(
                capability,
                "STALE_DATA",
                data,
                day,
                moment,
                str(exc),
                freshness_seconds=exc.age_seconds,
            )
        except AStockSchemaError as exc:
            return self._result(capability, "SCHEMA_ERROR", [], day, moment, str(exc))
        except AStockDataError as exc:
            return self._result(capability, "SOURCE_ERROR", [], day, moment, str(exc))
        except (TimeoutError, OSError) as exc:
            return self._result(capability, "SOURCE_ERROR", [], day, moment, type(exc).__name__)
        except (KeyError, TypeError, ValueError) as exc:
            return self._result(capability, "SCHEMA_ERROR", [], day, moment, type(exc).__name__)

    def _fetch_data(self, capability: str, day: str) -> list[dict[str, Any]]:
        if capability == "industry_ranking":
            payload = self.client.get(self.INDUSTRY_PATH, self._board_params("f3", "m:90+t:2", 100), capability, 60)
        elif capability.startswith("flow_"):
            period = capability.removeprefix("flow_")
            field = {"1d": "f62", "5d": "f164", "10d": "f174"}[period]
            payload = self.client.get(self.INDUSTRY_PATH, self._board_params(field, "m:90+t:2", 200), capability, 300)
        else:
            path = self.POOL_PATHS[capability]
            payload = self.pool_client.get(path, self._pool_params(day, capability), capability, 45)
        return self._normalize(capability, payload, day)

    def _normalize(self, capability: str, payload: dict[str, Any], day: str) -> list[dict[str, Any]]:
        if capability == "industry_ranking":
            return normalize_industry(payload)[: self.top_n]
        if capability.startswith("flow_"):
            return normalize_board_flow(payload, capability.removeprefix("flow_"))[: self.top_n]
        return normalize_limit_pool(payload, capability, day)

    def _result(
        self,
        capability: str,
        status: str,
        data: Any,
        day: str,
        moment: Any,
        error: str | None = None,
        freshness_seconds: float = 0.0,
    ) -> ProviderResult:
        quality = {
            "VALID": "GOOD",
            "VALID_EMPTY": "DEGRADED",
            "STALE_DATA": "STALE",
            "DISABLED": "UNKNOWN",
            "SCHEMA_ERROR": "FAILED",
            "SOURCE_ERROR": "FAILED",
        }.get(status, "UNKNOWN")
        return ProviderResult(
            capability=capability,
            status=status,
            data=data,
            metadata=SourceMetadata(
                source=self.SOURCE,
                source_endpoint=self._endpoint_for(capability),
                source_version=self.SOURCE_VERSION,
                retrieved_at=iso(moment),
                trading_date=day,
                freshness_seconds=freshness_seconds,
                quality=quality,
                warnings=(error,) if error else (),
            ),
            error=error,
        )

    def _endpoint_for(self, capability: str) -> str:
        client = self.pool_client if capability in self.POOL_PATHS else self.client
        default = "https://push2ex.eastmoney.com" if capability in self.POOL_PATHS else "https://push2.eastmoney.com"
        base_url = str(getattr(client, "base_url", default)).rstrip("/")
        path = self.POOL_PATHS[capability] if capability in self.POOL_PATHS else self.INDUSTRY_PATH
        return f"{base_url}{path}"

    @staticmethod
    def _board_params(fid: str, fs: str, page_size: int) -> dict[str, Any]:
        fields = "f2,f3,f4,f12,f13,f14,f62,f104,f105,f128,f136,f140,f141,f164,f165,f174,f175,f184,f204,f257"
        return {
            "pn": 1, "pz": page_size, "po": 1, "np": 1, "fltt": 2,
            "invt": 2, "fid": fid, "fs": fs, "fields": fields,
        }

    @staticmethod
    def _pool_params(day: str, capability: str) -> dict[str, Any]:
        sort = "fbt:asc" if capability in {"limit_up", "broken_limit"} else "fund:asc" if capability == "limit_down" else "zs:desc"
        return {
            "ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
            "Pageindex": 0, "pagesize": 10000, "sort": sort,
            "date": day.replace("-", ""),
        }
