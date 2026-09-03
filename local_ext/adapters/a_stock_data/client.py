from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from local_ext.adapters.a_stock_data.errors import AStockDataError, AStockHTTPError, AStockStaleData


@dataclass(frozen=True)
class CachedResponse:
    payload: dict[str, Any]
    loaded_at: float


class AStockDataClient:
    """Small, serialized EastMoney client with bounded retry and TTL cache."""

    DEFAULT_BASE_URL = "https://push2.eastmoney.com"
    USER_AGENT = "macro-market-intelligence/0.2"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 5.0,
        retries: int = 1,
        min_interval_seconds: float = 1.0,
        cache_ttls: dict[str, int] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(0.5, min(30.0, timeout_seconds))
        self.retries = max(0, min(2, retries))
        self.min_interval_seconds = max(0.0, min(10.0, min_interval_seconds))
        self.cache_ttls = cache_ttls or {}
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], CachedResponse] = {}

    def get(self, path: str, params: dict[str, Any], capability: str, ttl_seconds: int) -> dict[str, Any]:
        key = (path, tuple(sorted((str(k), str(v)) for k, v in params.items())))
        ttl = max(0, int(self.cache_ttls.get(capability, ttl_seconds)))
        with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached.loaded_at < ttl:
                return cached.payload
            try:
                payload = self._request_with_retry(path, params)
            except AStockDataError as exc:
                if cached is not None:
                    age = max(0.0, time.monotonic() - cached.loaded_at)
                    raise AStockStaleData(cached.payload, age, exc) from exc
                raise
            self._cache[key] = CachedResponse(payload, time.monotonic())
            return payload

    def _request_with_retry(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        attempts = self.retries + 1
        for attempt in range(attempts):
            wait = self.min_interval_seconds - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                request = Request(url, headers={"Accept": "application/json", "User-Agent": self.USER_AGENT})
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise AStockDataError("payload_not_object")
                return payload
            except HTTPError as exc:
                # 403 indicates a source policy/block response; retrying worsens it.
                if exc.code == 403 or exc.code < 500 and exc.code != 429 or attempt + 1 >= attempts:
                    raise AStockHTTPError(exc.code) from exc
                if exc.code not in (429, 500, 502, 503, 504):
                    raise AStockHTTPError(exc.code) from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt + 1 >= attempts:
                    raise AStockDataError(type(exc).__name__) from exc
            except ValueError as exc:
                raise AStockDataError("invalid_json") from exc
        raise AStockDataError("request_failed")
