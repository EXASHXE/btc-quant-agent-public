# Real Public Source Multi-Channel Qualification & Redaction Criteria

## 1. Defect Analysis: The R2 Smoke False-Positive Vector

In Market Event Bridge R2, live source qualification suffered from a critical false-positive vulnerability. In `connector.py`:
```python
if stats["events_received"] > 0:
    stats["status"] = "PUBLIC_SMOKE_VERIFIED"
```
Because the initial REST depth snapshot counted as 1 event (`stats["events_received"] = 1`), if both subsequent WebSocket connection attempts crashed immediately with `ConnectionRefusedError` or `SSLError`, `events_received > 0` remained True and the smoke check erroneously reported `PUBLIC_SMOKE_VERIFIED`.

Moreover, the diagnostic receipt leaked internal network topology (`NETWORK_ROUTE_DIAGNOSTIC.json` contained host IP `127.0.0.1`, port `7897`, WSL2 LAN gateway `192.168.31.1`, and unredacted `NO_PROXY` strings).

---

## 2. R3 Multi-Channel Qualification Specification

In R3, [`scripts/integration/market_event_bridge_r2/source_qualification.py`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/source_qualification.py) and [`scripts/market_data/forward_public_feed_r1/connector.py`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/market_data/forward_public_feed_r1/connector.py) implement strict qualification rules.

### Qualification Hierarchy
1. **`SOURCE_UNAVAILABLE`**: Network inaccessible, REST snapshot failed, or both WebSocket streams failed to connect.
2. **`PUBLIC_ROUTE_REACHABLE`**: REST snapshot succeeded, but WebSocket streams failed or disconnected.
3. **`SHORT_DIAGNOSTIC`**: WebSocket connected and received events, but execution window was shorter than required threshold (`duration < 120s`, `mark_span_seconds < 120.0s`, or `kline_closed_1m < 2`).
4. **`PUBLIC_SOURCE_PARTIAL`**: Missing required channel data (e.g. `aggTrade == 0` or raw depth updates missing).
5. **`PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED`**: Full multi-channel verification passing all thresholds:
   - Observation duration $\ge 120$ seconds
   - Mark price span $\ge 120.0$ seconds
   - Closed 1-minute klines $\ge 2$
   - AggTrades received $> 0$
   - Raw depth updates received $> 0$
   - Zero WebSocket errors across both public depth and market streams
6. **`L2_CONTINUOUS_WINDOW_VERIFIED`**: Meets all multi-channel criteria AND maintains continuous L2 order book without unrecovered desync or rebootstrap throughout the window.

### Per-Channel Telemetry Metrics
The client tracks granular per-channel telemetry counters:
- `raw_public_depth_update`: Total differential order book depth updates.
- `REST_snapshot`: Total REST snapshots ingested (initial + any rebootstrap).
- `aggTrade`: Total aggregate trade executions.
- `markPriceTick`: Total mark price ticks.
- `kline_closed_1m`: Total verified closed 1-minute candles (`k.x == True`).
- `kline_open_1m`: Total in-flight 1-minute candle updates (`k.x == False`).
- `estimatedFunding`: Total estimated funding ticks.
- `settledFunding`: Total settled funding records.
- `invalidFrames`: Malformed or schema-invalid JSON frames (must be 0).
- `sourceDropped`: Stream disconnects or network retries (must be 0).
- `rebootstrap_count`: Book desync recovery events.
- `clockUncertain`: Transit clock regression or uncertainty warnings.
- `mark_span_seconds`: Active span between first and last observed mark price ticks.

### Strict Proxy & Diagnostic Redaction
Public evidence must never expose internal network topology. [`build_redacted_route_diagnostic`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/market_data/forward_public_feed_r1/proxy_route.py) strictly outputs only:
- `proxy_enabled`: Boolean flag.
- `proxy_kind`: Protocol type (`http`, `socks5h`, or `none`).
- `loopback_or_host`: Categorical string (`loopback`, `remote_host`, or `direct`).
- `route_hash`: Irreversible 16-character SHA-256 hash of routing tuple.
- `session_id`: Cryptographic session identifier.
- `diagnostic_code`: Terminal error or success code.
- `layers`: Sanitized layer statuses omitting IP and port numbers.
- `error_detail`: Error message with all IPv4 addresses and port numbers masked as `[REDACTED_IP]` and `[REDACTED_PORT]`.

---

## 3. Real Public Telemetry Receipt

A full 180-second observation run was executed via the local Clash proxy:
- **Duration**: 180 seconds
- **Total Events Ingested**: 4,730
- **Differential Depth Updates**: 1,733
- **Aggregate Trades**: 2,405
- **Mark Price Ticks**: 178 (span: 177.0s)
- **Closed 1-Minute Klines**: 3 (exceeding minimum requirement of 2)
- **WebSocket Task Errors**: 0
- **Final Qualification Level**: `PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED`
- **Receipt Stored**: [`evidence/v0.6/b_line/market_event_bridge_r3/PUBLIC_SOURCE_CHANNEL_QUALITY.json`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/evidence/v0.6/b_line/market_event_bridge_r3/PUBLIC_SOURCE_CHANNEL_QUALITY.json)
