#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = ROOT / "web" / "src"
DISPLAY_PATH = WEB_SRC / "utils" / "homeOverviewDisplay.js"
OVERVIEW_PATH = WEB_SRC / "components" / "OverviewPanel.vue"
ROUTER_PATH = WEB_SRC / "router.js"
TABS_PATH = WEB_SRC / "composables" / "useDashboardTabs.js"


class HomeOverviewFrontendTests(unittest.TestCase):
    def test_overview_display_model_preserves_missing_values_and_ranks_candidates(self):
        scenario = f"""
const module = await import({json.dumps(DISPLAY_PATH.as_uri())} + '?overview-display-test=1');
const zeroAccount = module.overviewAccount({{
  total_equity: 0,
  cash: 0,
  initial_cash: 0,
  positions: [],
}});
const profitableAccount = module.overviewAccount({{
  total_equity: 1120000,
  cash: 420000,
  initial_cash: 1000000,
  generated_at: '2026-08-09 10:30:00',
  daily_equity_history: [{{time: '2026-08-08 15:00:00', equity: 1100000}}],
  positions: [{{code: '600000'}}, {{code: '000001'}}],
}});
const flatDailyAccount = module.overviewAccount({{
  total_equity: 1000000,
  cash: 1000000,
  initial_cash: 1000000,
  daily_pnl: 0,
  daily_pnl_pct: 0,
}});
const closedDayAccount = module.overviewAccount({{
  total_equity: 1020000,
  cash: 1020000,
  initial_cash: 1000000,
  generated_at: '2026-08-09 10:30:00',
  trading_calendar: {{date: '2026-08-09', is_trading_day: false}},
  daily_equity_history: [
    {{time: '2026-08-06 15:00:00', equity: 1000000}},
    {{time: '2026-08-07 15:00:00', equity: 1020000}},
  ],
}});
const missingBreadth = module.overviewBreadth({{latest: {{}}}});
const breadth = module.overviewBreadth({{latest: {{
  red: 3000,
  green: 2000,
  limit_up: 50,
  limit_down: 5,
  broken_limit: 12,
}}}});
const candidates = module.overviewCandidates([
  {{code: 'low', score: 4, entry_threshold: 8}},
  {{code: 'mid', score: 7.5, entry_threshold: 8}},
  {{code: 'blocked', score: 9, entry_threshold: 8, hard_blockers: ['结构未确认']}},
  {{code: 'high', score: 8.2, entry_threshold: 8, actionable: true, best_strategy: 'niu_leader'}},
]);
const indices = module.overviewIndices({{
  items: [
    {{key: 'cyb', name: '创业板指', market_type: 'a_index'}},
    {{key: 'hs300', name: '沪深300', market_type: 'a_index'}},
    {{key: 'sh', name: '上证指数', market_type: 'a_index'}},
    {{key: 'sz', name: '深证成指', market_type: 'a_index'}},
  ],
}});
const viewportModes = [
  module.overviewViewportMode(1920, 1080),
  module.overviewViewportMode(1024, 650),
  module.overviewViewportMode(900, 500),
  module.overviewViewportMode(700, 800),
];
const mainlinePanelModes = [260, 180, 117, 80].map(module.overviewMainlinePanelMode);
console.log(JSON.stringify({{
  zeroAccount,
  profitableAccount,
  flatDailyAccount,
  closedDayAccount,
  missingBreadth,
  breadth,
  candidateOrder: candidates.map(item => item.code),
  candidateLabels: candidates.map(item => item.tierLabel),
  indexOrder: indices.map(item => item.key),
  missingNumber: module.formatOverviewNumber(null),
  viewportModes,
  mainlinePanelModes,
}}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", scenario],
            cwd=ROOT / "web",
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        payload = json.loads(result.stdout)

        self.assertTrue(payload["zeroAccount"]["available"])
        self.assertIsNone(payload["zeroAccount"]["exposurePct"])
        self.assertAlmostEqual(payload["profitableAccount"]["exposurePct"], 62.5)
        self.assertEqual(payload["profitableAccount"]["pnl"], 120000)
        self.assertEqual(payload["profitableAccount"]["positionCount"], 2)
        self.assertEqual(payload["profitableAccount"]["dailyPnl"], 20000)
        self.assertAlmostEqual(payload["profitableAccount"]["dailyPnlPct"], 1.8181818)
        self.assertEqual(payload["flatDailyAccount"]["dailyPnl"], 0)
        self.assertEqual(payload["flatDailyAccount"]["dailyPnlPct"], 0)
        self.assertEqual(payload["closedDayAccount"]["dailyPnl"], 20000)
        self.assertEqual(payload["closedDayAccount"]["dailyPnlPct"], 2)
        self.assertFalse(payload["missingBreadth"]["available"])
        self.assertIsNone(payload["missingBreadth"]["advancing"])
        self.assertEqual(payload["breadth"]["advancingPct"], 60)
        self.assertEqual(payload["candidateOrder"], ["high", "blocked", "mid", "low"])
        self.assertEqual(
            payload["candidateLabels"],
            ["交易达标", "未达标", "待确认", "仅观察"],
        )
        self.assertEqual(payload["indexOrder"], ["sh", "sz", "cyb", "hs300"])
        self.assertEqual(payload["missingNumber"], "--")
        self.assertEqual(
            payload["viewportModes"],
            [
                {"layout": "wide", "density": "comfortable"},
                {"layout": "compact", "density": "compact"},
                {"layout": "compact", "density": "ultra-compact"},
                {"layout": "mobile", "density": "comfortable"},
            ],
        )
        self.assertEqual(
            payload["mainlinePanelModes"],
            ["full", "compact", "summary", "summary"],
        )

    def test_overview_route_is_lazy_read_only_and_lifecycle_safe(self):
        component = OVERVIEW_PATH.read_text(encoding="utf-8")
        breadth_component = (
            WEB_SRC / "components" / "indices" / "MarketBreadthChart.vue"
        ).read_text(encoding="utf-8")
        router = ROUTER_PATH.read_text(encoding="utf-8")
        tabs = TABS_PATH.read_text(encoding="utf-8")

        self.assertIn("const OverviewPanel = defineAsyncComponent", (
            WEB_SRC / "components" / "DashboardPage.vue"
        ).read_text(encoding="utf-8"))
        self.assertIn("'/'", router)
        self.assertNotIn("redirect: '/practice'", router)
        self.assertIn("overview: '/'", tabs)
        self.assertIn("overview: '总览'", tabs)
        self.assertIn("path === '/' && normalizedQuery", tabs)
        for activation in (
            "activateIndices()",
            "activateNiuOneMainline()",
            "activatePracticeCandidates()",
            "activatePractice()",
        ):
            self.assertIn(activation, component)
        for deactivation in (
            "deactivateIndices()",
            "deactivateNiuOneMainline()",
            "deactivatePracticeCandidates()",
            "deactivatePractice()",
        ):
            self.assertIn(deactivation, component)
        self.assertNotIn("triggerManualCycle", component)
        self.assertNotIn("resumeTrading", component)
        self.assertNotIn("refreshNiuOneMainline", component)
        self.assertIn('aria-label="核心决策指标"', component)
        self.assertIn("practiceState.loaded && account.value.available", component)
        self.assertIn("account.dailyPnl", component)
        self.assertIn("account.dailyPnlPct", component)
        self.assertIn("当日收益待补充", component)
        self.assertIn("document.body.classList.add('overview-terminal-open')", component)
        self.assertIn("document.body.classList.remove('overview-terminal-open')", component)
        self.assertIn("--overview-viewport-height", component)
        self.assertIn(':data-layout="viewportMode.layout"', component)
        self.assertIn(':data-density="viewportMode.density"', component)
        self.assertIn(':data-mainline-layout="mainlinePanelMode"', component)
        self.assertIn("mainlineResizeObserver.observe(mainlinePanel.value)", component)
        self.assertIn('[data-mainline-layout="summary"] .overview-theme-list', component)
        self.assertIn('[data-mainline-layout="compact"] .overview-theme-row:nth-child(n + 4)', component)
        self.assertIn('[data-mainline-layout="summary"] .overview-theme-row:nth-child(n + 3)', component)
        self.assertNotIn("todayTheme", component)
        self.assertNotIn("今日领涨", component)
        self.assertNotIn("primaryTheme", component)
        self.assertNotIn("跨日确认主线", component)
        self.assertNotIn("overview-mainline-hero", component)
        self.assertNotIn(".overview-command-head::after", component)
        self.assertNotIn(".overview-kpi::before", component)
        self.assertIn(
            ':global(html[data-theme="dark"] .overview-page)',
            component,
        )
        self.assertNotIn(
            ':global(html[data-theme="dark"]) .overview-page',
            component,
        )
        self.assertIn("@media (min-width: 721px)", component)
        self.assertIn(":global(body.overview-terminal-open) { overflow: hidden; }", component)
        self.assertIn(":payload=\"indicesState.marketBreadth\" terminal", component)
        self.assertIn("terminal: { type: Boolean, default: false }", breadth_component)
        self.assertIn("const showVolume = ref(!props.terminal)", breadth_component)
        self.assertIn("const height = props.terminal", breadth_component)
        self.assertIn("@media (max-width: 720px)", component)
        self.assertIn("@media (prefers-reduced-motion: reduce)", component)


if __name__ == "__main__":
    unittest.main()
