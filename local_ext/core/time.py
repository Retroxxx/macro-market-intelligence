from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(SHANGHAI)


def iso(moment: datetime | None = None) -> str:
    return (moment or now()).astimezone(SHANGHAI).isoformat(timespec="seconds")


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (result.replace(tzinfo=SHANGHAI) if result.tzinfo is None else result).astimezone(SHANGHAI)
