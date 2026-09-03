#!/usr/bin/env python3
"""Bounded, read-only a-stock-data smoke; never writes responses or fixtures."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_ext.adapters.a_stock_data.client import AStockDataClient
from local_ext.adapters.a_stock_data.provider import AStockDataAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the eight P0 supplemental capabilities once")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD trading date")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    adapter = AStockDataAdapter(
        enabled=True,
        top_n=3,
        client=AStockDataClient(timeout_seconds=args.timeout, retries=0, min_interval_seconds=args.interval),
        pool_client=AStockDataClient(base_url="https://push2ex.eastmoney.com", timeout_seconds=args.timeout, retries=0, min_interval_seconds=args.interval),
    )
    started = time.monotonic()
    snapshot = adapter.snapshot(args.date)
    elapsed = time.monotonic() - started
    print(f"date={args.date} elapsed_seconds={elapsed:.2f}")
    for name, result in snapshot.results.items():
        rows = len(result.data) if isinstance(result.data, list) else 0
        print(f"{name}: status={result.status} quality={result.metadata.quality} rows={rows} error={result.error or '-'}")
    return 0 if all(result.status in {"VALID", "VALID_EMPTY"} for result in snapshot.results.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
