#!/usr/bin/env python3
"""Generate a deterministic U.S. institutional-rating report from FMP.

Usage:
    us_rating_report.py              # generates, stores, and prints report
    us_rating_report.py --store-only
    us_rating_report.py --test       # fetches a small live sample without storing
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from market_data.fmp_ratings import (
    DEFAULT_BASE_URL as FMP_DEFAULT_BASE_URL,
    FmpRatingsError,
    GradeEvent,
    PriceTargetEvent,
    Quote,
    fetch_batch_quotes,
    fetch_latest_grades,
    fetch_latest_price_targets,
)
from niuone_paths import get_dashboard_env_file, get_dashboard_home


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def load_dashboard_env() -> None:
    allowed = {
        "FMP_API_BASE_URL",
        "FMP_API_KEY",
        "FMP_RATING_MAX_RESULTS",
        "US_RATING_DEADLINE_SECONDS",
        "US_RATING_REQUEST_TIMEOUT_SECONDS",
    }
    path = get_dashboard_env_file(PROJECT_ROOT)
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("\"'")


load_dashboard_env()
DASHBOARD_HOME = get_dashboard_home(PROJECT_ROOT)
os.environ.setdefault("DASHBOARD_HOME", str(DASHBOARD_HOME))
CN_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
US_EASTERN_TZ = ZoneInfo("America/New_York")

try:
    import push_history
except Exception:
    push_history = None


JOB_ID = "fd0b807138f4"
JOB_NAME = "每日美股机构买入评级汇报"
FMP_FEED_LIMIT = 250
FMP_FEED_PAGE_SIZE = 10


def _int_env(
    name: str,
    default: int,
    *,
    min_value: int,
    max_value: int,
) -> int:
    try:
        value = int(str(os.environ.get(name) or "").strip())
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


FMP_API_BASE_URL = str(
    os.environ.get("FMP_API_BASE_URL") or FMP_DEFAULT_BASE_URL
).strip().rstrip("/")
FMP_API_KEY = str(os.environ.get("FMP_API_KEY") or "").strip()
FMP_RATING_MAX_RESULTS = _int_env(
    "FMP_RATING_MAX_RESULTS",
    10,
    min_value=1,
    max_value=50,
)
US_RATING_DEADLINE_SECONDS = _int_env(
    "US_RATING_DEADLINE_SECONDS",
    120,
    min_value=30,
    max_value=600,
)
US_RATING_REQUEST_TIMEOUT_SECONDS = _int_env(
    "US_RATING_REQUEST_TIMEOUT_SECONDS",
    30,
    min_value=5,
    max_value=120,
)


_POSITIVE_GRADE_PATTERNS = (
    r"\bstrong\s*buy\b",
    r"\bconviction\s*buy\b",
    r"\bbuy\b",
    r"\boverweight\b",
    r"\boutperform(?:er)?\b",
    r"\bmarket\s+outperform\b",
    r"\bsector\s+outperform\b",
    r"\bpositive\b",
    r"\baccumulate\b",
    r"\badd\b",
)


def _compact_text(value: str, *, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def is_positive_grade(value: str) -> bool:
    grade = _compact_text(value).lower()
    if not grade or "underperform" in grade or "underweight" in grade:
        return False
    return any(re.search(pattern, grade) for pattern in _POSITIVE_GRADE_PATTERNS)


def is_negative_action(value: str) -> bool:
    action = _compact_text(value).lower()
    return any(token in action for token in ("downgrade", "down", "lower"))


def grade_strength(value: str) -> int:
    grade = _compact_text(value).lower()
    if "strong buy" in grade or "conviction buy" in grade:
        return 40
    if "buy" in grade:
        return 35
    if "overweight" in grade or "outperform" in grade:
        return 30
    if "positive" in grade or "accumulate" in grade or re.search(r"\badd\b", grade):
        return 20
    return 0


def action_strength(event: GradeEvent) -> int:
    action = event.action.lower()
    previous_positive = is_positive_grade(event.previous_grade)
    if "upgrade" in action or action == "up":
        return 55
    if any(token in action for token in ("init", "start", "new")):
        return 45
    if not previous_positive and event.previous_grade:
        return 40
    if any(token in action for token in ("hold", "maintain", "reit")):
        return 20
    return 25


def _deduplicate(events: Iterable[GradeEvent]) -> list[GradeEvent]:
    result: list[GradeEvent] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for event in sorted(events, key=lambda item: item.published_at, reverse=True):
        key = (
            event.symbol,
            _company_key(event.grading_company),
            event.new_grade.lower(),
            event.action.lower(),
            event.published_at.isoformat(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def select_latest_positive_events(events: Iterable[GradeEvent]) -> tuple[date | None, list[GradeEvent]]:
    valid = [event for event in _deduplicate(events) if event.symbol]
    if not valid:
        return None, []
    latest_day = max(event.published_at.astimezone(US_EASTERN_TZ).date() for event in valid)
    selected = [
        event
        for event in valid
        if event.published_at.astimezone(US_EASTERN_TZ).date() == latest_day
        and is_positive_grade(event.new_grade)
        and not is_negative_action(event.action)
    ]
    return latest_day, selected


def match_price_target(
    event: GradeEvent,
    targets: Iterable[PriceTargetEvent],
) -> PriceTargetEvent | None:
    company = _company_key(event.grading_company)
    candidates: list[tuple[int, float, PriceTargetEvent]] = []
    for target in targets:
        if target.symbol != event.symbol or target.price_target is None:
            continue
        delta = abs((target.published_at - event.published_at).total_seconds())
        if delta > 3 * 24 * 60 * 60:
            continue
        target_company = _company_key(target.analyst_company)
        company_match = bool(
            company
            and target_company
            and (company == target_company or company in target_company or target_company in company)
        )
        candidates.append((1 if company_match else 0, -delta, target))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best = candidates[0]
    # A symbol-only match is safe only when it was published very close to the
    # grade event; otherwise it may belong to a different analyst action.
    if best[0] == 0 and -best[1] > 6 * 60 * 60:
        return None
    return best[2]


def _target_upside(
    target: PriceTargetEvent | None,
    quote: Quote | None,
    event: GradeEvent,
) -> float | None:
    if target is None or target.price_target is None:
        return None
    reference_price = (
        quote.price if quote and quote.price else target.price_when_posted or event.price_when_posted
    )
    if not reference_price:
        return None
    return (target.price_target / reference_price - 1.0) * 100.0


def _event_score(
    event: GradeEvent,
    *,
    cluster_size: int,
    target: PriceTargetEvent | None,
    quote: Quote | None,
) -> float:
    score = float(grade_strength(event.new_grade) + action_strength(event))
    score += min(30, max(0, cluster_size - 1) * 10)
    upside = _target_upside(target, quote, event)
    if upside is not None:
        if upside >= 20:
            score += 25
        elif upside >= 10:
            score += 15
        elif upside > 0:
            score += 5
    return score


def rank_rating_groups(
    events: Iterable[GradeEvent],
    targets: Iterable[PriceTargetEvent],
    quotes: dict[str, Quote],
) -> list[tuple[str, list[GradeEvent], PriceTargetEvent | None, Quote | None]]:
    grouped: dict[str, list[GradeEvent]] = defaultdict(list)
    for event in events:
        grouped[event.symbol].append(event)
    ranked = []
    target_list = list(targets)
    for symbol, symbol_events in grouped.items():
        symbol_events.sort(
            key=lambda event: (grade_strength(event.new_grade), action_strength(event), event.published_at),
            reverse=True,
        )
        representative = symbol_events[0]
        quote = quotes.get(symbol)
        target = match_price_target(representative, target_list)
        score = _event_score(
            representative,
            cluster_size=len(symbol_events),
            target=target,
            quote=quote,
        )
        ranked.append((score, representative.published_at, symbol, symbol_events, target, quote))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[2:] for item in ranked]


def _action_description(event: GradeEvent) -> str:
    previous = _compact_text(event.previous_grade) or "未披露"
    current = _compact_text(event.new_grade) or "未披露"
    action = _compact_text(event.action) or "评级更新"
    return f"{_compact_text(event.grading_company) or '未披露机构'}：{previous} → {current}（{action}）"


def _format_target(
    event: GradeEvent,
    target: PriceTargetEvent | None,
    quote: Quote | None,
) -> str:
    if target is None or target.price_target is None:
        if quote and quote.price:
            return f"本次 FMP 评级记录未附目标价；当前参考价 ${quote.price:.2f}"
        return "本次 FMP 评级记录未附目标价"
    parts = [f"${target.price_target:.2f}"]
    reference_price = quote.price if quote and quote.price else target.price_when_posted or event.price_when_posted
    if reference_price:
        upside = (target.price_target / reference_price - 1.0) * 100.0
        parts.append(f"参考价 ${reference_price:.2f}，潜在空间 {upside:+.1f}%")
    return "；".join(parts)


def _attention_type(events: list[GradeEvent]) -> str:
    if len(events) >= 2:
        return "短线催化 / 机构集中关注"
    action = events[0].action.lower()
    if "upgrade" in action or action == "up" or "init" in action:
        return "短线催化"
    return "中线趋势观察"


def format_report(
    latest_day: date | None,
    ranked_groups: Iterable[
        tuple[str, list[GradeEvent], PriceTargetEvent | None, Quote | None]
    ],
    *,
    now: datetime,
    max_results: int,
    feed_limited: bool = False,
) -> str:
    local_dt = now.astimezone(CN_TZ)
    title = f"牛牛大王，美股机构买入评级日报（{local_dt:%Y年%m月%d日}）"
    groups = list(ranked_groups)[: max(1, max_results)]
    if not groups:
        source_day = latest_day.isoformat() if latest_day else "未知"
        content = (
            f"{title}\n\n"
            f"FMP 最新评级批次日期：{source_day}。"
            "本批次没有符合本地买入倾向规则的机构评级。"
        )
        if feed_limited:
            content += (
                "\n\n数据覆盖提示：当前 FMP 权限仅返回最新 10 条评级，"
                "本日报基于有限样本生成，可能遗漏同批次的其他机构评级。"
            )
        return content

    lines = [
        title,
        "",
        (
            f"数据源：Financial Modeling Prep（FMP）；评级批次：{latest_day.isoformat() if latest_day else '未知'}；"
            f"本地规则筛选出 {len(groups)} 只股票。排序综合考虑评级强度、升级/新覆盖、机构集中度和可用目标价空间。"
        ),
        "",
    ]
    if feed_limited:
        lines.extend(
            [
                "数据覆盖提示：当前 FMP 权限仅返回最新 10 条评级，本日报基于有限样本生成，可能遗漏同批次的其他机构评级。",
                "",
            ]
        )
    for symbol, events, target, quote in groups:
        representative = events[0]
        company_name = _compact_text(quote.name if quote and quote.name else symbol, limit=120)
        firms = []
        for event in events:
            firm = _compact_text(event.grading_company) or "未披露机构"
            if firm not in firms:
                firms.append(firm)
        firm_text = "、".join(firms[:4])
        if len(firms) > 4:
            firm_text += f"等 {len(firms)} 家"
        action_text = "；".join(_action_description(event) for event in events[:3])
        if len(events) > 3:
            action_text += f"；另有 {len(events) - 3} 条同日买入倾向评级"
        titles = []
        for event in events:
            news_title = _compact_text(event.news_title)
            if news_title and news_title not in titles:
                titles.append(news_title)
        catalyst = "；".join(titles[:2]) or "FMP 记录了机构买入倾向评级，但未提供完整研报摘要"
        lines.extend(
            [
                f"- {symbol} / {company_name}",
                f"  机构/分析师：{firm_text}",
                f"  评级动作：{action_text}",
                f"  目标价：{_format_target(representative, target, quote)}",
                f"  核心理由/催化剂：{catalyst}",
                "  风险点：FMP 结构化评级不包含完整研报风险披露；评级可能滞后或发生修订，需结合基本面、估值与市场波动复核",
                f"  适合关注类型：{_attention_type(events)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _remaining_timeout(deadline: float, *, max_retries: int) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 1:
        raise FmpRatingsError("FMP 评级任务超过本地总时限")
    retry_count = max(0, int(max_retries))
    retry_sleep = sum(min(0.5 * (2**attempt), 2.0) for attempt in range(retry_count))
    request_budget = max(1.0, remaining - retry_sleep) / (retry_count + 1)
    return min(float(US_RATING_REQUEST_TIMEOUT_SECONDS), request_budget)


def _fetch_latest_grade_feed(
    *,
    deadline: float,
    max_items: int,
    opener=urlopen,
) -> tuple[list[GradeEvent], bool]:
    """Read the newest complete rating day without requiring a large FMP page."""

    item_limit = max(1, min(FMP_FEED_LIMIT, int(max_items)))
    page_size = min(FMP_FEED_PAGE_SIZE, item_limit)
    page_count = (item_limit + page_size - 1) // page_size
    events: list[GradeEvent] = []
    latest_day: date | None = None
    max_retries = 2

    for page in range(page_count):
        request_limit = min(page_size, item_limit - len(events))
        try:
            page_events = fetch_latest_grades(
                FMP_API_BASE_URL,
                FMP_API_KEY,
                page=page,
                limit=request_limit,
                timeout=_remaining_timeout(deadline, max_retries=max_retries),
                max_retries=max_retries,
                opener=opener,
            )
        except FmpRatingsError as exc:
            if page > 0 and events and "HTTP 402" in str(exc):
                return events, True
            raise
        bounded_page = page_events[:request_limit]
        if not bounded_page:
            break
        events.extend(bounded_page)
        page_days = [
            event.published_at.astimezone(US_EASTERN_TZ).date()
            for event in bounded_page
        ]
        if latest_day is None:
            latest_day = max(page_days)
        if len(bounded_page) < request_limit or any(
            event_day < latest_day for event_day in page_days
        ):
            break

    return events, False


def _fetch_relevant_price_targets(
    selected_events: Iterable[GradeEvent],
    *,
    deadline: float,
    max_items: int,
    opener=urlopen,
) -> list[PriceTargetEvent]:
    """Page the optional target feed until it is older than the match window."""

    selected = list(selected_events)
    if not selected:
        return []
    symbols = {event.symbol for event in selected}
    cutoff = min(event.published_at for event in selected) - timedelta(days=3)
    item_limit = max(1, min(FMP_FEED_LIMIT, int(max_items)))
    page_size = min(FMP_FEED_PAGE_SIZE, item_limit)
    page_count = (item_limit + page_size - 1) // page_size
    targets: list[PriceTargetEvent] = []
    fetched_count = 0
    max_retries = 1

    for page in range(page_count):
        request_limit = min(page_size, item_limit - fetched_count)
        try:
            page_targets = fetch_latest_price_targets(
                FMP_API_BASE_URL,
                FMP_API_KEY,
                page=page,
                limit=request_limit,
                timeout=_remaining_timeout(deadline, max_retries=max_retries),
                max_retries=max_retries,
                opener=opener,
            )
        except FmpRatingsError as exc:
            if page > 0 and "HTTP 402" in str(exc):
                return targets
            raise
        bounded_page = page_targets[:request_limit]
        if not bounded_page:
            break
        fetched_count += len(bounded_page)
        targets.extend(target for target in bounded_page if target.symbol in symbols)
        if len(bounded_page) < request_limit or any(
            target.published_at < cutoff for target in bounded_page
        ):
            break

    return targets


def generate_report(
    test_mode: bool = False,
    *,
    now: datetime | None = None,
    opener=urlopen,
) -> str:
    if not FMP_API_KEY:
        raise FmpRatingsError("请先配置 FMP API Key")
    current = now or datetime.now(timezone.utc)
    deadline = time.monotonic() + US_RATING_DEADLINE_SECONDS
    feed_limit = 10 if test_mode else FMP_FEED_LIMIT
    grade_events, feed_limited = _fetch_latest_grade_feed(
        deadline=deadline,
        max_items=feed_limit,
        opener=opener,
    )
    latest_day, selected = select_latest_positive_events(grade_events)
    if not selected:
        return format_report(
            latest_day,
            [],
            now=current,
            max_results=2 if test_mode else FMP_RATING_MAX_RESULTS,
            feed_limited=feed_limited,
        )

    targets: list[PriceTargetEvent] = []
    quotes: dict[str, Quote] = {}
    try:
        targets = _fetch_relevant_price_targets(
            selected,
            deadline=deadline,
            max_items=feed_limit,
            opener=opener,
        )
    except FmpRatingsError as exc:
        print(f"WARN: FMP 目标价补充不可用：{exc}", file=sys.stderr)
    try:
        optional_retries = 1
        quotes = fetch_batch_quotes(
            FMP_API_BASE_URL,
            FMP_API_KEY,
            {event.symbol for event in selected},
            timeout=_remaining_timeout(deadline, max_retries=optional_retries),
            max_retries=optional_retries,
            opener=opener,
        )
    except FmpRatingsError as exc:
        print(f"WARN: FMP 行情补充不可用：{exc}", file=sys.stderr)

    ranked = rank_rating_groups(selected, targets, quotes)
    return format_report(
        latest_day,
        ranked,
        now=current,
        max_results=2 if test_mode else FMP_RATING_MAX_RESULTS,
        feed_limited=feed_limited,
    )


def write_report_to_db(content: str, now: datetime | None = None) -> int:
    if push_history is None:
        raise RuntimeError("push history database module is unavailable")
    if now is None:
        now = datetime.now(timezone.utc)
    local_dt = now.astimezone(CN_TZ)
    run_key = os.environ.get("NIUONE_CRON_RUN_KEY") or f"{JOB_ID}:{local_dt.strftime('%Y-%m-%d_%H-%M-%S')}"
    source_id = f"cron_output_{JOB_ID}"
    message = {
        "id": push_history.stable_id("us_ratings", JOB_ID, run_key),
        "timestamp": now.timestamp(),
        "time_text": local_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "category": "us_ratings",
        "source_type": "us_ratings",
        "source_id": source_id,
        "source_label": "美股机构买入评级",
        "platform": "dashboard",
        "platform_label": "Dashboard",
        "chat": "us-ratings",
        "external_id": run_key,
        "title": "美股机构买入评级",
        "content": content,
        "chars": len(content),
        "matched": True,
        "kind": "cron_output",
        "delivery": {"mode": "dashboard_database_only", "job_id": JOB_ID},
        "metadata": {
            "job_name": JOB_NAME,
            "run_key": run_key,
            "provider": "financial_modeling_prep",
        },
    }
    count = push_history.upsert_many([message])
    if count != 1:
        raise RuntimeError(f"US rating database write returned {count}")
    return count


def main() -> None:
    test_mode = "--test" in sys.argv
    store_only = "--store-only" in sys.argv

    try:
        content = generate_report(test_mode=test_mode)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        print(f"ERROR: {reason}", file=sys.stderr)
        sys.exit(1)

    if not content.strip():
        print("ERROR: FMP report is empty", file=sys.stderr)
        sys.exit(1)

    if not test_mode:
        now = datetime.now(timezone.utc)
        try:
            write_report_to_db(content, now=now)
        except Exception as exc:
            print(f"ERROR: database write failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            sys.exit(1)

    if not store_only:
        print(content)


if __name__ == "__main__":
    main()
