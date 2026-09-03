from __future__ import annotations

# Field-level policy is intentionally explicit rather than provider-wide priority.
SECTOR_FIELD_POLICY = {
    "change_pct": "niuone_then_a_stock_data",
    "advancing": "niuone_then_a_stock_data",
    "declining": "niuone_then_a_stock_data",
    "breadth_ratio": "niuone_then_a_stock_data",
    "leader_name": "niuone_then_a_stock_data",
    "leader_change": "niuone_then_a_stock_data",
    "flow_1d": "niuone_then_a_stock_data",
    "flow_ratio_1d": "niuone_then_a_stock_data",
    "flow_5d": "a_stock_data",
    "flow_ratio_5d": "a_stock_data",
    "flow_10d": "a_stock_data",
    "flow_ratio_10d": "a_stock_data",
}

MARKET_FIELD_POLICY = {
    "advancing": "niuone_then_a_stock_data",
    "declining": "niuone_then_a_stock_data",
    "limit_up": "niuone_then_a_stock_data",
    "limit_down": "niuone_then_a_stock_data",
    "broken_limit": "a_stock_data",
    "broken_rate": "a_stock_data",
    "yesterday_limit_up_count": "a_stock_data",
    "yesterday_limit_up_positive": "a_stock_data",
    "yesterday_limit_up_negative": "a_stock_data",
    "yesterday_limit_up_success_rate": "a_stock_data",
    "turnover": "niuone_then_a_stock_data",
    "turnover_change": "niuone_then_a_stock_data",
}

# EastMoney aggregate flow endpoints are not historical series.
FLOW_PERIODS = ("1d", "5d", "10d")
