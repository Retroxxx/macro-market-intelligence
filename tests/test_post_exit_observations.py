#!/usr/bin/env python3
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
COMPAT = APP / "compat"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(COMPAT))

from storage import practice_db  # noqa: E402
from trading.post_exit_observations import (  # noqa: E402
    build_post_exit_observations,
)


def bars(symbol_price: float, *, future_closes: list[float], future_lows=None, future_highs=None):
    lows = future_lows or future_closes
    highs = future_highs or future_closes
    rows = [{"date": "2026-08-03", "close": symbol_price, "high": symbol_price, "low": symbol_price}]
    for index, close in enumerate(future_closes, start=4):
        rows.append({
            "date": f"2026-08-{index:02d}",
            "close": close,
            "high": highs[index - 4],
            "low": lows[index - 4],
        })
    return rows


class PostExitObservationTests(unittest.TestCase):
    def test_five_day_labels_and_replacement_regret_use_forward_bars(self):
        trade = {
            "time": "2026-08-03 14:45:00",
            "action": "SELL",
            "code": "600000",
            "shares": 1000,
            "price": 10.0,
            "reason": "测试软退出",
            "exit_rule": "no_progress",
            "exit_signal": "no_progress",
            "buy_strategy": "niu_emerging",
            "position_fully_closed": True,
            "replacement_target_code": "000001",
            "entry_atr20": 0.4,
        }
        stock = bars(
            10.0,
            future_closes=[10.2, 10.4, 10.8, 11.2, 12.0, 12.1, 12.2, 12.3, 12.4, 12.5],
            future_lows=[9.4, 9.8, 10.0, 10.4, 10.8, 11.0, 11.2, 11.4, 11.6, 11.8],
            future_highs=[10.6, 10.8, 11.0, 11.5, 12.5, 12.6, 12.7, 12.8, 12.9, 13.0],
        )
        replacement = bars(
            20.0,
            future_closes=[20.2, 20.4, 20.6, 20.8, 21.0, 21.1, 21.2, 21.3, 21.4, 21.5],
        )
        benchmark = bars(
            100.0,
            future_closes=[100.2, 100.4, 100.6, 100.8, 101.0, 101.1, 101.2, 101.3, 101.4, 101.5],
        )

        rows = build_post_exit_observations(
            [trade],
            {"sh600000": stock, "sz000001": replacement, "sh000001": benchmark},
            updated_at="2026-08-18 15:15:00",
        )
        five_day = next(row for row in rows if row["horizon"] == 5)

        self.assertEqual(five_day["completed"], 1)
        self.assertEqual(five_day["sell_fly"], 1)
        self.assertEqual(five_day["avoided_loss"], 1)
        self.assertEqual(five_day["close_return_pct"], 20.0)
        self.assertEqual(five_day["benchmark_return_pct"], 1.0)
        self.assertEqual(five_day["excess_return_pct"], 19.0)
        self.assertEqual(five_day["replacement_return_pct"], 5.0)
        self.assertEqual(five_day["replacement_regret_pct"], 15.0)
        self.assertEqual(five_day["replacement_regret"], 1)
        self.assertEqual(five_day["sell_fly_threshold_pct"], 5.0)

    def test_missing_sell_date_bar_is_persistable_as_pending(self):
        rows = build_post_exit_observations(
            [{
                "time": "2026-08-03 14:45:00",
                "action": "SELL",
                "code": "600000",
                "shares": 100,
                "price": 10.0,
                "reason": "test",
            }],
            {"sh600000": [{"date": "2026-08-04", "close": 10.2}]},
            updated_at="2026-08-04 15:15:00",
        )

        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["completed"] == 0 for row in rows))
        self.assertTrue(all(row["quality_status"] == "missing_sell_date_bar" for row in rows))

    def test_observation_upsert_is_idempotent_and_summary_uses_completed_5d(self):
        original_path = practice_db.DB_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            practice_db.DB_PATH = Path(temp_dir) / "practice.db"
            try:
                practice_db.init_db()
                row = {
                    "trade_key": "trade-1",
                    "horizon": 5,
                    "sell_time": "2026-08-03 14:45:00",
                    "code": "600000",
                    "sell_price": 10.0,
                    "shares": 100,
                    "full_exit": 1,
                    "exit_rule": "no_progress",
                    "exit_signal": "no_progress",
                    "buy_strategy": "niu_emerging",
                    "replacement_target_code": "",
                    "sessions_observed": 5,
                    "observation_date": "2026-08-10",
                    "close_return_pct": 3.0,
                    "mfe_pct": 6.0,
                    "mae_pct": -5.5,
                    "benchmark_return_pct": 1.0,
                    "excess_return_pct": 2.0,
                    "replacement_return_pct": None,
                    "replacement_regret_pct": None,
                    "replacement_regret": None,
                    "sell_fly_threshold_pct": 5.0,
                    "sell_fly": 1,
                    "avoided_loss": 1,
                    "completed": 1,
                    "quality_status": "complete",
                    "updated_at": "2026-08-10 15:15:00",
                }
                practice_db.upsert_post_exit_observations([row])
                row["close_return_pct"] = 3.5
                practice_db.upsert_post_exit_observations([row])

                summary = practice_db.query_post_exit_observation_summary()
                with sqlite3.connect(practice_db.DB_PATH) as connection:
                    count = connection.execute(
                        "SELECT count(*) FROM post_exit_observations"
                    ).fetchone()[0]
                self.assertEqual(count, 1)
                self.assertEqual(summary["completed_5d_count"], 1)
                self.assertEqual(summary["sell_fly_5d_count"], 1)
                self.assertEqual(summary["avg_close_return_5d_pct"], 3.5)
            finally:
                practice_db.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
