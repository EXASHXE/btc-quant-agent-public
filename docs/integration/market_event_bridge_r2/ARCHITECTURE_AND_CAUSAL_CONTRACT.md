# Architecture & Causal Financial Contract — R2 Clash Routed Market Event Bridge

## 1. System Identity and Scope Bounds

- **TASK_ID**: `V06_GEMINI_GOAL_ABC_R2_CLASH_ROUTED_PUBLIC_SOURCE_PIT_BRIDGE`
- **CONTROLLER_AUTHORITY_SHA**: `acf59828f878f3b1cc56e257dd952a8cd2c9ea97`
- **EXACT_START_SHA**: `df00997f344eba82f7cca0d03ee1617948abee44`
- **DEPENDENCY_B_READ_ONLY_SHA**: `51cdd4e17503fbd18ad22aaeeaba3580f5efacf8`
- **DEPENDENCY_C_READ_ONLY_SHA**: `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`
- **ORIGINAL_G1_CORE_READ_ONLY_SHA**: `861a9d148f72db00e6079e53af78220bdd7e84ce`
- **Scientific Status Disclaimer**:
  The candidate research in branch B has been declared **INVALID** due to post-freeze algorithmic modifications and unverified freeze SHAs. This R2 integration bridge implements **engineering interface compatibility only**. It grants no new Alpha claim, no real prospective trading authorization, no order routing authority, and no live execution rights.

---

## 2. Four Cross-Branch Incompatibilities & Formal Adjudication

### Incompatibility 1: Mark Price Tick vs 1-Minute Mark Bar (A ↔ B)
- **Upstream Reality**: A receives official Binance WebSocket `markPriceUpdate` frames containing `{e: "markPriceUpdate", E, s, p, i, r, T}`. These represent 1-second sampled ticks, **not** minute candlestick bars.
- **Consumer Defect in B**: B's `PublicFeedAdapter._dispatch_event` routes `Channel.MARK_PRICE` events to `parse_kline_payload()`, expecting a candle dictionary `{"k": {"t", "T", "o", "h", "l", "c", "x"}}`. Because `markPriceUpdate` does not possess candle keys, `k.get("x")` evaluates to `False`, preventing `pending_mark_1m` from ever pairing with `pending_last_1m`.
- **Causal Resolution**:
  - The bridge aggregates verified 1-second Mark ticks over aligned 60-second windows (`[open_ms, open_ms + 59999]`).
  - Strict admission gates: minimum sample count (`count >= 40`), maximum gap between consecutive ticks (`gap <= 5000ms`), and window completion confirmation.
  - Generates `DERIVED_MARK_1M` with:
    - `derived_available_at_ms = max(obs.available_at_ms)`
    - `parent_event_sha256 = [tick1_sha, tick2_sha, ...]`
    - `raw_source_manifest_sha256 = manifest_sha`
  - If ticks are missing, sparse, or late: produces `NO_DERIVED_MARK` (quality `UNKNOWN` or `INVALID`). Never promotes an arbitrary single tick to an official 1m kline bar.

### Incompatibility 2: Depth Receipt vs Top-10 Ladder Notional Imbalance (A ↔ B)
- **Upstream Reality**: A's `BookIntegrityV1` receipt record includes `snapshot_update_id`, `first_update_id`, `final_update_id`, `continuous`, `best_bid`, `best_ask`, and `observed_depth_levels`. It omits full ladder price/quantity arrays `bids[]` and `asks[]` to maintain lightweight streaming telemetry.
- **Consumer Requirement in B**: B's P2 trading signal requires top-10 bids and asks to calculate notional order book imbalance: `(bid_notional - ask_notional) / (bid_notional + ask_notional)`.
- **Causal Resolution**:
  - The bridge accesses A's verified, continuous `OrderBookIntegrityEngine` internal state atomically (in read-only fashion) at the boundary of receipt emission.
  - Constructs an immutable top-10 ladder snapshot: `bids: tuple[(p, q), ...]` (descending) and `asks: tuple[(p, q), ...]` (ascending).
  - Emits top-10 ladder hash: `top10_ladder_sha256`.
  - Admission gate: requires `len(bids) >= 10`, `len(asks) >= 10`, `best_bid < best_ask`, and `stale_age_ms <= 1000ms`.
  - If the order book is unbootstrapped, crossed, stale (>1s), or spans a route epoch change: produces `NO_P2_SIGNAL` (with reason codes).

### Incompatibility 3: Settled Funding Rate Financial Accounting (A ↔ B)
- **Upstream Reality**: A fetches settled funding history from `GET /fapi/v1/fundingRate`, returning `[{fundingTime, fundingRate, symbol}]`.
- **Consumer Flaw in B**: B's `parse_funding_payload` checks keys `{T, r, p}`, silently defaulting missing keys to `0.0` or `0`. Ingesting A's payload directly results in `funding_time_ms = 0`, `funding_rate = 0.0`, `mark_price = 0.0`, resulting in a catastrophic financial accounting error (zero cash debit/credit).
- **Causal Resolution**:
  - Explicit canonical mapping: `T: fundingTime`, `r: Decimal(fundingRate)`, `p: Decimal(mark_price_at_settlement)`.
  - Financial verification gate: require `settled == True`, `rate_type == "SETTLED_REALIZED"`. Reject estimated or unfinalized funding.
  - Exact Decimal arithmetic:
    - Long position cash flow: `-1 * position_size * funding_rate * mark_price`
    - Short position cash flow: `+1 * position_size * funding_rate * mark_price`
  - Idempotent deduplication on `(symbol, fundingTime, settlement_id)` to prevent double settlement.
  - If contemporaneous mark price is unverified or missing at settlement: flag `COST_INCOMPLETE` / `NO_REALIZED_FUNDING_JOURNAL`.

### Incompatibility 4: Last 1m Raw Frame vs C MarketPitPort Composite BAR (A ↔ C)
- **Upstream Reality**: A records raw Binance USDⓈ-M kline frames `{"e": "kline", "k": {"t", "T", "o", "c", "h", "l", "v", "x", ...}}`.
- **Consumer Contract in C**: C's `MarketPitPort._translate_bar` enforces an exact, unbendable composite bar schema:
  `{"bar_open_ms", "bar_close_ms", "closed", "last_open", "last_high", "last_low", "last_close", "mark_close", "event_id"}`.
  It requires `closed == True`, `bar_open_ms % 60000 == 0`, `bar_close_ms == bar_open_ms + 59999`, `available_at_ms >= bar_close_ms`, and non-negative OHLC values conforming to `low <= min(open, close)` and `high >= max(open, close)`.
- **Causal Resolution**:
  - The bridge coordinates confirmed closed Last 1m frames (`k.x == True`) and contemporaneous `DERIVED_MARK_1M` closes.
  - Emits the exact composite schema demanded by `MarketPitPort` without modifying C's codebase or G1's cash ledger.
  - Fails closed on timestamp discrepancy or clock regression.

---

## 3. Network Egress and Clash Proxy Architecture

1. **Proxy Transparency & Security**:
   - Explicit configuration only: `--network public-clash-explicit --proxy-kind http|socks5h --proxy-host <HOST> --proxy-port <PORT>`.
   - Never scans LAN or loops across unconfigured ports.
   - Never reads or exposes passwords, tokens, API keys, or raw node subscription URLs.
   - Pinned egress: REST and WebSocket connections share the exact same proxy route.
2. **Four-Layer Health State Machine**:
   - `L1_TCP_PROBE`: Low-frequency ping to proxy socket.
   - `L2_PROXY_NEGOTIATION`: HTTP CONNECT or SOCKS5h greeting and remote DNS resolution.
   - `L3_TLS_VERIFY_REST`: Strict TLS certificate validation to official REST endpoint.
   - `L4_WSS_UPGRADE`: WebSocket handshake and initial frames on official streams.
3. **Route Epoch Isolation**:
   - Changing proxy host/port increments `route_epoch`.
   - Upon route epoch change, all order book state is invalidated and re-bootstrapped from fresh REST snapshot.
