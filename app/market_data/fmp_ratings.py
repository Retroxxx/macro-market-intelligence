"""Financial Modeling Prep analyst-rating data access.

The client deliberately keeps the FMP API key in an HTTP header so it never
appears in request URLs, exception messages, or scheduler logs.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urlencode, urlsplit


DEFAULT_BASE_URL = "https://financialmodelingprep.com/stable"
DEFAULT_FEED_LIMIT = 100
MAX_FEED_LIMIT = 250
USER_AGENT = "NiuOne/1.0"


class FmpRatingsError(RuntimeError):
    """A safe, user-facing FMP request or response failure."""


@dataclass(frozen=True)
class GradeEvent:
    symbol: str
    published_at: datetime
    grading_company: str
    new_grade: str
    previous_grade: str
    action: str
    news_title: str
    news_url: str
    price_when_posted: float | None


@dataclass(frozen=True)
class PriceTargetEvent:
    symbol: str
    published_at: datetime
    analyst_company: str
    analyst_name: str
    price_target: float | None
    price_when_posted: float | None
    news_title: str


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    price: float | None


UrlOpen = Callable[..., Any]


def normalize_base_url(value: str | None) -> str:
    base_url = str(value or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise FmpRatingsError("FMP API 地址必须是有效的 http(s) URL")
    return base_url


def _bounded_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_FEED_LIMIT
    return max(1, min(MAX_FEED_LIMIT, parsed))


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _transient_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {408, 425, 429, 500, 502, 503, 504}
    return isinstance(
        exc,
        (TimeoutError, socket.timeout, ConnectionError, urllib.error.URLError),
    )


def _response_error(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("Error Message", "error", "message"):
        value = payload.get(key)
        if isinstance(value, dict):
            value = value.get("message") or value.get("error")
        text = str(value or "").strip()
        if text:
            return text
    return ""


def request_json_list(
    base_url: str,
    api_key: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20,
    max_retries: int = 2,
    opener: UrlOpen = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Fetch one FMP JSON list with bounded retry and safe diagnostics."""

    base = normalize_base_url(base_url)
    key = str(api_key or "").strip()
    if not key:
        raise FmpRatingsError("请先配置 FMP API Key")
    query = urlencode(
        {name: value for name, value in (params or {}).items() if value is not None}
    )
    endpoint = f"{base}/{path.lstrip('/')}"
    if query:
        endpoint = f"{endpoint}?{query}"
    request = urllib.request.Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "apikey": key,
        },
    )
    attempts = max(1, min(4, int(max_retries) + 1))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with opener(request, timeout=max(1.0, float(timeout))) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            response_error = _response_error(payload)
            if response_error:
                safe_error = response_error.replace(key, "[已隐藏]")
                raise FmpRatingsError(f"FMP 返回错误：{safe_error[:200]}")
            if not isinstance(payload, list):
                raise FmpRatingsError("FMP 返回了无法识别的数据格式")
            return [item for item in payload if isinstance(item, dict)]
        except FmpRatingsError:
            raise
        except urllib.error.HTTPError as exc:
            last_error = exc
            status = exc.code
            exc.close()
            if not _transient_error(exc) or attempt + 1 >= attempts:
                if status in {401, 403}:
                    raise FmpRatingsError("FMP 拒绝访问，请检查 API Key 与套餐权限") from exc
                if status == 429:
                    raise FmpRatingsError("FMP 请求超过频率限制") from exc
                raise FmpRatingsError(f"FMP 请求失败（HTTP {status}）") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FmpRatingsError("FMP 返回了无效 JSON") from exc
        except Exception as exc:
            last_error = exc
            if not _transient_error(exc) or attempt + 1 >= attempts:
                if _transient_error(exc):
                    raise FmpRatingsError("FMP 请求超时或连接中断") from exc
                raise FmpRatingsError(f"FMP 请求失败（{type(exc).__name__}）") from exc
        sleep(min(0.5 * (2**attempt), 2.0))
    raise FmpRatingsError(
        f"FMP 请求失败（{type(last_error).__name__ if last_error else 'unknown'}）"
    )


def parse_grade_events(rows: Iterable[dict[str, Any]]) -> list[GradeEvent]:
    events: list[GradeEvent] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        published_at = _parse_datetime(row.get("publishedDate") or row.get("date"))
        if not symbol or published_at is None:
            continue
        events.append(
            GradeEvent(
                symbol=symbol,
                published_at=published_at,
                grading_company=str(row.get("gradingCompany") or "").strip(),
                new_grade=str(row.get("newGrade") or "").strip(),
                previous_grade=str(row.get("previousGrade") or "").strip(),
                action=str(row.get("action") or "").strip(),
                news_title=str(row.get("newsTitle") or "").strip(),
                news_url=str(row.get("newsURL") or "").strip(),
                price_when_posted=_float_or_none(row.get("priceWhenPosted")),
            )
        )
    return events


def parse_price_target_events(
    rows: Iterable[dict[str, Any]],
) -> list[PriceTargetEvent]:
    events: list[PriceTargetEvent] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        published_at = _parse_datetime(row.get("publishedDate") or row.get("date"))
        if not symbol or published_at is None:
            continue
        events.append(
            PriceTargetEvent(
                symbol=symbol,
                published_at=published_at,
                analyst_company=str(
                    row.get("analystCompany") or row.get("gradingCompany") or ""
                ).strip(),
                analyst_name=str(row.get("analystName") or "").strip(),
                price_target=_float_or_none(row.get("priceTarget")),
                price_when_posted=_float_or_none(row.get("priceWhenPosted")),
                news_title=str(row.get("newsTitle") or "").strip(),
            )
        )
    return events


def parse_quotes(rows: Iterable[dict[str, Any]]) -> dict[str, Quote]:
    result: dict[str, Quote] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        result[symbol] = Quote(
            symbol=symbol,
            name=str(row.get("name") or symbol).strip() or symbol,
            price=_float_or_none(row.get("price")),
        )
    return result


def fetch_latest_grades(
    base_url: str,
    api_key: str,
    *,
    page: int = 0,
    limit: int = DEFAULT_FEED_LIMIT,
    timeout: float = 20,
    max_retries: int = 2,
    opener: UrlOpen = urllib.request.urlopen,
) -> list[GradeEvent]:
    rows = request_json_list(
        base_url,
        api_key,
        "grades-latest-news",
        params={"page": max(0, int(page)), "limit": _bounded_limit(limit)},
        timeout=timeout,
        max_retries=max_retries,
        opener=opener,
    )
    return parse_grade_events(rows)


def fetch_latest_price_targets(
    base_url: str,
    api_key: str,
    *,
    page: int = 0,
    limit: int = DEFAULT_FEED_LIMIT,
    timeout: float = 20,
    max_retries: int = 1,
    opener: UrlOpen = urllib.request.urlopen,
) -> list[PriceTargetEvent]:
    rows = request_json_list(
        base_url,
        api_key,
        "price-target-latest-news",
        params={"page": max(0, int(page)), "limit": _bounded_limit(limit)},
        timeout=timeout,
        max_retries=max_retries,
        opener=opener,
    )
    return parse_price_target_events(rows)


def fetch_batch_quotes(
    base_url: str,
    api_key: str,
    symbols: Iterable[str],
    *,
    timeout: float = 20,
    max_retries: int = 1,
    opener: UrlOpen = urllib.request.urlopen,
) -> dict[str, Quote]:
    normalized = sorted(
        {
            str(symbol or "").strip().upper()
            for symbol in symbols
            if str(symbol or "").strip()
        }
    )
    if not normalized:
        return {}
    rows = request_json_list(
        base_url,
        api_key,
        "batch-quote",
        params={"symbols": ",".join(normalized)},
        timeout=timeout,
        max_retries=max_retries,
        opener=opener,
    )
    return parse_quotes(rows)
