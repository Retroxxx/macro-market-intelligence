import unittest
from unittest.mock import patch

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

    def test_local_api_routes_are_declared(self):
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

    def test_sector_rotation_does_not_turn_one_day_rank_into_persistence(self):
        snapshot = NiuOneSnapshot(sectors=[{"name": "机器人", "change_pct": 3.1}])
        result = evaluate_sectors(snapshot, "2026-09-01T10:00:00+08:00")
        self.assertEqual(result[0]["state"], "UNKNOWN")
        self.assertIn("persistence_unavailable", result[0]["warnings"])


if __name__ == "__main__":
    unittest.main()
