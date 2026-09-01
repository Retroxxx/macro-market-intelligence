from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StockSystemAdapter:
    """Reserved contract; this extension never reads the stock system directly."""

    configured: bool = False

    def market_aggregate(self) -> dict[str, Any]:
        return {"state": "NotConfigured", "available": False}
