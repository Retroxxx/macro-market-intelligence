# Data Fusion Contract

## Runtime boundary

`local_ext.adapters.niuone.NiuOneAdapter` remains the primary official read-only source. `local_ext.adapters.a_stock_data.AStockDataAdapter` is an opt-in supplemental provider for the eight P0 capabilities documented in `A_STOCK_DATA_CAPABILITY_AUDIT.md`. The provider is not imported by official `app/`, is not a database writer, and does not execute `SKILL.md`.

The request path is:

```text
NiuOne HTTP + optional EastMoney HTTP
        -> ProviderResult (status + SourceMetadata)
        -> canonical/fused NiuOneSnapshot
        -> deterministic Regime v2 / Sector Rotation v2
        -> MarketContext v1 additive JSON
```

## Status and quality

`VALID` means a structurally valid non-empty response; `VALID_EMPTY` means a structurally valid empty response; `SOURCE_ERROR`, `SCHEMA_ERROR`, `STALE_DATA`, and `DISABLED` remain distinct. Quality maps to `GOOD`, `DEGRADED`, `FAILED`, `STALE`, or `UNKNOWN`. Missing numeric facts are `null`, never zero.

Every provider result includes `source`, `source_endpoint`, `source_version`, `retrieved_at`, `event_time`, `trading_date`, `freshness_seconds`, `quality`, and `warnings`. The current P0 endpoints do not expose one authoritative event timestamp, so `event_time` remains `null` rather than reusing `retrieved_at`; `trading_date` records the requested market date.

## Field policy

| Canonical field | Primary | Fallback | Conflict | Freshness |
|---|---|---|---|---|
| Sector change/breadth/leader/1D flow | NiuOne | a-stock-data | retain both in lineage and warn `SOURCE_CONFLICT` when material | current context TTL |
| Sector 5D/10D aggregate flow | a-stock-data | none | provider status visible | 300 seconds |
| Market advancing/declining/turnover | NiuOne | none currently | retain both if a future fallback exists | current context TTL |
| Limit-up/down counts | NiuOne | pool-derived a-stock-data | retain both and warn on material count difference | current context TTL |
| Broken-limit and yesterday continuation | a-stock-data | none | status visible | 45 seconds |

Fallback adds a `fallback:<field>:a_stock_data` warning. A conflict does not silently overwrite lineage.

## Rotation rules v2

The evaluator consumes canonical fields only. Persistence is derived from available 1D/5D/10D flow signs:

- `PERSISTENT_POSITIVE` / `PERSISTENT_NEGATIVE`: all available periods agree and 1D+5D exist;
- `IMPROVING`: 1D positive while 5D is non-positive;
- `DETERIORATING`: 1D negative while 5D is non-negative;
- `MIXED`: contradictory signs;
- `UNKNOWN`: insufficient multi-period data.

State is deterministic: `STARTING` requires positive short-term change, healthy breadth, positive 1D flow and not-yet-positive 5D flow; `TRENDING` requires positive change, breadth and aligned 1D/5D flow; `EXPANDING` additionally requires broad participation and positive longer flow; `DIVERGING` catches positive price with weak breadth/flow; `FADING` requires negative price, contracting breadth and negative 1D/5D flow; `WEAK` is negative without enough evidence. `CROWDED` is not emitted without reliable crowding data.

## Regime rules v2

Existing regime names remain compatible. The evaluator additionally uses broken-limit rate, yesterday limit-up continuation, and limit-up/down imbalance when present. It emits `PANIC`, `RISK_OFF`, `RECOVERY`, `RISK_ON_ROTATION`, `RISK_ON_TREND`, or `UNKNOWN`; it never emits a trade instruction or position size.

## Cache and rate limits

The adapter serializes requests per process, uses a capability cache, and limits retry to two retries maximum. 403 is never retried; 429 and transient 5xx/network errors are bounded. Defaults are 60 seconds for ranking, 300 seconds for 5D/10D flow, and 45 seconds for pool snapshots. The minimum inter-request interval defaults to one second. Browser requests only read the local context cache.

The default `LOCAL_MACRO_A_STOCK_ENABLED=0` preserves safe deployment behavior. Enable it explicitly in a controlled environment and run `scripts/local/check_a_stock_sources.py`; production smoke is bounded and not part of CI.
