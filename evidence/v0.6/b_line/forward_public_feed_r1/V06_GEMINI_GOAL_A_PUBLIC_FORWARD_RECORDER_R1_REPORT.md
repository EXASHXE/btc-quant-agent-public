# Final Engineering Evidence Report: Gemini Goal A — BTCUSDT Public Forward Recorder (R1)
**Task ID**: `V06_GEMINI_GOAL_A_PUBLIC_FORWARD_RECORDER_R1`  
**Repository**: `EXASHXE/btc-quant-agent-public`  
**Branch**: `feature/v06-bline-gemini-forward-public-feed-r1`  
**Base Commit SHA**: `55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**Controller Authority SHA**: `e35724f1d1ee7458709e003dfc5673c826c68ffd`  
**Authority Reference**: `reviews/v0.6/b_line/V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md`  
**Terminal Grade**: `PUBLIC_FORWARD_RECORDER_OFFLINE_VERIFIED`  

---

## 1. System Inventory and File Changes

All deliverables are strictly isolated to the authorized write scopes:
- `scripts/market_data/forward_public_feed_r1/`:
  - `__init__.py`: Package entry and exports.
  - `contracts.py`: Semantic schemas for `MarketEventV1` and `BookIntegrityV1`, canonical UTF-8 JSON serialization, SHA-256 computation, dedupe key generation, and endpoint security allowlists.
  - `fixture.py`: Hermetic deterministic exchange fixture generator for all public USDⓈ-M channels.
  - `order_book.py`: `OrderBookIntegrityEngine` maintaining L2 depth, official Binance USDⓈ-M depth bridge rules (U/u/pu), crossed spread detection, and zero-quantity level deletion.
  - `time_authority.py`: `TimeAuthority` enforcing Point-in-Time arrival invariants, clock rollback detection (`CLOCK_UNCERTAIN`), process epoch isolation, and transit latency histograms (P50/P90/P99).
  - `durability.py`: `SegmentWriter` and `SegmentReader` providing append-only JSONL segments, cryptographic SHA-256 hash chaining, atomic manifest roll (`.tmp` -> `os.replace`), and torn-write quarantine recovery.
  - `health.py`: `HealthSupervisor` tracking channel staleness, segregated settled vs estimated funding, and source readiness gating (`SOURCE_READY`, `SOURCE_DEGRADED`, `SOURCE_UNAVAILABLE`).
  - `connector.py`: `BinancePublicFeedClient` providing explicit network-gated public read-only HTTP/WS connections, pre-parse ingress timestamping, and geoblock detection.
  - `replay.py`: `ReplayEngine` reconstructing and asserting immutability, continuous depth order book state, and arrival watermarks across recorded segments.
  - `cli.py`: Single-process Linux CLI supporting `--mode [fixture|replay|live-public]` and `--network [disabled|allow-public]`.
- `tests/`:
  - `test_v06_forward_public_feed_r1_contracts.py` (26 tests)
  - `test_v06_forward_public_feed_r1_book.py` (18 tests)
  - `test_v06_forward_public_feed_r1_time.py` (11 tests)
  - `test_v06_forward_public_feed_r1_durability.py` (7 tests)
  - `test_v06_forward_public_feed_r1_health.py` (7 tests)
  - `test_v06_forward_public_feed_r1_connector.py` (13 tests)
  - `test_v06_forward_public_feed_r1_replay.py` (5 tests)
  - `test_v06_forward_public_feed_r1_e2e_scenarios.py` (7 tests)
  - `test_v06_forward_public_feed_r1_adversarial.py` (12 tests)
  - `test_v06_forward_public_feed_r1_reviewer_fixes.py` (28 tests)
- `docs/market_data/forward_public_feed_r1/`:
  - `PUBLIC_FORWARD_RECORDER_SPECIFICATION.md`
  - `VERIFICATION_EVIDENCE.md`
- `evidence/v0.6/b_line/forward_public_feed_r1/`:
  - `V06_GEMINI_GOAL_A_PUBLIC_FORWARD_RECORDER_R1_REPORT.md` (this report)

Zero changes made to production `src/**`, CI configurations, `.github`, or historical data folders.

---

## 2. Python Dependencies and Environment

- **Runtime**: Linux x86_64, Python 3.12.3 (`/usr/bin/python3.12`).
- **Standard Libraries**: `json`, `hashlib`, `urllib`, `dataclasses`, `time`, `os`, `pathlib`, `ast`, `decimal`.
- **Core Dependencies**: `pytest 9.0.3`, `ruff 0.17.0`, `websockets 16.0`.

---

## 3. Negative Security and Anti-Cheat Matrix

The test suite validates negative error paths and contract enforcement across 134 automated tests:
1. **Network Gate Violation**:
   - Calling client without `--network allow-public` raises `NetworkGateError: Network access blocked`.
   - CLI invocation `--mode live-public --network disabled` exits with return code 2.
2. **Endpoint Allowlist & Protocol Guard**:
   - Attempting to connect to COIN-M `dapi.binance.com` raises `ContractValidationError`.
   - Attempting to connect to Spot `api.binance.com` raises `ContractValidationError`.
   - Attempting HTTP `POST`, `PUT`, or `DELETE` raises `ContractValidationError`.
   - URLs containing `/order`, `/listenKey`, or `/userDataStream` raise `ContractValidationError`.
3. **AST Security Audit**:
   - `test_ast_inspection_no_private_order_methods_or_keys` performs static AST analysis across all package source files to verify absence of order execution methods, API key headers, or private user stream paths.
4. **Symbol Allowlist & Payload Validation**:
   - Lowercase `btcusdt`, `BTC-USDT`, or non-target symbols (`ETHUSDT`, `SOLUSDT`) strictly raise `ContractValidationError`.
   - Alien symbol payloads in stream frames (`ETHUSDT`) are rejected before normalizing.
   - Provider payload shape validator enforces mandatory fields per channel (`s`, `E`, `u`, `U`, `b`, `a`).
   - Decimal validation enforces valid numeric price fields, strictly rejecting `NaN`, `Infinity`, and malformed strings with `ContractValidationError`.
5. **Clock Tampering, Monotonic Invariants & PIT Causality**:
   - System clock rollbacks (wall clock moves backwards while monotonic advances) degrade event quality to `CLOCK_UNCERTAIN`.
   - Backdating `available_at_ms` earlier than `observed_wall_utc_ms` raises `ContractValidationError`.
   - Exchange clock offset diagnostic captures provider-to-local divergence (`mean_offset_ms`, `latest_offset_ms`).
   - `join_mark_and_last` enforces strict Point-In-Time causality (`decision_at_ms >= max(mark.available_at_ms, kline.available_at_ms)`) and exact symbol match; future queries or symbol mismatches raise `PointInTimeViolationError`.
6. **Order Book Gaps, Contradictions & Sequence Integrity**:
   - Reversed sequence IDs (`U > u`) immediately fail closed (`REVERSED_SEQUENCE_IDS`).
   - Backwards / duplicate updates (`u <= pu` or `u <= prev_final_u`) fail closed (`DUPLICATE_OR_BACKWARDS_UPDATE`).
   - Intra-frame mutation contradictions (duplicate price levels in same delta) fail closed (`MUTATION_CONTRADICTION`).
   - Intra-snapshot duplicate price levels fail closed (`MUTATION_CONTRADICTION`).
   - First update bridging without `pu` safely bridges when `U <= lastUpdateId + 1 <= u`.
   - First update gap (`pu > lastUpdateId`) fails closed and marks `needs_rebootstrap`.
   - Crossed spread in snapshot or diff update (`bid >= ask`) fails closed (`CROSSED_BOOK`).
   - Empty book degrades quality to `DEGRADED` (`EMPTY_BOOK`).
   - Stale book age exceeding 5 minutes (`300_000 ms`) degrades quality to `DEGRADED` (`STALE_BOOK`).
7. **Durability, Raw Segregation, Replay & Restart Idempotence**:
   - Segregated raw wire persistence (`RawSegmentWriter`) records raw wire frames with independent cryptographic manifests.
   - Normalised segments chained via SHA-256 (`entry_hash = sha256(index:prev_hash:payload_sha:event_sha)`).
   - Broken hash-chains trigger `DurabilityError`.
   - Crash-restart idempotence seamlessly resumes existing segments on disk without breaking hash chains.
   - Atomic manifest `.tmp` promotion recovers from mid-swap process termination.
   - Truncated trailing writes from crash / power-off in both normalized and raw segments are automatically quarantined to `.quarantine` while restoring valid prefix.
   - Dual replay capability supports normalized replay (`--replay-source normalized`) and direct raw wire segment replay (`--replay-source raw`) reconstructing original arrival watermarks.
8. **Health Supervisor & Gating Robustness**:
   - Source gate checks staleness across all required channels (`mark_price`, `depth_delta`, `last_kline_1m`, `agg_trade`).
   - Unknown official settled funding fails closed (`LAST_SETTLED_FUNDING_UNKNOWN`).
   - High ingress queue drop rate degrades source gate (`CONSUMER_INGRESS_DROPS`).
   - HTTP 403 / 429 access denial immediately transitions gate to `SOURCE_UNAVAILABLE` (`EXCHANGE_ACCESS_DENIED`).

---

## 4. Replay and Continuous Depth Continuity Witness

Fixture generation and offline replay verification executed via CLI:
```bash
python3 -m scripts.market_data.forward_public_feed_r1.cli --mode fixture --records-count 50 --output-dir /tmp/btc-forward_public_feed_r1/clean_run
python3 -m scripts.market_data.forward_public_feed_r1.cli --mode replay --replay-dir /tmp/btc-forward_public_feed_r1/clean_run --replay-source normalized
python3 -m scripts.market_data.forward_public_feed_r1.cli --mode replay --replay-dir /tmp/btc-forward_public_feed_r1/clean_run --replay-source raw
```

**Normalized Replay Witness Output (`--replay-source normalized`)**:
```json
{
  "events_replayed": 53,
  "first_wall_utc_ms": 1791799159321,
  "last_wall_utc_ms": 1791799159515,
  "head_hash": "ba63ad72c2085eaaac835e39ce7daecc0c43b81838c3e2ed59c1ecb72184f2d7",
  "depth_continuous": true,
  "channel_counts": {
    "depth_snapshot": 1,
    "funding_settled": 1,
    "depth_delta": 13,
    "agg_trade": 13,
    "mark_price": 12,
    "last_kline_1m": 12,
    "health": 1
  },
  "quality_counts": {
    "VERIFIED": 53
  },
  "reason_code_counts": {
    "SNAPSHOT_APPLIED": 1,
    "OK": 52
  }
}
```

**Raw Wire Segment Replay Witness Output (`--replay-source raw`)**:
```json
{
  "events_replayed": 52,
  "first_wall_utc_ms": 1791799159321,
  "last_wall_utc_ms": 1791799159515,
  "head_hash": "dbe329ffcf62d2404f76bf828dad3cc865551a4131471e35df3dd08f174f61eb",
  "depth_continuous": true,
  "channel_counts": {
    "depth_snapshot": 1,
    "funding_settled": 1,
    "depth_delta": 13,
    "agg_trade": 13,
    "mark_price": 12,
    "last_kline_1m": 12
  },
  "quality_counts": {
    "VERIFIED": 52
  },
  "reason_code_counts": {
    "OK": 52
  }
}
```

---

## 5. Bounded Live Public Smoke Test Witness

Executed bounded public read-only smoke stream against official Binance USDⓈ-M public endpoints:
```bash
python3 -m scripts.market_data.forward_public_feed_r1.cli --mode live-public --network allow-public --duration-seconds 3
```

**Observed Live Run Result (Regional Restriction / SSL Protocol Reset)**:
```json
{
  "status": "NOT_TESTED_SOURCE_UNREACHABLE",
  "events_received": 0,
  "duration_seconds": 3,
  "rebootstrap_count": 0,
  "error": "REST depth snapshot failed: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1032)>"
}
```

Per task instructions:
- "Source/region unavailability is a valid explicit BLOCKED state, not permission to invent events or use private user files."
- "If public endpoint unreachable/geoblocked, live smoke = NOT_TESTED_SOURCE_UNREACHABLE; do not use a proxy around geographic restriction or change base provider silently."
- "Never claim any 24h real recorder until it actually ran; don't leave unattended eternal recorder process."
- "Terminal PUBLIC_FORWARD_RECORDER_OFFLINE_VERIFIED, PUBLIC_FORWARD_RECORDER_PUBLIC_SMOKE_VERIFIED or PUBLIC_FORWARD_RECORDER_FAIL_CLOSED."

Official public endpoints targeted:
- REST Snapshot: `https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000`
- WebSocket Combined Stream: `wss://fstream.binance.com/stream?streams=btcusdt@kline_1m/btcusdt@markPrice@1s/btcusdt@aggTrade/btcusdt@depth@100ms`

Operational observations:
- Zero authentication headers sent. Zero private credentials used.
- When runner network encounters SSL drops / provider regional blocking, the client cleanly traps the error, issues no unauthorized retries or proxy hops, and records status as `NOT_TESTED_SOURCE_UNREACHABLE`.
- Process terminated cleanly upon expiration with zero persistent background daemons.

---

## 6. Verification Summary Matrix

- **Total Unit & Integration Tests**: 134 automated tests.
- **Pass Rate**: 100% (134 passed, 0 failed, 0 skipped).
- **Ruff Lint Check**: Clean (0 errors).
- **Terminal Status**: `PUBLIC_FORWARD_RECORDER_OFFLINE_VERIFIED`.
