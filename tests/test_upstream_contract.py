import importlib
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

from local_ext.adapters.niuone import NiuOneAdapter
from local_ext.api.app import app
from local_ext.core.models import NiuOneSnapshot
from local_ext.macro.regime.rules import evaluate as evaluate_regime
from local_ext.macro.sector_rotation.rules import evaluate as evaluate_sectors
from local_ext.macro.style.rules import evaluate as evaluate_styles


class UpstreamContractTests(unittest.TestCase):
    def test_adapter_translates_public_payloads_without_internal_imports(self):
        payloads = {
            "/api/indices": {"items": [{"name": "创业板指", "change_pct": 1.2}]},
            "/api/market_breadth": {"latest": {"red": 7, "green": 3}, "timeline": []},
            "/api/sectors": {"sectors": [{"name": "机器人", "change_pct": 2.0}]},
            "/api/money_flow": {"inflow": [{"name": "机器人", "net_flow_yi": 4.2}], "outflow": []},
        }
        adapter = NiuOneAdapter("http://mock")
        with patch.object(adapter, "_get", side_effect=lambda path: payloads[path]):
            result = adapter.snapshot()
        self.assertEqual(result.indices[0]["name"], "创业板指")
        self.assertEqual(result.sectors[0]["name"], "机器人")
        self.assertEqual(result.sectors[0]["net_flow_yi"], 4.2)
        self.assertFalse(result.errors)

    def test_adapter_retries_transient_transport_failures(self):
        class Response(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        adapter = NiuOneAdapter("http://mock", retries=1)
        with patch(
            "local_ext.adapters.niuone.adapter.urlopen",
            side_effect=[URLError("offline"), Response(b'{"items": []}')],
        ) as request:
            self.assertEqual(adapter._get("/api/indices"), {"items": []})
        self.assertEqual(request.call_count, 2)

    def test_adapter_rejects_http_200_error_payload(self):
        class Response(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        adapter = NiuOneAdapter("http://mock", retries=1)
        with patch(
            "local_ext.adapters.niuone.adapter.urlopen",
            return_value=Response(b'{"items": [], "error": "upstream unavailable"}'),
        ) as request:
            with self.assertRaisesRegex(ValueError, "upstream_error:upstream unavailable"):
                adapter._get("/api/indices")
        self.assertEqual(request.call_count, 1)

        paths = {getattr(route, "path", "") for route in app.routes}
        self.assertTrue({
            "/api/local/v1/health",
            "/api/local/v1/context",
            "/api/local/v1/regime",
            "/api/local/v1/styles",
            "/api/local/v1/sectors",
        }.issubset(paths))

    def test_regime_fails_safe_when_breadth_missing(self):
        result = evaluate_regime(NiuOneSnapshot())
        self.assertEqual(result["regime"], "UNKNOWN")
        self.assertEqual(result["confidence"], 0.0)

    def test_style_missing_proxy_is_unknown(self):
        result = evaluate_styles(NiuOneSnapshot())
        self.assertTrue(result)
        self.assertTrue(all(item["state"] == "UNKNOWN" for item in result))

    def test_degraded_refresh_keeps_last_known_good_context(self):
        api_module = importlib.import_module("local_ext.api.app")
        previous = {
            "timestamp": "2026-09-02T09:30:00+08:00",
            "breadth": {"advancing": 7, "declining": 3, "quality": "GOOD"},
            "data_quality": {"sources_ok": 1, "degraded": False, "reasons": []},
            "data_freshness": {"status": "VALID"},
        }
        attempt = {
            "timestamp": "2026-09-02T10:00:00+08:00",
            "breadth": {"advancing": None, "declining": None, "quality": "FAILED"},
            "data_quality": {"sources_ok": 0, "degraded": True, "reasons": ["breadth"]},
        }
        old_context, old_loaded_at = api_module._context, api_module._context_loaded_at
        api_module._context = None
        api_module._context_loaded_at = 0.0
        try:
            with patch.object(api_module, "build_context", return_value=SimpleNamespace(as_dict=lambda: attempt)):
                with patch.object(api_module, "read_latest", return_value=previous):
                    with patch.object(api_module, "write_latest") as write_latest:
                        value = api_module.get_context()
            self.assertEqual(value["timestamp"], previous["timestamp"])
            self.assertEqual(value["data_freshness"]["status"], "STALE")
            self.assertTrue(value["data_quality"]["degraded"])
            write_latest.assert_not_called()
        finally:
            api_module._context = old_context
            api_module._context_loaded_at = old_loaded_at

        snapshot = NiuOneSnapshot(sectors=[{"name": "机器人", "change_pct": 3.1}])
        result = evaluate_sectors(snapshot, "2026-09-01T10:00:00+08:00")
        self.assertEqual(result[0]["state"], "UNKNOWN")
        self.assertIn("persistence_unavailable", result[0]["warnings"])
    def test_disabled_macro_does_not_refresh_or_persist(self):
        api_module = importlib.import_module("local_ext.api.app")
        old_settings = api_module.settings
        old_context, old_loaded_at = api_module._context, api_module._context_loaded_at
        api_module.settings = SimpleNamespace(enabled=False, refresh_seconds=60)
        api_module._context = None
        api_module._context_loaded_at = 0.0
        try:
            with patch.object(api_module, "build_context") as build_context:
                with patch.object(api_module, "read_latest") as read_latest:
                    with patch.object(api_module, "write_latest") as write_latest:
                        value = api_module.get_context()
            self.assertEqual(value["regime"]["regime"], "UNKNOWN")
            build_context.assert_not_called()
            read_latest.assert_not_called()
            write_latest.assert_not_called()
        finally:
            api_module.settings = old_settings
            api_module._context = old_context
            api_module._context_loaded_at = old_loaded_at


if __name__ == "__main__":
    unittest.main()
