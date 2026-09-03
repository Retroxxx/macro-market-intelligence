#!/usr/bin/env python3
"""Run a safe, local-only load test against the Macro API."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import quantiles
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS = {
    "/api/indices": {"items": [{"name": "沪深300", "change_pct": 0.8}]},
    "/api/market_breadth": {
        "latest": {"red": 7, "green": 3, "limit_up": 40, "limit_down": 6},
        "timeline": [{"generated_at": "2026-09-01T10:00:00+08:00", "red": 7, "green": 3}],
        "generated_at": "2026-09-01T10:00:00+08:00",
    },
    "/api/sectors": {"sectors": [{"name": "机器人", "change_pct": 2.0}]},
    "/api/money_flow": {"inflow": [{"name": "机器人", "net_flow_yi": 4.2}], "outflow": []},
}


class MockState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.hits = {path: 0 for path in ENDPOINTS}

    def record(self, path: str) -> None:
        with self._lock:
            self.hits[path] += 1

    def total(self) -> int:
        with self._lock:
            return sum(self.hits.values())


class MockHandler(BaseHTTPRequestHandler):
    state: MockState

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        payload = ENDPOINTS.get(self.path)
        if payload is None:
            self.send_error(404)
            return
        self.state.record(self.path)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def memory_bytes(pid: int) -> int | None:
    if sys.platform == "win32":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("page_fault_count", ctypes.c_ulong),
                        ("peak_working_set_size", ctypes.c_size_t), ("working_set_size", ctypes.c_size_t),
                        ("quota_peak_paged_pool_usage", ctypes.c_size_t), ("quota_paged_pool_usage", ctypes.c_size_t),
                        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t), ("quota_non_paged_pool_usage", ctypes.c_size_t),
                        ("pagefile_usage", ctypes.c_size_t), ("peak_pagefile_usage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return None
        try:
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb
            )
            return int(counters.working_set_size) if ok else None
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
    try:
        with open(f"/proc/{pid}/statm", encoding="ascii") as stream:
            pages = int(stream.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None


def fetch_json(url: str, timeout: float = 3.0) -> dict:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("response was not an object")
    return value


def wait_ready(base_url: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited with status {process.returncode}")
        try:
            if fetch_json(f"{base_url}/api/local/v1/health").get("ok") is True:
                return
        except (OSError, URLError, RuntimeError, ValueError):
            time.sleep(0.1)
    raise TimeoutError("Macro API did not become ready within 6 seconds")


def percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[int(fraction * 100) - 1]


def run_batch(base_url: str, workers: int, requests: int, process: subprocess.Popen[bytes]) -> dict:
    parties = min(workers, requests)
    barrier = threading.Barrier(parties)

    def request_once(index: int) -> tuple[float, dict]:
        # Only the first wave waits; queued requests must not deadlock the pool.
        if index < parties:
            try:
                barrier.wait(timeout=10)
            except threading.BrokenBarrierError:
                raise RuntimeError("load-test start barrier failed")
        started = time.monotonic()
        value = fetch_json(f"{base_url}/api/local/v1/context")
        return time.monotonic() - started, value

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(request_once, index) for index in range(requests)]
        results = [future.result() for future in futures]
    elapsed = time.monotonic() - started
    rss = memory_bytes(process.pid)
    latencies = sorted(item[0] for item in results)
    return {
        "requests": requests,
        "successes": len(results),
        "elapsed_seconds": round(elapsed, 4),
        "throughput_per_second": round(requests / elapsed, 2) if elapsed else None,
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50) * 1000, 3),
            "p95": round(percentile(latencies, 0.95) * 1000, 3),
            "p99": round(percentile(latencies, 0.99) * 1000, 3),
        },
        "rss_bytes_after": rss,
    }


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 8, 32])
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--ttl-check", action="store_true", help="wait for the 15-second cache TTL and reload")
    args = parser.parse_args()
    if not args.concurrency or any(value < 1 for value in args.concurrency):
        parser.error("--concurrency values must be positive")
    if args.requests < 1:
        parser.error("--requests must be positive")
    return args


def run_one(workers: int, request_count: int, ttl_check: bool) -> dict:
    state = MockState()
    handler = type("BoundMockHandler", (MockHandler,), {"state": state})
    mock = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    mock_thread = threading.Thread(target=mock.serve_forever, daemon=True)
    mock_thread.start()
    process: subprocess.Popen[bytes] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="macro-load-") as data_dir:
            port = free_port()
            env = os.environ.copy()
            env.update({
                "LOCAL_MACRO_ENABLED": "1",
                "LOCAL_MACRO_API_PORT": str(port),
                "LOCAL_MACRO_NIUONE_BASE_URL": f"http://127.0.0.1:{mock.server_port}",
                "LOCAL_MACRO_DATA_DIR": data_dir,
                "LOCAL_MACRO_CONTEXT_REFRESH_SECONDS": "15",
                "LOCAL_MACRO_TIMEOUT_SECONDS": "3",
            })
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "local_ext.api.app:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            base_url = f"http://127.0.0.1:{port}"
            wait_ready(base_url, process)
            baseline_rss = memory_bytes(process.pid)
            cold = run_batch(base_url, workers, request_count, process)
            cold_hits = state.total()
            if cold_hits != 4:
                raise AssertionError(f"cold cache expected 4 upstream calls, got {cold_hits}")
            warm = run_batch(base_url, workers, request_count, process)
            warm_hits = state.total()
            if warm_hits != cold_hits:
                raise AssertionError(f"warm cache added upstream calls: {cold_hits} -> {warm_hits}")
            result = {
                "concurrency": workers,
                "baseline_rss_bytes": baseline_rss,
                "cold": cold,
                "warm": warm,
                "upstream_hits": dict(state.hits),
            }
            if ttl_check:
                time.sleep(16)
                run_batch(base_url, 1, 1, process)
                ttl_hits = state.total()
                if ttl_hits != cold_hits + 4:
                    raise AssertionError(f"TTL reload expected 4 upstream calls, got {ttl_hits - cold_hits}")
                result["ttl_reload_upstream_calls"] = ttl_hits - cold_hits
            peak = max(
                (value for value in (baseline_rss, cold["rss_bytes_after"], warm["rss_bytes_after"]) if value is not None),
                default=None,
            )
            result["peak_rss_bytes"] = peak
            result["rss_delta_bytes"] = peak - baseline_rss if peak is not None and baseline_rss is not None else None
            return result
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        mock.shutdown()
        mock.server_close()
        mock_thread.join(timeout=5)


def main() -> int:
    args = parse_args()
    print(json.dumps({"mode": "loopback-mock", "requests": args.requests, "concurrency": args.concurrency}, ensure_ascii=False))
    try:
        for workers in args.concurrency:
            print(json.dumps(run_one(workers, args.requests, args.ttl_check), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
