# Binance USDⓈ-M Futures Public Forward Recorder Specification (R1)
**Document ID**: `DOC-V06-GEMINI-GOAL-A-PUBLIC-FORWARD-RECORDER-R1`  
**Task ID**: `V06_GEMINI_GOAL_A_PUBLIC_FORWARD_RECORDER_R1`  
**Authority Reference**: `reviews/v0.6/b_line/V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md`  
**Dispatch Commit SHA**: `e35724f1d1ee7458709e003dfc5673c826c68ffd`  
**Base Commit SHA**: `55ac4c631c69f6edbd275462ad23e4486b9782ed`  

---

## 1. Executive Summary & Core Constraints

This specification defines the high-reliability, **public-only, account-free, order-free** forward market recorder for Binance USDⓈ-M BTCUSDT perpetual futures (`BINANCE_USDT_M_PERP`).

### Fundamental Operational Boundary
1. **Public-Only Read Access**:
   - Strictly observational recording operation.
   - **No API keys**, no secret keys, no listenKeys, no userData streams.
   - **No order execution, cancellation, or private account endpoints**.
   - **No POST, PUT, or DELETE HTTP methods**. Only read-only `GET` for public snapshots/historical funding.
2. **Network Gate & Safety**:
   - Default CLI and Python library configuration is `--network disabled`.
   - Connecting to live network requires an explicit CLI flag `--mode live-public --network allow-public`.
   - Allowed hosts are strictly locked down to official Binance USDⓈ-M endpoints.
   - Any attempt to access COIN-M endpoints (`dapi.binance.com`), spot endpoints (`api.binance.com`), or non-allowlisted hosts fails closed immediately.
3. **Point-In-Time (PIT) Semantics**:
   - No unobserved moment receives known-at credit.
   - Observer records both **UTC wall-clock time (`observed_wall_utc_ms`)** and **process monotonic time (`observed_monotonic_ns`)** immediately on raw socket frame arrival prior to parsing.
   - `available_at_ms >= observed_wall_utc_ms`, never backdated to bar close or exchange event time.
   - System clock rollbacks or contradictions between monotonic ordering and wall-clock trigger `CLOCK_UNCERTAIN` quality degradation.

---

## 2. Official Binance USDⓈ-M Documentation URLs

The implementation conforms strictly to official Binance USDⓈ-M Futures documentation (2026 current):

1. **General Introduction & Base URLs**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction  
   - Base REST URL: `https://fapi.binance.com`  
   - Base WebSocket Stream URL: `wss://fstream.binance.com/ws`  
   - Combined WebSocket Stream URL: `wss://fstream.binance.com/stream`  

2. **WebSocket Live Subscribing & Streams**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams  

3. **Differential Depth Book Streams**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Diff-Book-Depth-Streams  
   - Stream Name: `<symbol>@depth` or `<symbol>@depth@100ms` (e.g. `btcusdt@depth@100ms`)  
   - Fields: `e="depthUpdate"`, `E` (Event time), `T` (Transaction time), `s` (Symbol), `U` (First update ID), `u` (Final update ID), `pu` (Previous final update ID), `b` (Bids), `a` (Asks).  

4. **Order Book REST Snapshot**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Order-Book  
   - Endpoint: `GET /fapi/v1/depth?symbol=BTCUSDT&limit=1000`  
   - Response: `lastUpdateId`, `E` (Message output time), `T` (Transaction time), `bids`, `asks`.  

5. **Kline / Candlestick Streams**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Kline-Candlestick-Streams  
   - Stream Name: `<symbol>@kline_1m` (e.g. `btcusdt@kline_1m`)  
   - Finalized candle condition: `k.x == True`. Developing candles (`k.x == False`) are observable but unsealed.  

6. **Mark Price Stream**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Mark-Price-Stream  
   - Stream Name: `<symbol>@markPrice` or `<symbol>@markPrice@1s`  
   - Fields: `p` (Mark price), `i` (Index price), `r` (Estimated next funding rate), `T` (Next funding time).  
   - **Crucial Rule**: The `r` rate from the mark price stream is an *estimated projection*, NOT settled funding. It is labeled `ESTIMATED_NOT_SETTLED` and forbidden from realized cash accounting.  

7. **Aggregate Trade Streams**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Aggregate-Trade-Streams  
   - Stream Name: `<symbol>@aggTrade`  
   - Fields: `a` (Agg trade ID), `p` (Price), `q` (Quantity), `f` (First trade ID), `l` (Last trade ID), `T` (Trade time), `m` (Was the buyer the maker? `True` -> sell aggressor; `False` -> buy aggressor).  

8. **Historical / Official Settled Funding Rate REST**:  
   https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Get-Funding-Rate-History  
   - Endpoint: `GET /fapi/v1/fundingRate?symbol=BTCUSDT&limit=100`  
   - Official settled funding is realized strictly after the funding timestamp has elapsed and the rate is confirmed.  

---

## 3. Data Contract: MarketEventV1

Every public observation is sealed into an immutable `MarketEventV1` envelope serialized in canonical UTF-8 JSON.

```json
{
  "schema_version": "market-event-v1",
  "symbol": "BTCUSDT",
  "product": "BINANCE_USDT_M_PERP",
  "channel": "last_kline_1m",
  "provider_event_ms": 1728720000000,
  "provider_transaction_ms": 1728719999999,
  "observed_wall_utc_ms": 1728720000150,
  "observed_monotonic_ns": 948123456789,
  "available_at_ms": 1728720000150,
  "source_stream_id": "btcusdt@kline_1m",
  "connection_epoch": "epoch-20261012-161500-pid12345",
  "source_sequence": 105234,
  "payload_sha256": "3a7b...",
  "payload": { ... },
  "quality": "VERIFIED",
  "reason_codes": ["OK"],
  "raw_source_manifest_sha256": "e81f...",
  "book": null
}
```

### Channel Specifics:
1. `last_kline_1m`: finalized 1m candle (`k.x=True`) or developing tick.
2. `mark_price`: periodic mark price updates.
3. `agg_trade`: aggregate trades with aggressor direction.
4. `depth_delta`: incremental L2 diff updates.
5. `depth_snapshot`: initial / resync REST book snapshots.
6. `funding_settled`: official realized 8-hour funding rates.
7. `health`: local recorder health heartbeats, latencies, drop metrics.

### Quality Levels:
- `VERIFIED`: Passed all semantic, sequence, continuity, and checksum validations.
- `DEGRADED`: Observable data present but degraded (e.g. clock uncertainty, partial book, high latency).
- `UNKNOWN`: Unverified source or unconfirmed preliminary event.
- `INVALID`: Discontinuous sequence, crossed spread, forged checksum, or contract violation.

---

## 4. Book Integrity (BookIntegrityV1) & Bridging Rules

Local order book maintenance follows the official USDⓈ-M protocol:
1. Stream `btcusdt@depth@100ms` is opened and buffered.
2. Public REST snapshot is fetched via `GET /fapi/v1/depth?symbol=BTCUSDT&limit=1000`.
3. Buffered events with `u < lastUpdateId` are dropped.
4. First bridging event must satisfy: `U <= lastUpdateId <= u`.
5. Subsequent events must satisfy `event.pu == prev_event.u`.
6. Price level mutations:
   - Quantity `0.0` or `"0"`: remove level.
   - Non-zero: update / insert level.
7. Integrity checks:
   - Bids strictly sorted descending; asks strictly sorted ascending.
   - Best bid < Best ask.
   - If crossed or gap detected: mark `quality=INVALID`, reason `GAP_DETECTED` or `CROSSED_BOOK`, fail-closed, initiate re-bootstrap.
