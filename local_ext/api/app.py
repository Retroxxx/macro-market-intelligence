from __future__ import annotations

import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from local_ext import __version__
from local_ext.adapters.a_stock_data import AStockDataAdapter
from local_ext.adapters.a_stock_data.client import AStockDataClient
from local_ext.adapters.niuone import NiuOneAdapter
from local_ext.core.config import load_settings
from local_ext.market_context import build_context
from local_ext.storage.context_store import read_latest, write_latest

settings = load_settings()
adapter = NiuOneAdapter(settings.niuone_base_url, settings.timeout_seconds)
supplemental_adapter = AStockDataAdapter(
    enabled=settings.a_stock_data_enabled,
    client=AStockDataClient(
        settings.a_stock_data_base_url,
        settings.timeout_seconds,
        settings.a_stock_data_retries,
        settings.a_stock_data_min_interval_seconds,
    ),
    pool_client=AStockDataClient(
        settings.a_stock_data_pool_base_url,
        settings.timeout_seconds,
        settings.a_stock_data_retries,
        settings.a_stock_data_min_interval_seconds,
    ),
)
_context_lock = threading.Lock()
_context: dict[str, Any] | None = None
_context_loaded_at = 0.0


def _has_usable_breadth(value: dict[str, Any]) -> bool:
    breadth = value.get("breadth")
    quality = value.get("data_quality")
    if not isinstance(breadth, dict) or not isinstance(quality, dict):
        return False
    return (
        quality.get("sources_ok", 0) > 0
        and breadth.get("advancing") is not None
        and breadth.get("declining") is not None
        and breadth.get("quality") not in {"FAILED", "UNKNOWN"}
    )


def _mark_stale(value: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    stale = deepcopy(value)
    data_quality = dict(stale.get("data_quality") or {})
    reasons = list(data_quality.get("reasons") or [])
    for reason in ("context_refresh_degraded", *(attempt.get("data_quality", {}).get("reasons") or [])):
        if reason and reason not in reasons:
            reasons.append(reason)
    data_quality.update({"degraded": True, "refresh_status": "STALE_FALLBACK", "reasons": reasons})
    freshness = dict(stale.get("data_freshness") or {})
    freshness.update({"status": "STALE", "last_attempt_at": attempt.get("timestamp", "")})
    stale["data_quality"] = data_quality
    stale["data_freshness"] = freshness
    return stale


def _fallback_context() -> dict[str, Any]:
    return {
        "context_version": "market-context-v1",
        "data_quality": {"degraded": True, "refresh_status": "UNAVAILABLE", "reason": "context_unavailable"},
        "data_freshness": {"status": "UNKNOWN"},
        "regime": {"regime": "UNKNOWN", "confidence": 0.0, "evidence": [], "warnings": ["context_unavailable"]},
        "style": [],
        "sector_rotation": [],
    }


def get_context() -> dict[str, Any]:
    global _context, _context_loaded_at
    with _context_lock:
        if not settings.enabled:
            _context = _fallback_context()
            _context_loaded_at = time.monotonic()
            return _context
        if _context is not None and time.monotonic() - _context_loaded_at < settings.refresh_seconds:
            return _context
        try:
            attempt = build_context(adapter, supplemental=supplemental_adapter).as_dict()
            previous = read_latest()
            if _has_usable_breadth(attempt):
                write_latest(attempt)
                _context = attempt
            elif previous is not None:
                _context = _mark_stale(previous, attempt)
            else:
                _context = attempt
        except Exception:  # last-resort read model; do not expose exception details
            previous = read_latest()
            _context = _mark_stale(previous, _fallback_context()) if previous else _fallback_context()
        _context_loaded_at = time.monotonic()
        return _context


def _envelope(value: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": value.get("context_version", "market-context-v1"),
        "generated_at": value.get("timestamp", ""),
        "freshness": value.get("data_freshness", {}),
        "quality": value.get("data_quality", {}),
        **body,
    }


app = FastAPI(title="NiuOne Local Macro Intelligence", docs_url=None, redoc_url=None, openapi_url=None)
web_root = Path(__file__).resolve().parents[2] / "local_web"
app.mount("/assets", StaticFiles(directory=str(web_root), check_dir=False), name="local-web-assets")


@app.get("/api/local/v1/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": settings.enabled,
        "local_macro_version": __version__,
        "context_version": "market-context-v1",
        "upstream_commit": os.environ.get("LOCAL_MACRO_UPSTREAM_COMMIT", "unknown"),
        "build_time": os.environ.get("LOCAL_MACRO_BUILD_TIME", "unknown"),
        "niuone_public_url": os.environ.get("LOCAL_MACRO_NIUONE_PUBLIC_URL", ""),
    }


@app.get("/api/local/v1/context")
def context() -> dict[str, Any]:
    return get_context()


@app.get("/api/local/v1/regime")
def regime() -> dict[str, Any]:
    value = get_context()
    return _envelope(value, value.get("regime", {}))


@app.get("/api/local/v1/styles")
def styles() -> dict[str, Any]:
    value = get_context()
    return _envelope(value, {"items": value.get("style", [])})


@app.get("/api/local/v1/sectors")
def sectors() -> dict[str, Any]:
    value = get_context()
    return _envelope(value, {"items": value.get("sector_rotation", [])})


@app.get("/", include_in_schema=False)
def index() -> Response:
    path = web_root / "index.html"
    return FileResponse(path) if path.is_file() else JSONResponse({"error": "local_web_not_built"}, status_code=503)
