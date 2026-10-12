# G1/G3 Offline Loopback Ports (`g1g3_offline_ports_r1`) — Port Data-Flow & Trust Translation Boundary Model

## 1. Authority & Scope Boundary

- **Task ID:** `V06_GEMINI_GOAL_C_G1G3_OFFLINE_PORTS_R1`
- **Controller Dispatch SHA:** `e35724f1d1ee7458709e003dfc5673c826c68ffd`
- **Authority Document:** `reviews/v0.6/b_line/V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md`
- **Repository:** `EXASHXE/btc-quant-agent-public`
- **Branch:** `feature/v06-bline-gemini-g1g3-offline-ports-r1`
- **Exact Start SHA:** `861a9d148f72db00e6079e53af78220bdd7e84ce`
- **Worktree:** `/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1`
- **Scratch Namespace:** `/tmp/btc-g1g3_offline_ports_r1`
- **Read-Only Core Dependency:** `scripts/g1_offline_preview_r1/**` at `861a9d148f72db00e6079e53af78220bdd7e84ce` (Codex G1 Offline Preview C4, 0 bytes modified).

---

## 2. Hexagonal Port Architecture & Data-Flow Model

```text
+---------------------------------------------------------------------------------------------------+
|                           G1/G3 Offline Port Integration Supervisor                               |
|                        (scripts/g1g3_offline_ports_r1/durable_supervisor.py)                      |
+---------------------------------------------------------------------------------------------------+
        |                        |                        |                        |
        v                        v                        v                        v
+----------------+      +-----------------+      +------------------+     +-----------------+
| MarketPitPort  |      | BoundedLLMPort  |      | AuthHumanPort    |     | FeishuOutboxPort|
| (MarketEventV1 |      | (Loopback HTTP  |      | (RFC8032 Ed25519 |     | (Local WAL +    |
|  PIT/Provenance|      |  Schema/Timeout |      |  Pinned Public   |     |  Loopback HTTP  |
|  Clock/Book/   |      |  Token/Depth/   |      |  Keys, 12-Field  |     |  Retry/Backoff/ |
|  SettledFund)  |      |  Prompt-Inject  |      |  Context Binding,|     |  Idempotent     |
|                |      |  Fail-Closed -> |      |  Durable Nonce   |     |  Redacted Cards)|
|                |      |  NO_ACTION)     |      |  Anti-Replay WAL)|     |                 |
+-------+--------+      +--------+--------+      +--------+---------+     +--------+--------+
        |                        |                        |                        ^
        | Verified BAR/FUNDING   | Verified ANALYZE       | Sealed Fixture         | Outbox Rows
        +--------------------+   |   +--------------------+ (trusted_approvals)    | (Read-Only)
                             |   |   |                                             |
                             v   v   v                                             |
+----------------------------------------------------------------------------------+----------------+
|                     Immutable Read-Only Codex G1 Core (scripts/g1_offline_preview_r1)             |
|  model.py + reducer.py + storage.py (Pure Transition, Mandatory Causal Exits, Decimal Cash Ledger)|
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
|                                        NoOrderPort Guard                                          |
|  - Rejects all order/trade/cancel/transfer/listenKey/account calls (NO_ORDER_PORT_FORBIDDEN)      |
|  - Blocks all non-loopback network & DNS; loopback 127.0.0.1/::1 requires --allow-loopback        |
|  - Lexical protected-path denial before stat/open; AST & C4 SHA256 immutability verification      |
+---------------------------------------------------------------------------------------------------+
```

### 2.1 Port Contracts

1. **`MarketPitPort` (`market_pit_port.py`)**:
   - Accepts canonical UTF-8 `MarketEventV1` (`schema_version == "market-event-v1"`) synthetic local envelopes only (`symbol == "BTCUSDT"`, `product == "BINANCE_USDT_M_PERP"`).
   - Enforces receiver ingress availability (`available_at_ms >= observed_wall_utc_ms` and `>= provider_event_ms`), monotonic-vs-wall-clock consistency (`CLOCK_UNCERTAIN` on wall-clock regression while monotonic advances), `payload_sha256` integrity, and `raw_source_manifest_sha256` provenance pinning.
   - Deduplicates by `sha256(symbol, channel, connection_epoch, provider_id_or_raw_sha)` while incrementing observable duplicate counters; rejects payload drift under the same deduplication key (`MARKET_EVENT_PROVENANCE_DRIFT`).
   - Validates `BookIntegrityV1` continuity, spread uncrossed (`best_bid < best_ask`), and staleness bounds (`BOOK_INTEGRITY_INVALID`).
   - Enforces closed-bar causality (`closed is True`), dense 1m continuity without forward-fill (`NO_DATA_UNKNOWN_GAP`), and settled-only funding (`ESTIMATED_NOT_SETTLED` is forbidden from cash journal).

2. **`BoundedLLMPort` (`bounded_llm_port.py`)**:
   - Consumes SHA-bound, credential-redacted signal/proposal/market context (`LLMAnalysisRequestV1`).
   - Enforces request schema, max request bytes (`<= 8192`), max response bytes (`<= 4096`), max JSON nesting depth (`<= 6`), max completion tokens (`<= 256`), per-attempt socket timeout, retry budget, and duplicate-context prevention.
   - External URLs and provider credentials are forbidden (`LLM_EXTERNAL_ENDPOINT_FORBIDDEN`). Only loopback (`127.0.0.1` / `::1`) fake HTTP servers are permitted when `--allow-loopback` is explicitly enabled.
   - Prompt injection in market/news/summary strings (`IGNORE PREVIOUS INSTRUCTIONS`, `place_order`, `tool_calls`, `risk: APPROVE`, etc.) or any HTTP `408`/`429`/`5xx`/timeout/malformed JSON/model-hash drift fails closed to `NO_ACTION_OR_MANUAL_REVIEW` (`approved = False`, `order_authorized = False`).

3. **`AuthenticatedHumanPort` (`authenticated_human_port.py`)**:
   - Rejects raw unauthenticated `TRUSTED_HUMAN_FIXTURE` dicts at the sidecar input boundary (`RAW_FIXTURE_TRUST_REJECTED`).
   - Requires a cryptographically signed `SignedOperatorDecisionV1` verified via RFC 8032 Ed25519 against pinned public keys (`PINNED_OPERATOR_KEYRING`).
   - Binds 12 mandatory fields: `signal_id`, `proposal_hash`, `version` (`1`), `side`, `quantity`, `issued_at`, `expires_at`, `operator_id`, `environment` (`"OFFLINE_PREVIEW"`), `context_hash` (binding `source_hash`, `proposal_hash`, `analysis_hash`, `worktree_id`, `route_id`, `process_epoch`), `approval_nonce`, `key_id`, and `decision_class`.
   - Persists consumed nonces and operator receipts to a durable append-only `operator_receipts.wal.jsonl` with `os.fsync` before any approval materialization.

4. **`FeishuOutboxPort` (`feishu_outbox_port.py`)**:
   - Translates approved, rejected, pending, and execution-state events into redacted `FeishuInformationalCardV1` payloads with deterministic `deduplication_id` and `payload_sha256`.
   - Writes locally to `feishu_outbox.wal.jsonl` by default, and optionally delivers over loopback HTTP to an isolated fake Feishu server (`200`, `400`, `401`, `429`, `500`, `503` recover, timeout) with bounded exponential-backoff retry and idempotency.
   - Outbox delivery or ACK never mutates portfolio cash/inventory, never duplicates human approval, and never delays mandatory causal exits (`STOP`, `TIME_CAP`, `TP2`, `TP1`).

5. **`NoOrderPort` (`no_order_port.py`)**:
   - Runtime and static AST guard blocking all order placement, cancellation, account reads, `listenKey`, non-loopback sockets, DNS resolution, and lexical protected filesystem paths.

---

## 3. Trust Translation Boundary & Limitations

1. **Why Original G1 Core Is Not Cryptographically Aware**:
   - The read-only Codex G1 core (`scripts/g1_offline_preview_r1/model.py` and `reducer.py`) validates static dictionary tokens with `"issuer": "TRUSTED_HUMAN_FIXTURE"` loaded into `initial_state(trusted_approvals)`.
   - We do **not** modify `scripts/g1_offline_preview_r1/**` and do **not** claim the underlying reducer performs cryptographic verification.
2. **How the Sidecar Trust Translation Works**:
   - The sidecar wrapper accepts an unsealed/untrusted scenario fixture (`trusted_approvals = []`) plus an external Ed25519-signed `SignedOperatorDecisionV1`.
   - Only after `AuthenticatedHumanPort` verifies the Ed25519 signature, pinned public key, 12-field context binding, causal timestamps, and durable one-use nonce does the sidecar materialize the translated G1 token inside an immutable (`0o400`) `sealed_fixture.json` paired with `SEAL_MANIFEST.json`.
3. **Why This Is Still `OFFLINE_LOOPBACK_ONLY` (Not Production Identity Control)**:
   - Keypairs in this repository are ephemeral/public synthetic test fixtures, not hardware-backed operator credentials (HSM/KMS/WebAuthn/IdP).
   - LLM and Feishu transports connect only to local `127.0.0.1` loopback fake HTTP servers; no real LLM provider, no real Feishu webhook, no live market feed, and no broker/exchange order port exist.
   - Process crash recovery (`os._exit(91)`) verifies single-process WAL replay and at-most-once simulated intent settlement on a live OS kernel, but does **not** prove hardware power-loss or disk write-reordering durability.
