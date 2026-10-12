# Gemini Goal C — G1/G3 Fail-Closed Human Auth + LLM + Feishu Loopback Adapter Integration R1

You are Gemini systems-engineering executor C under ChatGPT-0 B-line Controller. No Codex quota available. Complete a runnable **offline engineering handoff** by building a clean sidecar layer of ports (authenticated human decision, bounded LLM analysis, Feishu informational outbox transport simulator, observable recovery), backed by the exact verified **Codex G1 offline core C4**, without changing that original core or sending any real external requests.

TASK_ID: `V06_GEMINI_GOAL_C_G1G3_OFFLINE_PORTS_R1`
CONTROLLER_DISPATCH_SHA: `e35724f1d1ee7458709e003dfc5673c826c68ffd`
AUTHORITY: https://github.com/EXASHXE/btc-quant-agent-public/blob/e35724f1d1ee7458709e003dfc5673c826c68ffd/reviews/v0.6/b_line/V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md
REPO: `EXASHXE/btc-quant-agent-public`
BRANCH: `feature/v06-bline-gemini-g1g3-offline-ports-r1`
EXACT_START_SHA: `861a9d148f72db00e6079e53af78220bdd7e84ce`
WORKTREE: `/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1`
SCRATCH: `/tmp/btc-g1g3_offline_ports_r1`
EXCLUSIVE_WRITES: `scripts/g1g3_offline_ports_r1/**`; `tests/test_v06_g1g3_offline_ports_r1_*.py`; `docs/engineering/g1g3_offline_ports_r1/**`; `evidence/v0.6/b_line/g1g3_offline_ports_r1/**`.
READ-ONLY DEPENDENCY: original Codex `scripts/g1_offline_preview_r1/**` at SHA `861a9d148f72db00e6079e53af78220bdd7e84ce`. Gemini E independent audit `9dad78c40ae28ec59fc1d186dc7802ea7f79594a` has 65 adversarial rejection witnesses, 10 Decimal scenarios and **145/149 local pytest passed (4 its own fixture mismatches)**; do NOT call it "all green" or casually amend its original tests. Prior P1 engine was NO-GO. A-line/Performance/H39-H41 scientific authority are separate.

## New capability required (not a redesign of strategy engine)

Create a **port-boundary “production-shape but OFFLINE-only” G1/G3 integration executable**:
1. **MarketPitPort** consumes `MarketEventV1` *synthetic local* envelopes validated against literal Controller contract. It must reject incomplete, stale, future-known, source provenance drift or wrong provenance; no live Binance stream or private broker. All synthetic feeds are independent fixtures; do not import Gemini A/B experimental branches.
2. **BoundedLLMPort**: receives SHA-bound, redacted signal/evidence context; enforces model request schema, max tokens/bytes, timeout, max attempts and retry budget, structured JSON output schema, model request/response digest and owner-independent traces. A real LLM interface shape may be implemented, but testing uses **loopback HTTP fake server only**. External provider URLs/Credentials disabled by default and not permitted to call; prompt injection in market/news text cannot authorize approval, orders or tool calls. On 408/429/5xx, invalid JSON, output drift, timeout or replay, fail closed to `NO_ACTION_OR_MANUAL_REVIEW`; fallback never silently approves.
3. **AuthenticatedHumanPort**: remove the *sidecar adapter's* reliance on trust by hardcoded `TRUSTED_HUMAN_FIXTURE`, replacing the adapter boundary with verified cryptographic operator decisions (Ed25519 verifier with pinned public keys, or a carefully chosen standard-library HMAC fixture verifier with keys scoped to test and explicit limitation; do not mix live secrets with synthetic fixtures). Signed approval binds signal_id, proposal_hash, version, side, quantity, issue/expiry, operator_id, environment OFFLINE_PREVIEW, context_hash, approval nonce, static trusted key-ID and exact class. Explicit reject: replayed nonce, forged signature, wrong model output, stale clock, wrong key, mutable quantity/side, prior process sequence, unknown environment. No automatic approval even after positive model output. Test keys ephemeral/public fixtures only; never read env real credential files.
4. **FeishuOutboxPort**: translate approved/rejected/pending events into informational cards or JSON messages with deterministic SHA receipt, deduplication id and safe redaction. Use local JSONL/WAL/outbox by default. For integration exercise only, an isolated **loopback** fake Feishu HTTP server with 200/400/401/429/500/timeout variants; test bounded retry, exponential backoff and idempotency, no duplicate human approval, no portfolio mutation on outbox ACK, no silent stop delays. Do **not** send a real Feishu bot notification and do not read user's Feishu secrets. Message content cannot contain private keys/tokens/passwords. Feishu is an informational/approval *adapter interface*, not permission to make external transfers, account transactions or real trading.
5. **NoOrderPort**: runtime and AST/process guard must reject ANY attempt to load Binance signed clients, order/trade/cancel/transfer, listenKey, real account reads, TESTNET/LIVE endpoints. Zero public and private non-loopback network traffic. Only allow loopback 127.0.0.1 / ::1 fake servers when `--allow-loopback` explicitly enabled. No production `src/**` startup modifications, no network on module import, no broker adapter (even mock broker writes must target immutable local simulated core only). G1 pure reducer immutable and entry/stop rules preserved.
6. **Durability/observability**: add independently recoverable journal of operator receipt and outbox interactions, with idempotency/retries and deterministic replay under process failure. Approval can't be duplicated by outbox at-least-once semantics; WAL and approval replay must fail closed on mismatch. Trace_id/span_id, source event hash, operator key-ID, bounded LLM request hash, final approval event ID and simulated-intent ID. Crash after "approved" but before simulated place must settle at-most-once simulated intent. Document power-loss not proven.

## Functional architecture

This is a **read-only/non-ordering adapter wrapper**, not wholesale rewire:
- Original G1 `SignalProposal`, `ANALYZE`, `APPROVE`, `PLACE`, `FILL_ENTRY`, `ACK`, `FUNDING`, `TP1`, `UPDATE_STOP`, `STOP`, `OUTBOX_RECEIPT` remain pure sim state transitions.
- Wrapper authenticates an *external synthetic* operator-signed decision and only then materializes the original `trusted_approvals` **within a newly generated, immutable fixture** which is sealed by source+operator signature. Document the trust translation boundary and why this is NOT yet production identity control; do not deceptively label original core cryptographically aware.
- Original offline fixtures, 24h long/short event hashes, source ledger conservation and 30 process-crash semantics remain regression witnesses. Wrapper may enforce stricter **input acceptance**, must not silently relax reducer guard to pass integration test.
- Loopback stub external LLM/Feishu transports must not become real deployment connectors during this Goal. A production adapter capability that needs user credentials, DNS/TLS, operator auth or actual Feishu webhook is **not implemented** and **not implicitly authorized**.

## Explicit acceptance test suite

Deliver >=**100 executable deterministic tests**, comprising:
- 30 operator authority tests (valid/invalid key, stale nonce, cross-worktree, tampered qty/side, token expiry, replay after restart, multiple operators, wrong environment, one-use nonce, approval after route rebind).
- 20 LLM bounded/fail-closed tests (strict output schema, malicious user supplied prompt, huge response/JSON nesting, token cap, 408/429/5xx and timeouts, retries, wrong model hash, duplicate context, model failure leading NO_ACTION).
- 20 outbox and mock Feishu tests (dedup/reorder, real network blocked, 200/400/401/429/500 response, 503 recover, retry cap, force stop while network-simulated outbox held, no portfolio mutation).
- 20 simulated core integration tests (1x synthetic Last/Mark, TP1 ACK and partial residual, signed Funding, stop newly effective after ACK, out-of-order human ack, 24h cap, entry ack after stop, no implicit order authorization).
- 10 or more process recovery/fault injection tests at boundaries: after operator receipt fsync, before APPROVE, after approve before PLACE, after simulated ENTRY, Feishu ACK, STOP and snapshot, double pending ACK, torn WAL, restart same fixture unchanged. Assert simulated financial journal effect count stable.
- Independent no-real-network guard / static imports test for signed/account APIs, no source access to protected paths, no privileged user file loader. "localhost loopback only" can be enforced using socket connection monkeypatch and explicit host+port allowlist, with an actual listening fake test server.
- Full regression read-only Codex G1 test subset if feasible; no edits to original `tests/test_v06_g1_offline_preview_r1_*.py`.
- Account math original 1000.33834810 LONG / 1000.34054750 SHORT for synthetic baseline when same fixture; do not misrepresent as real profit.

## Verification and completion

Engineering task, max four coherent commits. Unlike scientific freeze, module code may be repaired under own namespace before final code commit; expose complete code SHA, tests on final code and remote HEAD proof. Follow:
C1: written port/data-flow model + implementation key primitives and negative tests; push
C2: loopback fake LLM/Feishu service and trust boundary integration CLI; push
C3: adversarial/restart full suite and hardened output receipts; push
C4: final report, actual GitHub Actions coverage and self-contained local E2E reproduction; push if needed.

Report explicit BEFORE and AFTER capability and release gaps: G1 mock original versus signed-fixture offline wrapper; human trust remains synthetic, not live. G3 readiness **OFFLINE_LOOPBACK_ONLY**, no integrated real LLM or Feishu. Evidence includes roundtrip simulated signal+operator approval+LLM JSON+outbox with no external calls, 100 tests/coverage/durations, actual process-kill receipts, no private endpoint access, Python 3.12, Ruff/compile, source manifests, CI step details. Failure terminal `G1G3_OFFLINE_PORTS_BLOCKED` if any unauthorized network/order path, auth bypass or persistent corruption. Passing terminal `G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED` means only architecture/loopback ready; does not authorize production, real Feishu sends, TESTNET or real funds.

Do not touch local owner Quant-agent/data or Quant-agent-sanitized (NO even listing/stating), 2024–26 protected, H39/H40/H41/Forward, A-line/Performance, G1 original pure core, other agent worktrees or .github; no real OpenAI/Gemini endpoints, no Feishu outside loopback, no Binance private/user APIs and no merges.
