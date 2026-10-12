# G1/G3 Offline & Loopback Ports Sidecar Integration — Final Engineering Report (`R1`)

- **Task ID:** `V06_GEMINI_GOAL_C_G1G3_OFFLINE_PORTS_R1`
- **Controller Dispatch SHA:** `e35724f1d1ee7458709e003dfc5673c826c68ffd`
- **Immutable Base SHA (Codex G1 C4):** `861a9d148f72db00e6079e53af78220bdd7e84ce`
- **Branch:** `feature/v06-bline-gemini-g1g3-offline-ports-r1`
- **Readiness Classification:** `OFFLINE_LOOPBACK_ONLY`
- **Safety Posture:** `DRY_RUN_NO_NETWORK_NO_ORDERING`

---

## 1. Executive Summary

This deliverable implements and verifies the **G1/G3 Offline & Loopback Ports Sidecar (`scripts/g1g3_offline_ports_r1/`)** around the read-only Codex G1 core (`scripts/g1_offline_preview_r1/` at `861a9d148f72db00e6079e53af78220bdd7e84ce`, `0` bytes modified across all 13 pinned files).

The sidecar enforces strict port boundaries between untrusted external/loopback inputs and the pure G1 state machine:
1. **`MarketPitPort`** ([`market_pit_port.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/scripts/g1g3_offline_ports_r1/market_pit_port.py)): Validates synthetic local `MarketEventV1` and `BookIntegrityV1` envelopes, enforcing closed-bar completeness, point-in-time (PIT) causality, monotonic/wall-clock consistency (`CLOCK_UNCERTAIN`), dense 1-minute bar continuity (`NO_DATA_UNKNOWN_GAP` without forward fill), settled-only funding (`SETTLED_REALIZED`), and idempotent deduplication.
2. **`BoundedLLMPort`** ([`bounded_llm_port.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/scripts/g1g3_offline_ports_r1/bounded_llm_port.py)): Enforces strict request/response schemas, payload size caps (`8 KiB` / `8192` bytes request, `4 KiB` / `4096` bytes response), token budget caps (`<= 256` tokens), JSON object nesting depth (`<= 6`), duplicate JSON key rejection, prompt-injection/secret/order-directive filtering, and bounded loopback HTTP timeouts/retries, degrading deterministically to `NO_ACTION_OR_MANUAL_REVIEW` with zero trading authority.
3. **`AuthenticatedHumanPort`** ([`authenticated_human_port.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/scripts/g1g3_offline_ports_r1/authenticated_human_port.py)) & **`crypto_ed25519`** ([`crypto_ed25519.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/scripts/g1g3_offline_ports_r1/crypto_ed25519.py)): Verifies 12-attribute RFC 8032 Ed25519 operator signatures against a pinned offline keyring (`ACTIVE` vs `REVOKED`), persists hash-chained receipts in `operator_receipts.wal.jsonl`, and performs explicit trust translation into a read-only (`0o400`) sealed G1 fixture (`SEAL_MANIFEST.json`).
4. **`FeishuOutboxPort`** ([`feishu_outbox_port.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/scripts/g1g3_offline_ports_r1/feishu_outbox_port.py)): Formats redacted `FeishuInformationalCardV1` notifications, persists delivery state in `feishu_outbox.wal.jsonl`, delivers over allowlisted `127.0.0.1` loopback HTTP with bounded retries, and guarantees that outbox failures neither mutate portfolio state nor delay mandatory exits (`STOP`, `TIME_CAP`, `TP1`, `TP2`).
5. **`NoOrderPort` & `LoopbackSocketGuard`** ([`no_order_port.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/scripts/g1g3_offline_ports_r1/no_order_port.py)): Rejects all order/cancel/modify/transfer/account/listenKey operations, blocks non-loopback sockets, DNS resolution, and direct `urllib.request.urlopen`, denies protected data/credential paths lexically before any `stat`/`open` syscall, and verifies static AST cleanliness plus 13-file SHA-256 immutability of the Codex G1 core.
6. **`DurableSidecarSupervisor`** ([`durable_supervisor.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/scripts/g1g3_offline_ports_r1/durable_supervisor.py)): Coordinates all 5 ports with the read-only `G1Engine`, maintains hash-chained `sidecar.wal.jsonl`, enforces at-most-once simulated intent settlement (`settled_simulated_intent_count == 1`), and recovers idempotently across all 10 `os._exit(91)` subprocess crash boundaries.

---

## 2. Exact Financial Baseline Reproduction

End-to-end execution through `DurableSidecarSupervisor` (both offline `allow_loopback=False` and live loopback HTTP `allow_loopback=True` via `FakeLoopbackLLMServer` and `FakeLoopbackFeishuServer` on `127.0.0.1`) reproduces the exact Codex G1 24-hour `Decimal` accounting baselines:

| Metric | `LONG` (`synthetic-long-24h-stop`) | `SHORT` (`synthetic-short-24h-stop`) |
| :--- | :--- | :--- |
| Terminal Status | `G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED` | `G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED` |
| G1 Phase | `CLOSED` | `CLOSED` |
| Final `cash` | `1000.33834810` | `1000.34054750` |
| Final `available_cash` | `1000.33834810` | `1000.34054750` |
| Final `mark_equity` | `1000.33834810` | `1000.34054750` |
| Final `reserved_notional` | `0.0000` | `0.0000` |
| Final `remaining_qty` | `0.000` | `0.000` |
| `journal_effects` | `6` | `6` |
| `settled_simulated_intent_count` | `1` | `1` |
| `actual_private_or_network_calls` | `0` | `0` |

---

## 3. Verification Matrix (`287` Passing Tests)

### 3.1 New G1/G3 Offline Ports Test Suite (`142` Passed)
1. **Category 1 — Operator Authority & Ed25519 Trust Translation** ([`test_v06_g1g3_offline_ports_r1_operator_auth.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/tests/test_v06_g1g3_offline_ports_r1_operator_auth.py)): `32` passed. Covers RFC 8032 Ed25519 signature verification, tampered bit rejection, untrusted/revoked/mismatched keys, nonce & token replay across restarts, stale process epoch, worktree/route mismatch, proposal/context drift, expiry/clock bounds, raw `trusted_approvals` rejection, and `0o400` sealed fixture materialization.
2. **Category 2 — Bounded LLM Port** ([`test_v06_g1g3_offline_ports_r1_bounded_llm.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/tests/test_v06_g1g3_offline_ports_r1_bounded_llm.py)): `27` passed. Covers valid loopback HTTP & offline mock analysis, HTTP 500/429/timeout/truncated JSON/invalid UTF-8/empty body, duplicate JSON key rejection, extra fields, non-descriptive risk, order directive injection, prompt injection/secret leaks, token/byte/depth caps, and fail-closed `NO_ACTION_OR_MANUAL_REVIEW` degradation.
3. **Category 3 — Feishu Outbox Port** ([`test_v06_g1g3_offline_ports_r1_feishu_outbox.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/tests/test_v06_g1g3_offline_ports_r1_feishu_outbox.py)): `22` passed. Covers redacted `FeishuInformationalCardV1` construction, secret/forbidden field rejection, loopback HTTP 200 delivery, retryable 500/429/timeout recovery, retry exhaustion fail-safe (`portfolio_mutated: False`), duplicate suppression across restarts, and non-blocking mandatory exit priority.
4. **Category 4 — Core Integration & MarketPitPort** ([`test_v06_g1g3_offline_ports_r1_core_integration.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/tests/test_v06_g1g3_offline_ports_r1_core_integration.py)): `26` passed. Covers `MarketEventV1` closed-bar/PIT/stale/future-known/provenance/symbol/product/channel/secret/monotonic/wall-clock (`CLOCK_UNCERTAIN`) checks, `BookIntegrityV1` sequence gap/crossed spread/staleness, missing bar gap (`NO_DATA_UNKNOWN_GAP` without forward fill), deduplication, settled vs estimated funding, 1x mark exposure guard, and exact `LONG`/`SHORT` 24h accounting reproduction.
5. **Category 5 — Subprocess Crash Recovery & Guards** ([`test_v06_g1g3_offline_ports_r1_recovery_and_guards.py`](file:///z:/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1/tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py)): `35` passed. Covers real `os._exit(91)` subprocess crash + recovery across all 10 crash boundaries (`after_operator_receipt_fsync`, `before_approve`, `after_approve_before_place`, `after_place_before_entry`, `after_simulated_entry`, `after_feishu_ack`, `after_tp1_before_ack`, `at_stop_before_snapshot`, `at_stop_after_snapshot`, `double_pending_ack`), torn sidecar WAL and torn G1 WAL quarantine without unsafe replay, idempotent restart on unchanged state, `NoOrderPort` runtime blocking, lexical protected-path denial before `os.stat`/`Path.stat`, static AST & 13-file C4 SHA-256 verification, `LoopbackSocketGuard` enforcement with a live local server, and CLI secret non-reflection.

### 3.2 Read-Only Codex G1 Core Regression Suite (`145` Passed)
- Executed `tests/test_v06_g1_offline_preview_r1_*.py`: `145 passed`, `0` bytes modified in `scripts/g1_offline_preview_r1/**` or `tests/test_v06_g1_offline_preview_r1_*.py`.

---

## 4. Explicit Non-Claims & Honest Limitations

1. **Offline & Loopback Only (`OFFLINE_LOOPBACK_ONLY`):** This sidecar is verified exclusively on deterministic synthetic fixtures and `127.0.0.1` loopback HTTP test servers. It does not connect to any public or private exchange, LLM provider, or Feishu cloud endpoint, and does not authorize testnet, live trading, or real-money execution.
2. **Process Crash vs. Hardware Power Loss (`power_loss_durability_proven: false`):** The `os._exit(91)` subprocess crash suite and torn-WAL quarantine tests prove process-crash recovery and deterministic quarantine of truncated WAL tails after `os.fsync()`. They do **not** prove physical hardware power-loss durability across storage controller caches or kernel fault injection (`dm-flakey`).
3. **Synthetic Trust Translation Boundary:** `AuthenticatedHumanPort.materialize_sealed_fixture` translates a verified external Ed25519 operator receipt into a read-only (`0o400`) sealed G1 fixture (`trusted_approvals`) so the immutable Codex G1 reducer can execute without modifying a single byte of `scripts/g1_offline_preview_r1/**`. This is an offline sidecar bridge (`SYNTHETIC_ED25519_TO_SEALED_G1_FIXTURE_ONLY`), not a production HSM/KMS identity control plane.
4. **Historical Repository Test Debt Transparency:**
   - Gemini E's historical 145/149 suite (4 failures) is outside this worktree's scope, was not touched, and is never claimed as "all green".
   - In GitHub Actions (`.github/workflows/ci.yml`), commits that touch `scripts/**` (`C1` `c1f8099`, `C2` `381b902`) trigger `scripts/ci/test_plan.py` `mode = "full"`, which runs the entire repository test suite including the pre-existing, out-of-scope `tests/test_p09_through_p18_exact_scientific_graph.py` failure while passing `Ruff`, `Compile Python`, and `Validate changed JSON artifacts`. In `C3` (`5f88bbd`), `mode = "focused"` invoked the `pytest` console script with `PYTHONPATH=src` (without repository root on `sys.path`), which failed collection. After `f926191` (`docs-only` green run `38219079391`) and `ca01e42` (added `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` across all 5 test suites, which triggered 26 `RUF100` unused `# noqa: E402` warnings in run `38224361334`), the final `C4` commit removes the unused `# noqa: E402` directives across all 5 `tests/test_v06_g1g3_offline_ports_r1_*.py` suites so both Step 10 (`Ruff`) and Step 14 (`mode = "focused"` on all 5 test suites, `142` tests) pass with `conclusion: "success"`.
