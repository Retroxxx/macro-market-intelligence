from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from local_ext import __version__
from local_ext.adapters.niuone import NiuOneAdapter
from local_ext.core.config import load_settings
from local_ext.market_context import build_context
from local_ext.storage.context_store import read_latest, write_latest

settings = load_settings()
adapter = NiuOneAdapter(settings.niuone_base_url, settings.timeout_seconds)
_context_lock = threading.Lock()
_context: dict[str, Any] | None = None
_context_loaded_at = 0.0


def get_context() -> dict[str, Any]:
    global _context, _context_loaded_at
    with _context_lock:
        if _context is not None and time.monotonic() - _context_loaded_at < settings.refresh_seconds:
            return _context
        try:
            value = build_context(adapter).as_dict()
            write_latest(value)
            _context = value
        except Exception:  # last-resort read model; do not expose exception details
            _context = read_latest() or {
                "context_version": "market-context-v1",
                "data_quality": {"degraded": True, "reason": "context_unavailable"},
                "data_freshness": {"status": "unknown"},
                "regime": {"regime": "UNKNOWN", "confidence": 0.0, "evidence": [], "warnings": ["context_unavailable"]},
                "style": [],
                "sector_rotation": [],
            }
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
