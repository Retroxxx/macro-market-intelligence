#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from dashboard.data_source_connectivity import (  # noqa: E402
    data_source_test_metadata,
    data_source_test_override_names,
    test_data_source_connection as run_data_source_connection_test,
)
from market_data.fmp_ratings import (  # noqa: E402
    FmpRatingsError,
    fetch_latest_grades,
    request_json_list,
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


class FmpRatingsTests(unittest.TestCase):
    def test_latest_grades_uses_stable_endpoint_and_header_key(self):
        calls = []

        def opener(request, timeout=0):
            calls.append((request, timeout))
            return _Response(
                [
                    {
                        "symbol": "nvda",
                        "publishedDate": "2026-08-12T14:00:00Z",
                        "gradingCompany": "Example Bank",
                        "newGrade": "Buy",
                        "previousGrade": "Hold",
                        "action": "upgrade",
                        "newsTitle": "Rating raised",
                        "priceWhenPosted": 100,
                    }
                ]
            )

        events = fetch_latest_grades(
            "https://financialmodelingprep.com/stable/",
            "fmp-private-key",
            limit=25,
            timeout=9,
            opener=opener,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].symbol, "NVDA")
        request, timeout = calls[0]
        self.assertEqual(
            request.full_url,
            "https://financialmodelingprep.com/stable/grades-latest-news?page=0&limit=25",
        )
        self.assertNotIn("fmp-private-key", request.full_url)
        self.assertEqual(request.get_header("Apikey"), "fmp-private-key")
        self.assertEqual(timeout, 9.0)

    def test_request_retries_transient_failure_with_a_bound(self):
        calls = []
        sleeps = []

        def opener(request, timeout=0):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    request.full_url,
                    503,
                    "unavailable",
                    {},
                    io.BytesIO(b""),
                )
            return _Response([])

        result = request_json_list(
            "https://financialmodelingprep.com/stable",
            "fmp-private-key",
            "grades-latest-news",
            max_retries=1,
            opener=opener,
            sleep=sleeps.append,
        )

        self.assertEqual(result, [])
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [0.5])

    def test_missing_key_and_api_errors_are_safe(self):
        with self.assertRaisesRegex(FmpRatingsError, "FMP API Key"):
            request_json_list(
                "https://financialmodelingprep.com/stable",
                "",
                "grades-latest-news",
                opener=lambda *_args, **_kwargs: self.fail("network must not run"),
            )

        with self.assertRaisesRegex(FmpRatingsError, "套餐权限") as raised:
            request_json_list(
                "https://financialmodelingprep.com/stable",
                "fmp-private-key",
                "grades-latest-news",
                max_retries=0,
                opener=lambda request, timeout=0: (_ for _ in ()).throw(
                    urllib.error.HTTPError(
                        request.full_url,
                        403,
                        "forbidden",
                        {},
                        io.BytesIO(b""),
                    )
                ),
            )
        self.assertNotIn("fmp-private-key", str(raised.exception))

    def test_data_source_test_metadata_and_success_are_secret_safe(self):
        metadata = data_source_test_metadata()
        self.assertEqual([item["id"] for item in metadata], ["fmp-ratings"])
        self.assertEqual(metadata[0]["group_slug"], "us-market")
        self.assertEqual(
            data_source_test_override_names("fmp-ratings"),
            {"FMP_API_BASE_URL", "FMP_API_KEY"},
        )

        ticks = iter((10.0, 10.125))
        result = run_data_source_connection_test(
            "fmp-ratings",
            {
                "FMP_API_BASE_URL": "https://financialmodelingprep.com/stable",
                "FMP_API_KEY": "fmp-private-key",
            },
            opener=lambda *_args, **_kwargs: _Response([]),
            monotonic=lambda: next(ticks),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["elapsed_ms"], 125)
        self.assertEqual(result["record_count"], 0)
        self.assertNotIn("fmp-private-key", json.dumps(result, ensure_ascii=False))

    def test_data_source_test_rejects_unknown_target_and_missing_key(self):
        unknown = run_data_source_connection_test("unknown", {})
        missing = run_data_source_connection_test("fmp-ratings", {})

        self.assertFalse(unknown["ok"])
        self.assertFalse(missing["ok"])
        self.assertIn("FMP API Key", missing["error"])


if __name__ == "__main__":
    unittest.main()
