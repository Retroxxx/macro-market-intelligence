# a-stock-data Capability Audit

- Upstream: `https://github.com/simonlin1212/a-stock-data`
- Version: `3.7.2`
- Commit: `3a599d09dfa5f15c6e171e96febdb693664455e6`
- Audited: 2026-09-02
- License: Apache-2.0 (Copyright 2026 Simon Lin; no `NOTICE` file)

## Positioning

This repository is used as source knowledge, not as a runtime dependency. Its endpoint recipes are primarily embedded in `SKILL.md`; this project implements a small stdlib-only adapter with its own validation, cache, retry, and source metadata. No `SKILL.md` content is executed at runtime and no git submodule is used.

## P0 capability matrix

| Capability | Endpoint | Integrated | Notes |
|---|---|---:|---|
| Industry ranking / breadth | `push2.eastmoney.com/api/qt/clist/get`, `fs=m:90+t:2`, `fid=f3` | Yes | Keeps board code, normalized name, advancing/declining and leader fields. |
| Industry fund flow, 1D | `push2.eastmoney.com/api/qt/clist/get`, `fid=f62` | Yes | Main net amount, main ratio, change and leader where supplied. |
| Industry fund flow, 5D | same, `fid=f164` | Yes | Aggregate 5-day fields only; not a point-in-time history. |
| Industry fund flow, 10D | same, `fid=f174` | Yes | Aggregate 10-day fields only; leader deliberately remains unknown. |
| Limit-up pool | `push2ex.eastmoney.com/getTopicZTPool` | Yes | Trading-date snapshot; empty on a valid non-trading date is distinct from error. |
| Broken-limit pool | `push2ex.eastmoney.com/getTopicZBPool` | Yes | Trading-date snapshot. |
| Limit-down pool | `push2ex.eastmoney.com/getTopicDTPool` | Yes | Trading-date snapshot. |
| Yesterday limit-up pool | `push2ex.eastmoney.com/getYesterdayZTPool` | Yes | Trading-date snapshot. |

All pool prices follow the upstream recipe's `p`/`ztp` scale conversion (divide by 1000); money amounts remain yuan until a canonical consumer converts them.

## Deliberately not integrated

Individual K-lines, level-2/order book, ticks, research reports, F10, financial statements, CYQ, individual-stock fund flow/valuation, ETF/options, macro series, Interactive Q&A, news/AI, narrative, policy/global tape, broker or trading-account interfaces, browser automation, credentials, and every non-P0 endpoint are out of scope.

## Operational findings

The endpoints are undocumented EastMoney push APIs. `ut`, `fid`, `fs`, field numbers, response nesting, rate limits, and pagination can drift. Community observations report problems around bursts of roughly 5 requests/second, more than 10 concurrent connections, or sustained hundreds of requests per minute. A 403 is treated as a hard source error and is not retried; 429 and transient 5xx/network failures receive bounded retries. The adapter serializes calls behind a process lock and uses per-capability TTL cache plus single-flight behavior. It never calls EastMoney per browser request.

## Drift controls

The adapter validates object shape, row shape, date format, and numeric fields without inventing missing values. Unknown fields are ignored. A schema change produces `SCHEMA_ERROR`; an empty but structurally valid response produces `VALID_EMPTY`. Every result carries endpoint, fixed upstream version/SHA, retrieval time, event time, trading date, freshness, quality, and warnings. A bounded production smoke is intentionally separate from unit tests and is never required by CI.
