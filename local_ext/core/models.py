from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONTEXT_VERSION = "market-context-v1"


@dataclass(frozen=True)
class NiuOneSnapshot:
    indices: list[dict[str, Any]] = field(default_factory=list)
    breadth: dict[str, Any] = field(default_factory=dict)
    sectors: list[dict[str, Any]] = field(default_factory=list)
    money_flow: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketContext:
    timestamp: str
    trading_date: str
    market_status: str
    regime: dict[str, Any]
    style: list[dict[str, Any]]
    sector_rotation: list[dict[str, Any]]
    breadth: dict[str, Any]
    liquidity: dict[str, Any]
    risk: dict[str, Any]
    data_quality: dict[str, Any]
    data_freshness: dict[str, Any]
    source_versions: dict[str, str]
    context_version: str = CONTEXT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "trading_date": self.trading_date,
            "market_status": self.market_status,
            "regime": self.regime,
            "style": self.style,
            "sector_rotation": self.sector_rotation,
            "breadth": self.breadth,
            "liquidity": self.liquidity,
            "risk": self.risk,
            "data_quality": self.data_quality,
            "data_freshness": self.data_freshness,
            "source_versions": self.source_versions,
            "context_version": self.context_version,
        }
