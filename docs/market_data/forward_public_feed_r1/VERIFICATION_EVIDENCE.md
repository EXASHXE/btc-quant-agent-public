# Binance USDⓈ-M Futures Public Forward Recorder Verification Evidence (R1)
**Task ID**: `V06_GEMINI_GOAL_A_PUBLIC_FORWARD_RECORDER_R1`  
**Branch**: `feature/v06-bline-gemini-forward-public-feed-r1`  
**Starting Commit SHA**: `55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**Controller Authority SHA**: `e35724f1d1ee7458709e003dfc5673c826c68ffd`  
**Terminal Grade**: `PUBLIC_FORWARD_RECORDER_OFFLINE_VERIFIED`  

---

## 1. Verified Architecture & Boundaries

The implementation strictly satisfies all constraints established by the Controller Authority:
1. **Public-Only, Account-Free, Order-Free**:
   - Zero private API keys, zero listenKey endpoints, zero account or execution methods.
   - AST validation confirms zero occurrences of HTTP `POST`, `PUT`, or `DELETE`, and zero references to execution order methods.
2. **Explicit Network Gate**:
   - Default CLI and library execution enforces `--network disabled`.
   - Connecting to live Binance servers strictly requires explicit opt-in `--network allow-public`.
3. **Strict Official USDⓈ-M Futures Allowlist**:
   - REST Host: `https://fapi.binance.com`
   - WebSocket Host: `wss://fstream.binance.com`
   - COIN-M (`dapi.binance.com`) and Spot (`api.binance.com`) endpoints are strictly blocked and raise `ContractValidationError`.
4. **Point-in-Time (PIT) Semantics**:
   - Wall-clock (`observed_wall_utc_ms`) and process monotonic nanoseconds (`observed_monotonic_ns`) captured immediately at the network ingress boundary prior to JSON parsing.
   - Invariant enforced: `available_at_ms >= observed_wall_utc_ms`.
   - Backwards wall clock movement or extreme clock divergence degrades quality to `CLOCK_UNCERTAIN`.
5. **Continuous Order Book Bridging**:
   - Full implementation of Binance USDⓈ-M depth bridge:
     - Buffer stream deltas while waiting for REST snapshot (`GET /fapi/v1/depth?symbol=BTCUSDT&limit=1000`).
     - Drop buffered deltas where `u < lastUpdateId`.
     - First update satisfies `pu == lastUpdateId` or `U <= lastUpdateId <= u` (contiguous bridging).
     - Subsequent updates satisfy `pu == prev_u` and `u > prev_final_u`.
     - Reject reversed sequence IDs (`U > u`) and backwards/duplicate updates.
     - Reject intra-frame level mutation contradictions (duplicate price levels in same delta).
     - Non-zero quantities update levels; zero quantity removes levels.
     - Crossed spreads (`bid >= ask`) or missing updates immediately fail closed (`quality=INVALID`, `continuous=False`).
6. **Durability, Hash-Chains & Raw Log Segregation**:
   - Segregated append-only raw wire frames (`RawSegmentWriter`, `raw_segment_*.jsonl`) with independent cryptographic manifests.
   - Normalized append-only `MarketEventV1` JSONL segments chained with SHA-256 hashes (`entry_hash = sha256(index:prev_hash:payload_sha:event_sha)`).
   - Atomic manifest roll (`.tmp` -> `fsync` -> `os.replace`).
   - Crash-restart idempotence: seamlessly resumes existing segments on disk without breaking hash chains.
   - Torn-write detection and automatic quarantine of corrupt trailing bytes.
7. **Point-in-Time Causality & Time Diagnostics**:
   - Ingress timestamp capture prior to parsing: `available_at_ms >= observed_wall_utc_ms`.
   - Exchange clock offset tracking: bidirectional transit diagnostic (`mean_offset_ms`, `latest_offset_ms`).
   - Causal join (`join_mark_and_last`) strictly enforcing decision timestamp precedence (`decision_at_ms >= max(mark.available_at_ms, kline.available_at_ms)`).
8. **Settled Funding vs Estimated Funding Separation**:
   - Channel `funding_settled`: records official 8-hour settled rates realized after the funding timestamp has elapsed.
   - Channel `mark_price`: records current mark price and annotates estimated rate `r` as `ESTIMATED_NOT_SETTLED`.
   - Health supervisor fails closed (`SOURCE_UNAVAILABLE`) when official settled funding is unknown.

---

## 2. Automated Test Execution Record

Total Automated Tests: **134 tests** (all passing).

| Test Suite File | Tests | Coverage Area | Status |
| :--- | :--- | :--- | :--- |
| `tests/test_v06_forward_public_feed_r1_contracts.py` | 26 | MarketEventV1 schema, BookIntegrityV1, canonical JSON, SHA-256, dedupe key, fixture generator | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_book.py` | 18 | Order book bridging, U/u/pu sequences, gaps, crossed spreads, stale threshold, level deletion | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_time.py` | 11 | PIT clock authority, wall rollback detection, monotonic order, latency percentiles P50/P90/P99 | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_durability.py` | 7 | Hash-chain integrity, segment rotation, manifest atomic swap, torn-write quarantine | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_health.py` | 7 | HealthSupervisor, channel staleness, SOURCE_READY/DEGRADED/UNAVAILABLE gating, funding status | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_connector.py` | 13 | Network gate, URL security validation, COIN-M blocking, frame parsers, unreachable reporting | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_replay.py` | 5 | ReplayEngine, hash verification across files, arrival watermark preservation, ReplayWitness | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_e2e_scenarios.py` | 7 | CLI modes (fixture/replay/live-public), 15m high-velocity synthetic burst, crash-restart recovery | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_adversarial.py` | 12 | AST security audit, 1k reconnect epochs, rate-limit backoff, head-of-line drop, symbol confusion | **PASSED** |
| `tests/test_v06_forward_public_feed_r1_reviewer_fixes.py` | 28 | Reviewer repairs: reversed sequence IDs, duplicate/backwards sequence IDs, intra-frame mutation contradictions, contiguous bridge without pu, pu snapshot gap, empty book degradation, exchange clock offset tracking, causal PIT join, raw segment log segregation, crash-restart idempotence, manifest clock uncertainty, health gating on settled funding and queue drops, access denial, symbol allowlist, aggressor side mapping, multi-epoch replay, raw segment replay, manifest .tmp crash promotion, raw torn-write quarantine, Decimal price rejection of NaN/Inf | **PASSED** |

---

## 3. Live Public Smoke Execution Record

Command:
```bash
python3 -m scripts.market_data.forward_public_feed_r1.cli --mode live-public --network allow-public --duration-seconds 3
```

Live Smoke Output (Observed under regional restriction / SSL protocol reset):
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

When public exchange endpoints are unreachable or geoblocked by provider network topology in the runner environment, the client cleanly detects unreachable status, captures the exact provider connection error without bypassing security restrictions or inventing fake events, and marks the terminal grade as `PUBLIC_FORWARD_RECORDER_OFFLINE_VERIFIED`. All offline deterministic fixture, replay, and durability suites pass 100% across all 134 tests.
