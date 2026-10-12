# Binance 2026-04-23 WebSocket Migration & USDⓈ-M Stream Routing Architecture

## 1. Executive Summary & Regulatory Authority

- **TASK_ID**: `V06_GEMINI_GOAL_ABC_R2_CLASH_ROUTED_PUBLIC_SOURCE_PIT_BRIDGE`
- **CONTROLLER_AUTHORITY_SHA**: `acf59828f878f3b1cc56e257dd952a8cd2c9ea97`
- **Migration Effective Date**: `2026-04-23 00:00:00 UTC`
- **Product**: Binance USDⓈ-M Futures (`BINANCE_USDT_M_PERP`), Symbol: `BTCUSDT`
- **Official Documentation Anchors**:
  - [USDⓈ-M WebSocket Connect](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect)
  - [Important WebSocket Change Notice (2026 Migration)](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice)
  - [How to manage a local order book correctly](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly)
  - [Order Book REST API](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Order-Book)
  - [Get Funding Rate History REST API](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Get-Funding-Rate-History)

---

## 2. Upstream Factual Change & Endpoint Separation

Prior to April 23, 2026, clients could subscribe to combined market and depth streams across a single unrouted endpoint:
```text
(LEGACY - OBSOLETE AFTER 2026-04-23)
wss://fstream.binance.com/stream?streams=btcusdt@kline_1m/btcusdt@markPrice@1s/btcusdt@aggTrade/btcusdt@depth@100ms
```

**Starting 2026-04-23**, Binance USDⓈ-M Futures WebSocket infrastructure strictly partitioned market traffic from high-frequency public order book diffs:
1. **Unrouted Endpoint Deprecation**: Connecting to `/stream?streams=...` without route classifier drops all Market class streams (`@markPrice`, `@kline_1m`, `@aggTrade`).
2. **Dedicated Public Stream (Diff Depth)**:
   - Base URL: `wss://fstream.binance.com/public/stream`
   - Canonical Subscription: `wss://fstream.binance.com/public/stream?streams=btcusdt@depth@100ms`
   - Purpose: Differential L2 order book updates (`depthUpdate` frames with `U`, `u`, `pu`, `b`, `a`).
3. **Dedicated Market Stream (Market Events)**:
   - Base URL: `wss://fstream.binance.com/market/stream`
   - Canonical Subscription: `wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade/btcusdt@kline_1m/btcusdt@markPrice@1s`
   - Purpose: Public trade matching (`aggTrade`), 1-minute candlestick updates (`kline`), and 1-second mark price ticks (`markPriceUpdate`).
4. **REST Public Endpoints**:
   - Depth Snapshot: `GET https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000`
   - Settled Realized Funding: `GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=5`

---

## 3. Strict Fail-Closed Routing Policies

Any connection attempt matching any of the following triggers immediate **FAIL-CLOSED** with `BINANCE_ROUTING_INVALID`:
- **Private Stream Prohibitions**: Any URL containing `/private`, `listenKey`, `ws-fapi`, `api_key`, `secret`, `signature`, `order`, `balance`.
- **Cross-Product Prohibitions**: Host `dapi.binance.com` (COIN-M Delivery / Inverse) or `api.binance.com` (Spot).
- **Testnet Prohibitions**: `testnet.binancefuture.com` or `testnet.binance.vision`.
- **Legacy Route Prohibitions**: Any attempt to subscribe to market streams (`kline`, `markPrice`, `aggTrade`) over unrouted `/stream` or `/public/stream`.
- **Cross-Stream Contamination**: Attempting to combine `depth` on `/market/stream` or `kline`/`markPrice`/`aggTrade` on `/public/stream`.

---

## 4. Dual Connection Lifecycle & Invariants

Because Binance requires two distinct WebSocket connections post-migration, the client bridge enforces the following invariants:
1. **Independent Connection Epochs**:
   - `public_connection_epoch`: e.g. `pub-epoch-20261012-001`
   - `market_connection_epoch`: e.g. `mkt-epoch-20261012-001`
   - Route and connection epoch increments independently upon reconnection or route failure.
2. **Receiver Ingress Timestamp Isolation**:
   - `observed_wall_utc_ms` and `observed_monotonic_ns` are captured strictly at network ingress on the host machine.
   - Provider timestamps (`E` event time, `T` transaction time) are recorded strictly as upstream metadata and never overwrite arrival time.
3. **Cross-Stream Causal Alignment**:
   - Mark Price and Last Trade/Kline alignment occurs strictly after reception.
   - For any derived feature or composite bar, `feature_known_at_ms = max(available_at_ms)` across both constituent events.
4. **Session Lifetime & Reconnection Limit**:
   - Binance terminates WebSocket connections at 24 hours. The bridge schedules bounded proactive reconnection before 24h (default: 23 hours 50 minutes).
   - Reconnection adheres to exponential backoff and bounded retry limits.
5. **Rate Limiting**:
   - Maximum 300 connection attempts per 5-minute rolling window per IP.
   - Backpressure supervision buffers no more than 10,000 frames before entering `DEGRADED` or `FAIL_CLOSED`.
