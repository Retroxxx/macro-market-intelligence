from __future__ import annotations

import unittest

from local_ext.adapters.a_stock_data.models import AStockSnapshot
from local_ext.core.models import NiuOneSnapshot, ProviderResult, SourceMetadata
from local_ext.fusion.market import fuse_snapshot
from local_ext.fusion.quality import choose_value
from local_ext.fusion.sectors import fuse_sectors


NOW = "2026-09-02T10:00:00+08:00"


def result(capability, data, status="VALID", error=None):
    return ProviderResult(capability, status, data, SourceMetadata("a_stock_data", "https://mock/" + capability, "3.7.2@test", NOW, NOW, "2026-09-02", 0.0, "GOOD" if status == "VALID" else "DEGRADED"), error)


def astock(*, status="VALID", sectors=None, flows=None, pools=None):
    values = {
        "industry_ranking": result("industry_ranking", sectors or [], status),
        "flow_1d": result("flow_1d", (flows or {}).get("1d", []), status),
        "flow_5d": result("flow_5d", (flows or {}).get("5d", []), status),
        "flow_10d": result("flow_10d", (flows or {}).get("10d", []), status),
    }
    for name in ("limit_up", "broken_limit", "limit_down", "yesterday_limit_up"):
        values[name] = result(name, (pools or {}).get(name, []), status)
    return AStockSnapshot(values)


class FusionContractTests(unittest.TestCase):
    def test_field_policy_prefers_official_and_keeps_conflict_lineage(self):
        selected, lineage, warnings = choose_value("change_pct", 3.0, 1.0, conflict_delta=1.0)
        self.assertEqual(selected, 3.0)
        self.assertEqual(lineage["niuone_value"], 3.0)
        self.assertEqual(lineage["astock_value"], 1.0)
        self.assertIn("SOURCE_CONFLICT:change_pct", warnings)

    def test_sector_flow_falls_back_and_preserves_board_identity(self):
        official = NiuOneSnapshot(sectors=[{"name": "机器人", "change_pct": None}])
        supplemental = astock(
            sectors=[{"sector_id": "BK001", "sector_name": "机器人", "taxonomy": "industry", "change_pct": 2.1, "advancing": 72, "declining": 28, "breadth_ratio": .72}],
            flows={"1d": [{"sector_id": "BK001", "sector_name": "机器人", "period": "1d", "flow": 12.0, "flow_ratio": 3.2}], "5d": [{"sector_id": "BK001", "sector_name": "机器人", "period": "5d", "flow": 31.8, "flow_ratio": 4.0}], "10d": [{"sector_id": "BK001", "sector_name": "机器人", "period": "10d", "flow": 48.2, "flow_ratio": 5.0}]},
        )
        row = fuse_sectors(official, supplemental, NOW)[0]
        self.assertEqual(row.sector_id, "BK001")
        self.assertEqual(row.flow_1d, 12.0)
        self.assertEqual(row.flow_5d, 31.8)
        self.assertEqual(row.quality, "DEGRADED")
        self.assertEqual(row.lineage["flow_1d"]["selected_source"], "a_stock_data")

    def test_niuone_failure_still_produces_supplemental_context(self):
        official = NiuOneSnapshot(errors={"breadth": "URLError"})
        supplemental = astock(pools={"limit_up": [{"code": "1"}], "broken_limit": [{"code": "2"}], "limit_down": [], "yesterday_limit_up": [{"pct": 2.0}, {"pct": -1.0}]})
        fused = fuse_snapshot(official, supplemental, NOW)
        self.assertEqual(fused.canonical_breadth.limit_up, 1)
        self.assertEqual(fused.canonical_breadth.broken_limit, 1)
        self.assertAlmostEqual(fused.canonical_breadth.yesterday_limit_up_success_rate, .5)
        self.assertIn("a_stock_data", fused.canonical_breadth.sources)

    def test_both_providers_failed_do_not_invent_values(self):
        fused = fuse_snapshot(NiuOneSnapshot(errors={"breadth": "error"}), astock(status="SOURCE_ERROR"), NOW)
        self.assertIsNone(fused.canonical_breadth.advance_ratio)
        self.assertIsNone(fused.canonical_breadth.limit_up)
        self.assertEqual(fused.canonical_breadth.quality, "FAILED")
        self.assertTrue(fused.errors)


if __name__ == "__main__":
    unittest.main()
