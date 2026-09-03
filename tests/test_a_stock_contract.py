from __future__ import annotations

import unittest
from datetime import datetime
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from local_ext.adapters.a_stock_data.client import AStockDataClient
from local_ext.adapters.a_stock_data.errors import AStockDataError, AStockHTTPError, AStockStaleData
from local_ext.adapters.a_stock_data.normalize import normalize_board_flow, normalize_industry, normalize_limit_pool
from local_ext.adapters.a_stock_data.provider import AStockDataAdapter


MOMENT = datetime(2026, 9, 2, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def industry_payload():
    return {"data": {"diff": [{"f12": "BK001", "f14": "机器人", "f3": 210, "f104": 72, "f105": 28, "f140": "甲公司", "f136": 880}]}}


def flow_payload(period="1d"):
    fields = {"1d": ("f62", "f184", "f3", "f204"), "5d": ("f164", "f165", "f109", "f257"), "10d": ("f174", "f175", "f160", None)}[period]
    row = {"f12": "BK001", "f14": "机器人", fields[0]: 12_000_000_000, fields[1]: 3.2, fields[2]: 210}
    if fields[3]:
        row[fields[3]] = "甲公司" if period == "1d" else 1
    return {"data": {"diff": [row]}}


def pool_payload():
    return {"data": {"pool": [{"c": "000001", "n": "甲公司", "p": 12345, "zdp": 1000, "amount": 1000000, "fbt": "09:30:00", "zttj": {"days": 2, "ct": "2/2"}}]}}


class FakeClient:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def get(self, path, params, capability, ttl):
        self.calls.append((path, capability, ttl))
        if self.failure:
            raise self.failure
        if capability == "industry_ranking":
            return industry_payload()
        if capability.startswith("flow_"):
            return flow_payload(capability.removeprefix("flow_"))
        return pool_payload()


class AStockContractTests(unittest.TestCase):
    def test_normalizers_preserve_identity_and_units(self):
        industry = normalize_industry(industry_payload())
        self.assertEqual(industry[0]["sector_id"], "BK001")
        self.assertEqual(industry[0]["advancing"], 72)
        self.assertAlmostEqual(industry[0]["breadth_ratio"], 0.72)
        flow = normalize_board_flow(flow_payload("5d"), "5d")
        self.assertEqual(flow[0]["flow"], 120.0)
        self.assertEqual(normalize_limit_pool(pool_payload(), "limit_up", "2026-09-02")[0]["price"], 12.345)

    def test_valid_response_has_all_p0_capabilities_and_metadata(self):
        adapter = AStockDataAdapter(client=FakeClient(), pool_client=FakeClient(), clock=lambda: MOMENT)
        snapshot = adapter.snapshot("2026-09-02")
        self.assertEqual(set(snapshot.results), set(adapter.capabilities))
        self.assertTrue(all(result.status == "VALID" for result in snapshot.results.values()))
        self.assertEqual(snapshot.results["flow_10d"].data[0]["leader_name"], None)
        self.assertEqual(snapshot.results["limit_up"].metadata.trading_date, "2026-09-02")
        self.assertTrue(snapshot.results["limit_up"].metadata.source_endpoint.endswith("/getTopicZTPool"))

    def test_valid_empty_is_not_source_error(self):
        class EmptyClient(FakeClient):
            def get(self, path, params, capability, ttl):
                return {"data": None}
        snapshot = AStockDataAdapter(client=EmptyClient(), pool_client=EmptyClient(), clock=lambda: MOMENT).snapshot("2026-09-02")
        self.assertTrue(all(result.status == "VALID_EMPTY" for result in snapshot.results.values()))
        self.assertFalse(snapshot.errors)

    def test_timeout_http_rate_limit_and_schema_are_diagnosed(self):
        for failure in (TimeoutError("slow"), AStockHTTPError(429), AStockDataError("socket")):
            snapshot = AStockDataAdapter(client=FakeClient(failure), pool_client=FakeClient(failure), clock=lambda: MOMENT).snapshot("2026-09-02")
            self.assertTrue(all(result.status == "SOURCE_ERROR" for result in snapshot.results.values()))
        class BrokenClient(FakeClient):
            def get(self, path, params, capability, ttl):
                return {"data": {"diff": "changed"}}
        snapshot = AStockDataAdapter(client=BrokenClient(), pool_client=BrokenClient(), clock=lambda: MOMENT).snapshot("2026-09-02")
        self.assertTrue(all(result.status == "SCHEMA_ERROR" for result in snapshot.results.values()))

    def test_disabled_provider_does_not_make_calls(self):
        client = FakeClient()
        snapshot = AStockDataAdapter(enabled=False, client=client, pool_client=client, clock=lambda: MOMENT).snapshot("2026-09-02")
        self.assertTrue(all(result.status == "DISABLED" for result in snapshot.results.values()))
        self.assertFalse(client.calls)

    def test_client_cache_and_bounded_http_retry(self):
        class Response(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        client = AStockDataClient(timeout_seconds=1, retries=1, min_interval_seconds=0)
        with patch("local_ext.adapters.a_stock_data.client.urlopen", return_value=Response(b'{"data": null}')) as request:
            self.assertEqual(client.get("/x", {"q": "1"}, "cap", 60), {"data": None})
            self.assertEqual(client.get("/x", {"q": "1"}, "cap", 60), {"data": None})
            self.assertEqual(request.call_count, 1)
        retry_response = Response(b'{"data": null}')
        with patch("local_ext.adapters.a_stock_data.client.urlopen", side_effect=[HTTPError("http://mock", 429, "busy", {}, None), retry_response]) as request:
            self.assertEqual(client.get("/retry", {}, "retry", 60), {"data": None})
            self.assertEqual(request.call_count, 2)
        with patch("local_ext.adapters.a_stock_data.client.urlopen", side_effect=HTTPError("http://mock", 403, "blocked", {}, None)) as request:
            with self.assertRaises(AStockHTTPError):
                client.get("/blocked", {}, "blocked", 60)
            self.assertEqual(request.call_count, 1)
    def test_expired_cache_surfaces_stale_data_after_source_failure(self):
        class Response(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        client = AStockDataClient(timeout_seconds=1, retries=0, min_interval_seconds=0, cache_ttls={"cap": 0})
        with patch("local_ext.adapters.a_stock_data.client.urlopen", return_value=Response(b'{"data": null}')):
            self.assertEqual(client.get("/stale", {}, "cap", 60), {"data": None})
        with patch("local_ext.adapters.a_stock_data.client.urlopen", side_effect=AStockDataError("offline")):
            with self.assertRaises(AStockStaleData) as raised:
                client.get("/stale", {}, "cap", 60)
        self.assertEqual(raised.exception.payload, {"data": None})
        self.assertGreaterEqual(raised.exception.age_seconds, 0)

    def test_adapter_exposes_stale_cache_as_stale_data(self):
        class StaleIndustryClient(FakeClient):
            def get(self, path, params, capability, ttl):
                self.calls.append((path, capability, ttl))
                if capability == "industry_ranking":
                    raise AStockStaleData(
                        industry_payload(),
                        42.5,
                        AStockDataError("offline"),
                    )
                return super().get(path, params, capability, ttl)

        snapshot = AStockDataAdapter(
            client=StaleIndustryClient(),
            pool_client=FakeClient(),
            clock=lambda: MOMENT,
        ).snapshot("2026-09-02")
        result = snapshot.results["industry_ranking"]
        self.assertEqual(result.status, "STALE_DATA")
        self.assertEqual(result.metadata.quality, "STALE")
        self.assertEqual(result.metadata.freshness_seconds, 42.5)
        self.assertEqual(result.data[0]["sector_id"], "BK001")

    def test_invalid_json_is_source_error(self):
        class Response(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        client = AStockDataClient(timeout_seconds=1, retries=0, min_interval_seconds=0)
        with patch("local_ext.adapters.a_stock_data.client.urlopen", return_value=Response(b"{")):
            with self.assertRaisesRegex(AStockDataError, "invalid_json"):
                client.get("/broken", {}, "broken", 60)


if __name__ == "__main__":
    unittest.main()
