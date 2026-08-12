#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
COMPAT = APP / "compat"
REPORT_PATH = APP / "reports" / "us" / "rating_report.py"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(COMPAT))

from market_data.fmp_ratings import (  # noqa: E402
    FmpRatingsError,
    GradeEvent,
    PriceTargetEvent,
    Quote,
)


class _Response:
    def __init__(self, payload) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


@contextmanager
def loaded_report(*, api_key: str = "", extra_env: dict[str, str] | None = None):
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            "DASHBOARD_HOME": tmp,
            "DASHBOARD_ENV_FILE": str(Path(tmp) / "dashboard.env"),
            "FMP_API_BASE_URL": "https://financialmodelingprep.com/stable",
            "FMP_API_KEY": api_key,
            "FMP_RATING_MAX_RESULTS": "10",
        }
        env.update(extra_env or {})
        with mock.patch.dict(os.environ, env, clear=False):
            name = f"us_rating_report_test_{uuid.uuid4().hex}"
            spec = importlib.util.spec_from_file_location(name, REPORT_PATH)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(module)
        yield module


def grade(
    symbol: str,
    published: str,
    *,
    company: str = "Example Bank",
    new_grade: str = "Buy",
    previous_grade: str = "Hold",
    action: str = "upgrade",
    title: str = "Analyst raises rating",
) -> GradeEvent:
    return GradeEvent(
        symbol=symbol,
        published_at=datetime.fromisoformat(published).astimezone(timezone.utc),
        grading_company=company,
        new_grade=new_grade,
        previous_grade=previous_grade,
        action=action,
        news_title=title,
        news_url="https://example.test/news",
        price_when_posted=100.0,
    )


class UsRatingReportTests(unittest.TestCase):
    def test_latest_eastern_batch_keeps_only_positive_non_downgrades(self):
        with loaded_report() as report:
            latest_day, selected = report.select_latest_positive_events(
                [
                    grade("OLD", "2026-08-11T15:00:00+00:00"),
                    grade("BUY", "2026-08-12T14:00:00+00:00"),
                    grade(
                        "DOWN",
                        "2026-08-12T15:00:00+00:00",
                        previous_grade="Strong Buy",
                        action="downgrade",
                    ),
                    grade(
                        "HOLD",
                        "2026-08-12T16:00:00+00:00",
                        new_grade="Hold",
                        action="reiterated",
                    ),
                ]
            )

        self.assertEqual(latest_day.isoformat(), "2026-08-12")
        self.assertEqual([event.symbol for event in selected], ["BUY"])

    def test_deduplicates_events_and_ranks_cluster_ahead(self):
        duplicate = grade("AAA", "2026-08-12T14:00:00+00:00")
        with loaded_report() as report:
            _, selected = report.select_latest_positive_events(
                [
                    duplicate,
                    duplicate,
                    grade(
                        "AAA",
                        "2026-08-12T15:00:00+00:00",
                        company="Second Bank",
                        action="initiated",
                    ),
                    grade("BBB", "2026-08-12T16:00:00+00:00"),
                ]
            )
            ranked = report.rank_rating_groups(selected, [], {})

        self.assertEqual(len(selected), 3)
        self.assertEqual(ranked[0][0], "AAA")
        self.assertEqual(len(ranked[0][1]), 2)

    def test_report_keeps_dashboard_parser_field_contract(self):
        event = grade("NVDA", "2026-08-12T14:00:00+00:00")
        target = PriceTargetEvent(
            symbol="NVDA",
            published_at=event.published_at,
            analyst_company="Example Bank",
            analyst_name="A. Analyst",
            price_target=150.0,
            price_when_posted=100.0,
            news_title="Target raised",
        )
        quote = Quote(symbol="NVDA", name="NVIDIA Corporation", price=120.0)
        with loaded_report() as report:
            content = report.format_report(
                event.published_at.date(),
                [("NVDA", [event], target, quote)],
                now=datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc),
                max_results=10,
            )

        self.assertIn("数据源：Financial Modeling Prep（FMP）", content)
        self.assertIn("- NVDA / NVIDIA Corporation", content)
        for label in (
            "机构/分析师：",
            "评级动作：",
            "目标价：",
            "核心理由/催化剂：",
            "风险点：",
            "适合关注类型：",
        ):
            self.assertIn(label, content)
        self.assertIn("$150.00", content)
        self.assertIn("+25.0%", content)

    def test_generate_report_uses_fmp_feeds_without_model_configuration(self):
        requests = []

        def opener(request, timeout=0):
            requests.append((request, timeout))
            if "/grades-latest-news?" in request.full_url:
                return _Response(
                    [
                        {
                            "symbol": "NVDA",
                            "publishedDate": "2026-08-12T14:00:00Z",
                            "gradingCompany": "Example Bank",
                            "newGrade": "Buy",
                            "previousGrade": "Hold",
                            "action": "upgrade",
                            "newsTitle": "NVIDIA upgraded after results",
                            "priceWhenPosted": 100,
                        }
                    ]
                )
            if "/price-target-latest-news?" in request.full_url:
                return _Response(
                    [
                        {
                            "symbol": "NVDA",
                            "publishedDate": "2026-08-12T14:00:00Z",
                            "analystCompany": "Example Bank",
                            "priceTarget": 150,
                            "priceWhenPosted": 100,
                        }
                    ]
                )
            if "/batch-quote?" in request.full_url:
                return _Response([{"symbol": "NVDA", "name": "NVIDIA", "price": 120}])
            raise AssertionError(request.full_url)

        with loaded_report(
            api_key="fmp-private-key",
            extra_env={
                "US_RATING_MODEL": "must-be-ignored",
                "US_RATING_API_KEY": "must-be-ignored",
                "DASHBOARD_GROK_API_KEY": "must-be-ignored",
            },
        ) as report:
            content = report.generate_report(
                now=datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc),
                opener=opener,
            )

        self.assertIn("NVDA / NVIDIA", content)
        self.assertIn("Example Bank", content)
        self.assertEqual(len(requests), 3)
        for request, timeout in requests:
            self.assertNotIn("fmp-private-key", request.full_url)
            self.assertEqual(request.get_header("Apikey"), "fmp-private-key")
            self.assertGreater(timeout, 0)

    def test_optional_target_and_quote_failures_degrade_report(self):
        with loaded_report(api_key="fmp-private-key") as report:
            event = grade("TEST", "2026-08-12T14:00:00+00:00")
            with (
                mock.patch.object(report, "fetch_latest_grades", return_value=[event]),
                mock.patch.object(
                    report,
                    "fetch_latest_price_targets",
                    side_effect=FmpRatingsError("target unavailable"),
                ),
                mock.patch.object(
                    report,
                    "fetch_batch_quotes",
                    side_effect=FmpRatingsError("quote unavailable"),
                ),
            ):
                content = report.generate_report(
                    now=datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)
                )

        self.assertIn("TEST / TEST", content)
        self.assertIn("本次 FMP 评级记录未附目标价", content)

    def test_missing_fmp_key_never_falls_back_to_legacy_model_or_grok(self):
        with loaded_report(
            extra_env={
                "US_RATING_MODEL": "legacy-model",
                "US_RATING_API_KEY": "legacy-key",
                "DASHBOARD_GROK_API_KEY": "legacy-grok-key",
            }
        ) as report:
            with self.assertRaisesRegex(FmpRatingsError, "FMP API Key"):
                report.generate_report()
            self.assertFalse(hasattr(report, "US_RATING_MODEL"))

    def test_database_write_is_idempotent_and_records_fmp_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["DASHBOARD_HOME"] = tmp
            env["DASHBOARD_ENV_FILE"] = str(Path(tmp) / "dashboard.env")
            code = f"""
import importlib.util, json, os, sys
from datetime import datetime, timezone
sys.path[:0] = [{str(COMPAT)!r}, {str(APP)!r}]
spec = importlib.util.spec_from_file_location('us_rating_report_under_test', {str(REPORT_PATH)!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
os.environ['NIUONE_CRON_RUN_KEY'] = 'fd0b807138f4:202608130900'
now = datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)
first = m.write_report_to_db('- TEST / Test Corp', now=now)
second = m.write_report_to_db('- TEST / Test Corp', now=now)
import push_history
records = push_history.query_messages(category='us_ratings', limit=5)['records']
record = records[0]
print(json.dumps({{
    'first': first,
    'second': second,
    'count': len(records),
    'provider': (record.get('metadata') or {{}}).get('provider'),
    'external_id': record.get('external_id'),
}}))
"""
            out = subprocess.check_output(
                [sys.executable, "-c", textwrap.dedent(code)], env=env, text=True
            )
            result = json.loads(out)

        self.assertEqual(result["first"], 1)
        self.assertEqual(result["second"], 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["provider"], "financial_modeling_prep")
        self.assertEqual(result["external_id"], "fd0b807138f4:202608130900")

    def test_generation_failure_creates_no_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["DASHBOARD_HOME"] = tmp
            env["DASHBOARD_ENV_FILE"] = str(Path(tmp) / "dashboard.env")
            code = f"""
import importlib.util, json, sys
sys.path[:0] = [{str(COMPAT)!r}, {str(APP)!r}]
spec = importlib.util.spec_from_file_location('us_rating_report_under_test', {str(REPORT_PATH)!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.generate_report = lambda test_mode=False: (_ for _ in ()).throw(RuntimeError('boom'))
sys.argv = ['us_rating_report.py', '--store-only']
try:
    m.main()
except SystemExit as exc:
    exit_code = int(exc.code or 0)
else:
    exit_code = 0
import push_history
records = push_history.query_messages(category='us_ratings', limit=5)['records']
print(json.dumps({{'exit_code': exit_code, 'count': len(records)}}))
"""
            proc = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(code)],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            result = json.loads(proc.stdout)

        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["count"], 0)
        self.assertIn("ERROR: RuntimeError: boom", proc.stderr)

    def test_database_failure_exits_nonzero_for_scheduler_retry(self):
        with loaded_report(api_key="fmp-private-key") as report:
            with (
                mock.patch.object(report, "generate_report", return_value="- TEST / Test Corp"),
                mock.patch.object(
                    report,
                    "write_report_to_db",
                    side_effect=RuntimeError("database unavailable"),
                ),
                mock.patch.object(sys, "argv", ["us_rating_report.py", "--store-only"]),
                mock.patch("sys.stderr"),
            ):
                with self.assertRaisesRegex(SystemExit, "1"):
                    report.main()


if __name__ == "__main__":
    unittest.main()
