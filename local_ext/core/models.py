from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CONTEXT_VERSION = "market-context-v1"
A_STOCK_DATA_VERSION = "3.7.2@3a599d09dfa5f15c6e171e96febdb693664455e6"


@dataclass(frozen=True)
class SourceMetadata:
    source: str
    source_endpoint: str
    source_version: str
    retrieved_at: str
    event_time: str | None = None
    trading_date: str | None = None
    freshness_seconds: float | None = None
    quality: str = "UNKNOWN"
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["warnings"] = list(self.warnings)
        return value


@dataclass(frozen=True)
class ProviderResult:
    capability: str
    status: str
    data: Any
    metadata: SourceMetadata
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "status": self.status,
            "data": self.data,
            "metadata": self.metadata.as_dict(),
            "error": self.error,
        }


@dataclass(frozen=True)
class CanonicalSector:
    sector_id: str
    sector_name: str
    taxonomy: str = "unknown"
    change_pct: float | None = None
    advancing: int | None = None
    declining: int | None = None
    flat: int | None = None
    breadth_ratio: float | None = None
    leader_name: str | None = None
    leader_change: float | None = None
    flow_1d: float | None = None
    flow_5d: float | None = None
    flow_10d: float | None = None
    flow_ratio_1d: float | None = None
    flow_ratio_5d: float | None = None
    flow_ratio_10d: float | None = None
    relative_rank: int | None = None
    updated_at: str | None = None
    sources: tuple[str, ...] = ()
    quality: str = "UNKNOWN"
    warnings: tuple[str, ...] = ()
    lineage: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sources"] = list(self.sources)
        value["warnings"] = list(self.warnings)
        return value


@dataclass(frozen=True)
class MarketBreadthSnapshot:
    advancing: int | None = None
    declining: int | None = None
    flat: int | None = None
    advance_ratio: float | None = None
    limit_up: int | None = None
    limit_down: int | None = None
    broken_limit: int | None = None
    broken_rate: float | None = None
    yesterday_limit_up_count: int | None = None
    yesterday_limit_up_positive: int | None = None
    yesterday_limit_up_negative: int | None = None
    yesterday_limit_up_success_rate: float | None = None
    turnover: float | None = None
    turnover_change: float | None = None
    updated_at: str | None = None
    sources: tuple[str, ...] = ()
    quality: str = "UNKNOWN"
    warnings: tuple[str, ...] = ()
    lineage: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sources"] = list(self.sources)
        value["warnings"] = list(self.warnings)
        return value


@dataclass(frozen=True)
class LimitStateSnapshot:
    state: str
    trading_date: str | None
    rows: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str | None = None
    sources: tuple[str, ...] = ()
    quality: str = "UNKNOWN"
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sources"] = list(self.sources)
        value["warnings"] = list(self.warnings)
        return value


@dataclass(frozen=True)
class NiuOneSnapshot:
    indices: list[dict[str, Any]] = field(default_factory=list)
    breadth: dict[str, Any] = field(default_factory=dict)
    sectors: list[dict[str, Any]] = field(default_factory=list)
    money_flow: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    canonical_breadth: MarketBreadthSnapshot | None = None
    canonical_sectors: list[CanonicalSector] = field(default_factory=list)
    market_internals: dict[str, Any] = field(default_factory=dict)
    provider_health: dict[str, Any] = field(default_factory=dict)
    source_versions: dict[str, str] = field(default_factory=dict)


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
