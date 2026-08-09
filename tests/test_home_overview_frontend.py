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
DASHBOARD_HEADER_STYLES_PATH = ROOT / "frontend" / "dashboard-header.css"
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
const previousBreadth = module.overviewBreadth({{
  displaying_previous_trading_day: true,
  display_date: '2026-08-07',
  latest: {{
    generated_at: '2026-08-07 15:00:00',
    red: 3200,
    green: 1800,
    limit_up: 60,
    limit_down: 4,
  }},
}});
const fallbackBreadth = module.overviewBreadth({{latest: {{}}}}, {{
  generated_at: '2026-08-07 15:11:31',
  breadth_score: 53.37,
  limit_up: 77,
  limit_down: 5,
  median_change_pct: 0.154,
}});
const industryNetFlow = module.overviewMoneyFlowNet({{
  inflow: [{{net_flow_yi: 12}}, {{net_flow_yi: 8}}],
  outflow: [{{net_flow_yi: -6}}],
}});
const candidates = module.overviewCandidates([
  {{code: 'low', score: 4, entry_threshold: 8}},
  {{code: 'mid', score: 7.5, entry_threshold: 8}},
  {{code: 'blocked', score: 9, entry_threshold: 8, hard_blockers: ['结构未确认']}},
  {{code: 'high', score: 8.2, entry_threshold: 8, actionable: true, best_strategy: 'niu_leader'}},
]);
const previousDayCandidates = module.overviewCandidates([
  {{code: 'history', score: 9, entry_threshold: 8, actionable: true}},
]);
const uncappedCandidates = module.overviewCandidates(
  Array.from({{length: 10}}, (_, index) => ({{
    code: `candidate-${{index + 1}}`,
    score: 10 - index / 10,
    entry_threshold: 8,
    actionable: true,
  }})),
);
const candidatePeriods = [
  module.overviewCandidatePeriod('2026-08-07 15:00:00', {{
    date: '2026-08-09', previous_trading_day: '2026-08-07',
  }}),
  module.overviewCandidatePeriod('2026-08-06 15:00:00', {{
    date: '2026-08-09', previous_trading_day: '2026-08-07',
  }}),
  module.overviewCandidatePeriod('2026-08-09 10:00:00', {{
    date: '2026-08-09', previous_trading_day: '2026-08-07',
  }}),
];
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
const flowRowLimits = [1000, 800, 650, 500].map(module.overviewFlowRowLimit);
const mainlinePayload = {{
  themes: [{{
    industry: 'CRO',
    score: 83.8,
    niuone_lifecycle_label: '主线高潮',
    effective_breadth_pct: 55.3,
    today_strength_score: 91.9,
    today_median_change_pct: 12.2,
    strong_stock_count: 21,
    confirmation_count: 3,
    strong_stocks: [
      {{code: '301047', name: '义翘神州'}},
      {{code: '600721', name: '百花医药'}},
      {{code: '300725', name: '药石科技'}},
    ],
  }}],
  today_themes: [{{
    industry: '机器人',
    score: 72.5,
    niuone_lifecycle_label: '主线启动',
    today_strength_score: 96.4,
    today_adjusted_breadth_pct: 68.2,
    today_median_change_pct: 5.6,
    today_attributed_up_count: 18,
    today_leader_stock: {{code: '300024', name: '机器人', change_pct: 12.4}},
    today_leaders: [
      {{code: '300024', name: '机器人', change_pct: 12.4}},
      {{code: '002747', name: '埃斯顿', change_pct: 8.1}},
    ],
  }}],
}};
const themes = module.overviewThemes(mainlinePayload);
const todayThemes = module.overviewThemes(mainlinePayload, 5, 'today');
const practiceMarketSummaries = [
  module.overviewPracticeMarketSummary({{
    available: true,
    summary: '资金回流成长方向，市场赚钱效应有所修复。',
  }}),
  module.overviewPracticeMarketSummary({{
    running: true,
    stage_label: '正在抓取实时盘面',
  }}),
  module.overviewPracticeMarketSummary({{loading: false}}),
];
console.log(JSON.stringify({{
  zeroAccount,
  profitableAccount,
  flatDailyAccount,
  closedDayAccount,
  missingBreadth,
  breadth,
  previousBreadth,
  fallbackBreadth,
  industryNetFlow,
  candidateOrder: candidates.map(item => item.code),
  candidateLabels: candidates.map(item => item.tierLabel),
  previousDayCandidates,
  uncappedCandidateCount: uncappedCandidates.length,
  candidatePeriods,
  indexOrder: indices.map(item => item.key),
  missingNumber: module.formatOverviewNumber(null),
  viewportModes,
  mainlinePanelModes,
  flowRowLimits,
  themes,
  todayThemes,
  practiceMarketSummaries,
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
        self.assertTrue(payload["previousBreadth"]["previousTradingDay"])
        self.assertEqual(payload["previousBreadth"]["displayDate"], "2026-08-07")
        self.assertEqual(payload["previousBreadth"]["advancingPct"], 64)
        self.assertTrue(payload["fallbackBreadth"]["available"])
        self.assertFalse(payload["fallbackBreadth"]["countsAvailable"])
        self.assertEqual(payload["fallbackBreadth"]["advancingPct"], 53.37)
        self.assertEqual(payload["fallbackBreadth"]["limitUp"], 77)
        self.assertEqual(payload["fallbackBreadth"]["limitDown"], 5)
        self.assertEqual(payload["fallbackBreadth"]["medianChangePct"], 0.154)
        self.assertEqual(payload["industryNetFlow"], 14)
        self.assertEqual(payload["candidateOrder"], ["high", "blocked", "mid", "low"])
        self.assertEqual(
            payload["candidateLabels"],
            ["交易达标", "未达标", "待确认", "仅观察"],
        )
        self.assertEqual(payload["previousDayCandidates"][0]["tier"], "high")
        self.assertEqual(payload["previousDayCandidates"][0]["tierLabel"], "交易达标")
        self.assertEqual(payload["uncappedCandidateCount"], 10)
        self.assertEqual(
            payload["candidatePeriods"],
            [
                {
                    "historical": True,
                    "previousTradingDay": True,
                    "generatedDate": "2026-08-07",
                    "label": "上一交易日候选 08-07",
                },
                {
                    "historical": True,
                    "previousTradingDay": False,
                    "generatedDate": "2026-08-06",
                    "label": "历史候选 08-06",
                },
                {
                    "historical": False,
                    "previousTradingDay": False,
                    "generatedDate": "2026-08-09",
                    "label": "",
                },
            ],
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
        self.assertEqual(payload["flowRowLimits"], [6, 5, 4, 3])
        self.assertEqual(payload["themes"][0]["todayScore"], 91.9)
        self.assertEqual(payload["themes"][0]["medianChangePct"], 12.2)
        self.assertEqual(payload["themes"][0]["strongStockCount"], 21)
        self.assertEqual(payload["themes"][0]["confirmationCount"], 3)
        self.assertEqual(payload["themes"][0]["followers"], ["百花医药", "药石科技"])
        self.assertEqual(len(payload["themes"][0]["coreStocks"]), 3)
        self.assertEqual(payload["themes"][0]["coreStocks"][0]["code"], "301047")
        self.assertEqual(payload["todayThemes"][0]["rankingKey"], "today")
        self.assertEqual(payload["todayThemes"][0]["displayName"], "机器人")
        self.assertEqual(payload["todayThemes"][0]["displayScore"], 96.4)
        self.assertEqual(payload["todayThemes"][0]["comparisonScore"], 72.5)
        self.assertEqual(payload["todayThemes"][0]["breadth"], 68.2)
        self.assertEqual(payload["todayThemes"][0]["strongStockCount"], 18)
        self.assertEqual(payload["todayThemes"][0]["leaderBadge"], "领涨")
        self.assertEqual(payload["todayThemes"][0]["coreStocks"][0]["code"], "300024")
        self.assertEqual(
            payload["practiceMarketSummaries"],
            [
                "资金回流成长方向，市场赚钱效应有所修复。",
                "正在抓取实时盘面",
                "模拟交易盘面资料待更新",
            ],
        )

    def test_overview_route_is_lazy_read_only_and_lifecycle_safe(self):
        component = OVERVIEW_PATH.read_text(encoding="utf-8")
        dashboard_header_styles = DASHBOARD_HEADER_STYLES_PATH.read_text(encoding="utf-8")
        display_model = DISPLAY_PATH.read_text(encoding="utf-8")
        breadth_component = (
            WEB_SRC / "components" / "indices" / "MarketBreadthChart.vue"
        ).read_text(encoding="utf-8")
        market_overview = (
            WEB_SRC / "components" / "indices" / "MarketOverview.vue"
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
        self.assertIn("if (path === '/')", tabs)
        self.assertIn("return PATH_CATEGORIES[path] || ''", tabs)
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
        self.assertIn('<h2 id="overviewTitle">盘面监测总览</h2>', component)
        self.assertNotIn("今日市场作战台", component)
        self.assertNotIn("A股决策中枢", component)
        self.assertNotIn("overview-eyebrow", component)
        self.assertNotIn("先判断市场环境", component)
        self.assertIn('aria-label="模拟交易盘面总结"', component)
        self.assertIn("practiceState.marketSummary,", component)
        self.assertIn("practiceState.marketSummaryGenerating,", component)
        self.assertNotIn("overviewMarketSummary", component)
        self.assertIn("practiceState.loaded && account.value.available", component)
        self.assertIn("account.dailyPnl", component)
        self.assertIn("account.dailyPnlPct", component)
        self.assertIn("当日收益待补充", component)
        self.assertNotIn("账户与风控", component)
        self.assertNotIn("overview-account-panel", component)
        self.assertNotIn("overview-side-stack", component)
        self.assertNotIn("accountPnlTone", component)
        self.assertNotIn("readinessTone", component)
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
        self.assertIn('[data-mainline-layout="full"] .overview-theme-list', component)
        self.assertIn("title: '今日排名'", component)
        self.assertIn("title: '结构排名'", component)
        self.assertIn("overviewThemes(mainlinePayload.value, 5, 'today')", component)
        self.assertIn("overviewThemes(mainlinePayload.value, 5, 'structure')", component)
        self.assertIn('class="overview-theme-rankings"', component)
        self.assertIn("overview-theme-table-head", component)
        self.assertIn("题材 / 周期", component)
        self.assertNotIn('<span role="columnheader">序</span>', component)
        self.assertNotIn("overview-rank", component)
        self.assertIn("overview-theme-leader", component)
        self.assertIn("overview-theme-lifecycle", component)
        self.assertIn("overview-theme-meta", component)
        self.assertIn("核心股 / 梯队", component)
        self.assertNotIn("theme.followers.join(' · ')", component)
        self.assertNotIn("核心梯队待确认", component)
        self.assertIn("toggleThemeStocks(ranking.key, index, $event)", component)
        self.assertIn(":aria-expanded=\"isThemeExpanded(ranking.key, index)\"", component)
        self.assertIn('<Teleport to="body">', component)
        self.assertIn("overview-theme-stock-popover", component)
        self.assertIn("overview-theme-leader-toggle", component)
        self.assertIn(".overview-theme-leader-toggle { font-size: 10px; padding: 2px 6px; }", component)
        self.assertGreaterEqual(component.count("<span>{{ themeLeader(theme) }}</span>"), 2)
        self.assertNotIn("查看{{ theme.coreStocks.length }}只", component)
        self.assertIn("{{ expandedTheme.stockListLabel }}", component)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 42px 46px;", component)
        self.assertIn(".overview-theme-stock-list-head span:last-child { text-align: left; }", component)
        self.assertIn("Math.min(208, viewportWidth - 16)", component)
        self.assertIn("handleThemeStockPointerDown", component)
        self.assertIn("handleThemeStockKeydown", component)
        self.assertIn("position: fixed;", component)
        self.assertNotIn("overview-theme-stock-expand", component)
        self.assertIn("v-for=\"(stock, stockIndex) in expandedTheme.coreStocks\"", component)
        stock_name_position = component.index("<strong>{{ stock.name || '名称待补充' }}</strong>")
        leader_badge_position = component.index('<b v-if="stockIndex === 0">{{ expandedTheme.leaderBadge }}</b>')
        self.assertLess(stock_name_position, leader_badge_position)
        self.assertNotIn("核心股 {{ theme.coreStocks.length }}只", component)
        self.assertIn("{{ theme.comparisonLabel }} {{ formatOverviewNumber(theme.comparisonScore, 1) }}", component)
        self.assertIn("中位 {{ formatOverviewPercent(theme.medianChangePct, 1, true) }}", component)
        self.assertIn("overview-theme-metric-track", component)
        self.assertIn("themeMetricPosition(theme.displayScore)", component)
        self.assertIn(".overview-theme-score b { color: var(--overview-mainline-accent); }", component)
        self.assertIn(".overview-theme-breadth b { color: var(--overview-text); }", component)
        self.assertIn(".overview-theme-leader-toggle svg { color: var(--overview-mainline-accent); }", component)
        self.assertIn(".overview-theme-score .overview-theme-metric-track i { background: var(--overview-mainline-accent); }", component)
        for mainline_tone in (
            "--overview-mainline-accent: #46627c;",
            "--overview-mainline-secondary: #4f5d69;",
            "--overview-mainline-accent: #9bb1c5;",
            "--overview-mainline-secondary: #aab5bf;",
        ):
            self.assertIn(mainline_tone, component)
        self.assertIn("border-left: 1px solid var(--overview-border-strong);", component)
        self.assertIn("{{ formatOverviewPercent(theme.breadth, 0) }}", component)
        self.assertNotIn("overview-theme-metrics", component)
        self.assertNotIn(".overview-theme-row:last-child:nth-child(odd)", component)
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
        for subdued_color in (
            "--overview-accent: #536b82;",
            "--overview-up: #b6534e;",
            "--overview-down: #34745d;",
            "--overview-warning: #7b5e30;",
            "--overview-accent: #7b8fa3;",
            "--overview-up: #d06e68;",
            "--overview-down: #559a7f;",
            "--overview-warning: #b18b52;",
        ):
            self.assertIn(subdued_color, component)
        for saturated_color in ("#79a7ff", "#ff7d75", "#45cb91", "#f2bd55"):
            self.assertNotIn(saturated_color, component)
        self.assertEqual(component.count("--overview-faint: #66727e;"), 2)
        self.assertEqual(component.count("--overview-faint: #7d8995;"), 2)
        self.assertIn("--market-breadth-limit-up: var(--overview-up);", component)
        self.assertIn("--market-breadth-actual-turnover: var(--overview-accent);", component)
        self.assertIn(
            ".overview-tier.high { background: var(--overview-surface-strong); border-color: var(--overview-border-strong); color: var(--overview-text); }",
            component,
        )
        for readable_terminal_text in (
            ".overview-kpi-label { font-size: 9px; }",
            ".overview-index-tile time { font-size: 9px; }",
            ".overview-theme-table-head { font-size: 9px; padding: 0 1px 3px; }",
            ".overview-theme-lifecycle { font-size: 9px; padding-left: 4px; }",
            ".overview-theme-metric small { font-size: 9px; }",
            ".overview-candidate-table-head { font-size: 9px; padding: 0 5px 3px; }",
            ".overview-flow-row { flex: 1 1 0; font-size: 9px; min-height: 20px; }",
        ):
            self.assertIn(readable_terminal_text, component)
        self.assertNotIn(
            ':global(html[data-theme="dark"]) .overview-page',
            component,
        )
        self.assertIn("@media (min-width: 721px)", component)
        self.assertIn(
            ':global(html:not([data-theme="tongdaxin"]) body.overview-terminal-open) { overflow: hidden; }',
            component,
        )
        self.assertNotIn(':global(body.overview-terminal-open header)', component)
        self.assertNotIn('body.overview-terminal-open header)', component)
        self.assertIn(
            'html:not([data-theme="tongdaxin"]) .dashboard-site-header {',
            dashboard_header_styles,
        )
        self.assertIn(
            'html:not([data-theme="tongdaxin"]) .dashboard-site-header .dashboard-brand { gap:7px; font-size:19px; }',
            dashboard_header_styles,
        )
        self.assertIn(
            'html:not([data-theme="tongdaxin"]) .dashboard-site-header .dashboard-brand-logo { width:30px; height:30px; }',
            dashboard_header_styles,
        )
        self.assertIn(
            'html:not([data-theme="tongdaxin"]) .dashboard-site-header .category-tabs { margin-top:5px; padding:2px; }',
            dashboard_header_styles,
        )
        self.assertIn(":payload=\"indicesState.marketBreadth\" terminal", component)
        self.assertIn("terminal: { type: Boolean, default: false }", breadth_component)
        self.assertIn("const showVolume = ref(!props.terminal)", breadth_component)
        self.assertIn("const height = props.terminal", breadth_component)
        self.assertIn("props.payload.displaying_previous_trading_day", breadth_component)
        self.assertIn("最近交易日数据", breadth_component)
        self.assertIn('previousDayLabel && !terminal', breadth_component)
        self.assertNotIn("breadthPeriodLabel", component)
        self.assertNotIn("最近交易日", component)
        self.assertIn("overviewCandidatePeriod", component)
        self.assertIn("上一交易日候选", display_model)
        self.assertNotIn("历史参考", display_model)
        for candidate_heading in ("涨跌幅", "题材 / 行业"):
            self.assertIn(candidate_heading, component)
        self.assertIn("overview-candidate-wide-only", component)
        self.assertIn("overview-candidate-compact-only", component)
        self.assertIn("grid-auto-rows: minmax(0, 1fr)", component)
        self.assertIn(
            'grid-template-areas:\n      "market flow"\n      "mainline candidate";',
            component,
        )
        for panel_area in (
            ".overview-market-panel { grid-area: market; }",
            ".overview-flow-panel { grid-area: flow; }",
            ".overview-mainline-panel { grid-area: mainline; }",
            ".overview-candidate-panel { grid-area: candidate; }",
        ):
            self.assertIn(panel_area, component)
        self.assertNotIn("candidateState.strategyMeta,\n  5,", component)
        self.assertIn(
            "grid-template-columns: repeat(6, minmax(0, 1fr))",
            component,
        )
        self.assertIn("overview-update-time", component)
        self.assertIn("overviewPreviousTradingDayLabel", component)
        self.assertIn("数据基准：上一交易日", component)
        self.assertIn("overviewFlowRowLimit", component)
        self.assertIn("flowRowLimit.value", component)
        self.assertIn(".overview-flow-columns { flex: 1 1 0;", component)
        self.assertIn(".overview-flow-columns > div { display: flex; flex-direction: column;", component)
        self.assertIn(".overview-flow-row { flex: 1 1 0;", component)
        self.assertIn("主要行业主力净额", component)
        self.assertIn("overviewMoneyFlowNet", component)
        self.assertIn("overview-breadth-unavailable", component)
        self.assertIn("flex: 1 1 auto; min-height: 0; width: 100%;", component)
        self.assertIn("日内曲线暂无完整采样", component)
        self.assertNotIn("overview-breadth-track", component)
        self.assertNotIn("收盘涨跌停统计", component)
        self.assertIn(
            "<span>炸板 {{ formatOverviewNumber(breadth.brokenLimit, 0) }}只</span>",
            component,
        )
        self.assertNotIn('v-if="breadth.brokenLimit != null"', component)
        self.assertNotIn("overview-section-kicker", component)
        self.assertIn("--overview-terminal-left: minmax(0, 1.55fr)", component)
        self.assertIn("--overview-terminal-right: minmax(380px, .9fr)", component)
        self.assertIn(
            "grid-template-columns: var(--overview-terminal-left) var(--overview-terminal-right)",
            component,
        )
        self.assertIn("grid-template-rows: minmax(0, .9fr) minmax(0, 1.1fr)", component)
        self.assertNotIn("minmax(0, 1.16fr) minmax(0, .84fr)", component)
        for english_heading in (
            "MARKET PULSE",
            "MAINLINE",
            "RISK BOOK",
            "OPPORTUNITY SET",
            "CAPITAL FLOW",
        ):
            self.assertNotIn(english_heading, component)
        self.assertNotIn("moneyFlowPeriodLabel", component)
        self.assertNotIn("上一交易日资金", component)
        self.assertIn("props.moneyFlow.displaying_previous_trading_day", market_overview)
        self.assertIn("上一交易日资金", market_overview)
        self.assertIn("@media (max-width: 720px)", component)
        self.assertIn("@media (prefers-reduced-motion: reduce)", component)
        for square_overview_surface in (
            ':global(html[data-corners="square"]) .overview-command-head,',
            ':global(html[data-corners="square"]) .overview-theme-stock-popover,',
            ':global(html[data-corners="square"]) .overview-tier,',
            ':global(html[data-corners="square"]) .overview-chart-wrap :deep(.market-breadth-card),',
        ):
            self.assertIn(square_overview_surface, component)
        self.assertIn("border-radius: 0 !important;", component)
        self.assertIn("状态圆点和数据进度轨道保留原有几何语义", component)
        for professional_terminal_style in (
            "--overview-surface-raised: #f3f5f7;",
            "--overview-border: #cfd6dd;",
            "--overview-border-strong: #aeb9c4;",
            "--overview-border: #303c47;",
            "--overview-border-strong: #43515e;",
            "box-shadow: none;",
            ".overview-panel { border-color: var(--overview-border-strong); }",
            ".overview-theme-table-head { background: var(--overview-surface-raised);",
            ".overview-candidate-table-head { background: var(--overview-surface-raised);",
        ):
            self.assertIn(professional_terminal_style, component)
        self.assertIn(
            'html:not([data-theme="tongdaxin"]) .dashboard-site-header :where(.settings-link,.header-link,.version-status,.refresh-pill,.theme-toggle,.category-tabs,.tab) { box-shadow:none; }',
            dashboard_header_styles,
        )


if __name__ == "__main__":
    unittest.main()
