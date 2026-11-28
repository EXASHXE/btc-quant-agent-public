# QUANT v0.8.0 — H4 Consolidated S2–S5 Field-Trial Readiness

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.


- **Task ID:** \`V080-SOL62-H4-S2S5-CONSOLIDATED-READINESS-01\`
- **Executor:** GPT-6.2 Sol / Extra High (\`xhigh\`); record actual interface-reported model ID
- **Controller:** ChatGPT Controller 0-C
- **Dispatch:** See the separate immutable Controller runtime receipt under \`controller-decisions/\`; this canonical card alone does not grant authority
- **Work classification:** ONE LONG-RUN, FOUR INTERNAL PHASES, OFFLINE ENGINEERING AND INTEGRATED QA ONLY
- **Acceptance:** ONE consolidated Controller independent offline review; no per-phase re-authorization for work expressly in scope
- **Real Binance / Feishu / provider OAuth / recurring / private / trading permissions:** NOT AUTHORIZED
- **Final handoff language:** Chinese; engineering artifacts and logs: English
- **Workroot:** \`/root/workspace/project/quant-0.8.0/workspaces/lt-v080-sol62-h4-s2s5-consolidated-readiness-01/\`

## 1. Executive mission and deliverable

Deliver a single installable, independently auditable **offline integration candidate** clearing the known technical readiness defects for:
- H4-A / S2: future genuine **two-request** Binance A1 Canary and protected production rollout;
- H4-B / S3: separate, bounded genuine BTC/ETH/SOL source collection and B2 market-decision continuation;
- H4-C / S4: correct H2-B **quota ledger replacement/reset**, prepare real-compatible Feishu one-shot sender and authenticated bounded inbound;
- H4-D / S5: end-to-end **mock** Binance → QUANT Core → Hermes canonical sender → Feishu p2p → read-only inquiry/reply with truthful evidence classes.

Do not reimplement existing R1/B1/B2/B3/B4/B5, H1/H2-A/H2-B/H3/H3-B or A1, or build a new strategy engine, sender, agent platform or raw exchange collector. Identify and amend the minimum technical deltas against accepted sealed inputs in your own isolated workroot. Keep QUANT Core authoritative and V1 frozen.

A missing real Owner-local value must lead to \`UNKNOWN / OWNER_ACTION_REQUIRED / BLOCKED_LIVE_GATE\`, not stop independent offline development in other approved phases. **No internal checkpoint in H4-A/B/C/D requires a new offline authorization** so long as all work stays within this exact dispatch, uses no external service, and changes no frozen boundary. Any material scope expansion requires a separate Controller decision.

## 2. Mandatory read-first and source preservation

**Executable:** \`/root/workspace/project/quant-0.8.0/\`, branch \`v0.8.0\`; record actual HEAD.
**Documentation:** adjacent \`quant-docs-engineering/\`, branch \`docs/engineering\`; record actual HEAD and whether it has advanced. Do not revert the canonical branch for historical QA HEAD pins.

Read the actual, immutable Controller receipts, not status prose:
- \`controller-decisions/V080_CONTROLLER_A1_B5_POST2_OFFLINE_CANDIDATE_SCOPED_ACCEPTANCE_20261121.json\` (SHA256 \`f0864075c3e88165109f961aa119b5bf11419814aab59f8d7f47e3fa32080759\`);
- \`controller-decisions/V080_CONTROLLER_H3B_GATE_A_OFFLINE_PREPARATION_SCOPED_ACCEPTANCE_20261121.json\`;
- \`controller-decisions/V080_CONTROLLER_H3_PHASE_A_OFFLINE_INTEGRATION_SCOPED_ACCEPTANCE_20261121.json\`;
- \`controller-decisions/V080_CONTROLLER_H2A_B5_PHASEB_OFFLINE_SCOPED_ACCEPTANCE_20261120.json\`;
- \`controller-decisions/V080_CONTROLLER_H2B_HERMES_FEISHU_OFFLINE_SCOPED_ACCEPTANCE_20261121.json\`;
- \`controller-decisions/V080_CONTROLLER_H1_P0_OFFLINE_REFERENCE_SCOPED_ACCEPTANCE_20261120.json\`.

A1 accepted wheel: \`quant_personal_live_public_b5-0.8.0b5.post2-py3-none-any.whl\`, SHA256 \`1acaae4e9e49bf3a0dd9313b3c21d45ee5cd2476b3fce80d024ab7c83608a56f\`.
A1 original seal: \`0c33ca5255a61dec0efa38ae2c2ba248907ff9375c22986ea7b7e97ba2ebe1ed\`. A1 Controller independent 237/237 offline QA passed using an **explicit review-only docs-head drift adaptation**, not an unchanged historical test harness. Do not erase or misrepresent this caveat.

At minimum read:
- A1: \`CONTROLLER_HANDOFF.md\`, \`A1_OWNER_LOCAL_FACT_SHEET.md\`, \`A1_CONTROLLER_PRE_ACTIVATION_CHECKLIST.md\`, \`A1_PROTECTED_ENROLLMENT_REVIEW.md\`, \`A1_RELEASE_BUILD_AND_PROVENANCE.md\`, \`A1_FIRST_TWO_GET_OPERATOR_RUNBOOK.md\`;
- H3-B: \`H3B_GATE_A_READINESS_MATRIX.md\`, \`H3B_MARKET_CONTINUATION_BLOCKERS.md\`, \`H3B_FEISHU_OUTBOUND_APPROVAL_PACKET.md\`, \`H3B_FEISHU_INBOUND_APPROVAL_PACKET.md\`, \`H3B_RELEASE_PROVISIONING_PLAN.md\`, \`H3B_PRODUCTION_UID_UDS_AND_SECRET_BOUNDARY.md\`, \`H3B_FIRST_BOUNDED_FIELD_TRIAL_RUNBOOK.md\`, \`H3B_REAL_EVIDENCE_AND_LATENCY_PROTOCOL.md\`, \`H3B_INITIAL_OPERATIONAL_BASELINE_CRITERIA.md\`;
- H3: \`H3_RUNTIME_COMPOSITION_AND_STARTUP.md\`, \`H3_INBOUND_AND_SIX_TOOL_CONFORMANCE.md\`, \`H3_LATENCY_MEASUREMENT_SCHEMA.md\`, \`H3_PI_P2_BASELINE_EXPORT_SCHEMA.md\`;
- Canonical docs: \`docs/project/V080_ROADMAP_AND_GATES_20261118.md\`, \`V080_TRADING_INTELLIGENCE_PLATFORM_ROADMAP_20261121.md\`, \`V080_CONTROLLER_TRADING_INTELLIGENCE_ROADMAP_SYNC_20261121.md\`, \`V080_HERMES_H_FIRST_PI_FIELD_TRIAL_SEQUENCE_20261120.md\`, \`docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md\` (frozen), \`docs/project/V080_MODEL_ROUTING_POLICY_20261119.md\`.

Verify protected Program J and sealed legacy artifacts. Preserve historical SHA256/Controller JSON and installed release provenance. Read actual code before introducing modules. Do not edit accepted worktrees.

## 3. Exact offline authority and write set

**Allowed writes:** the H4 workroot only, including independent copies of upstream files, isolated source deltas, synthetic fixtures, offline wheel candidates, local private QA state, redacted test artifacts and H4 handoff. No workroot creation by Controller is needed; the worker may create the exact named workroot under this authorized task.

**Not authorized:**
- ANY genuine Binance, Feishu or paid/free LLM provider DNS, TCP, HTTPS, websocket, OAuth, Bot message or account probe; no actual exchange public market-data fetch and no third-party connectivity diagnostic;
- any production credential, signing key or actual Owner/Controller digital signature; do not activate trust roots, enrollment or final production grant;
- actual Feishu application installation, privileged host routing/firewall/proxy change, live bot message, consumer-provider login, model call or continuous worker;
- recurrent scan, real +5/+10 reprice, genuine source polling, private Futures USER_DATA, Layer 3 TRADE, Pi P2, QI1/QL1/QB1/QR1 implementation, news monitoring or multi-market expansion;
- rewriting frozen V1, editing original approved workspaces or historical receipts.

Mock transports must be enforced in a separate Linux network namespace with only loopback and no default route. The mock Feishu client must not be able to create a real external attempt. For externally hosted vendor documentation, use existing locally available reference snapshots; do not call the exchange or provider and clearly label material not independently established.

All release candidates remain **default-deny**, with synthetic test keys only and no real production trust.

## 4. Internal Phase H4-A — S2 A1 production readiness

Start from accepted A1 **post2**, not older H2-A. Review the five accepted source changes (pyproject, trust, live, enrollment, ledger) and preserve the original disabled candidate.

Future S2 live operation requires **a separate exact dual approval**, and may then perform only:
1. \`GET https://fapi.binance.com/fapi/v1/time\`;
2. \`GET https://fapi.binance.com/fapi/v1/exchangeInfo\`.

Fixed order; **at most 2 requests and 2 known weight units**; zero retry, redirect, proxy fallback, Stage 2, background processing and private data. Expected successful result \`NOT_EVALUATED\`, **zero cards**, with true signed receipt/response provenance.

Build or specify only the minimum **offline** future production-derivative provisioning and release verification. Preserve:
- native \`H2A_OWNER_PUBLIC_SCOPE_V2\` staged request schema (do not silently substitute \`B5_OWNER_PUBLIC_SCOPE_V1\`) and \`B5_DUAL_APPROVAL_V1\`;
- exact code/wheel/scope/egress SHA, run ID, UTC validity, separate Owner/Controller Ed25519 verification keys, rejected QA keys, trusted CA+SNI+peer and exact route;
- dedicated nonroot UID, protected enrolled state/journal, precise registry/anchor identity, durable single-use \`SPENT\` marker prior to possible dispatch, fail-before-DNS and local revoke;
- hash-checked installation, clean vs mixed install and original inactive baseline.

**Known critical concern:** restoring only SQLite at the same inode is blocked by the SPENT witness, but a privileged rollback restoring **both** SQLite and protected enrollment bytes can erase the apparent consumption. Precisely threat-model the simultaneous rollback. Test suitable minimal personal-use countermeasures such as independently pinned monotonic witness, separated protected state, snapshot/restore exclusion, explicit recovery requiring new independent dual approval. Do not claim impossibility of administrator-level rollback without actual evidence; do not require an enterprise HSM or TPM by default. If impossible to verify on the intended host, record \`BLOCKED_PRODUCTION\` with clear Owner-local checks, not a mock PASS.

Owner-only values remain \`UNKNOWN\` until locally established and reviewed: applicable venue region/eligibility, approved direct network route, namespace/source/peer/CA, shared usage headroom, exact nonroot UID/storage/retention/durability, deployment trust keys and final wheel/scope/egress hashes. **Never infer eligibility from VPN location**.

Provide unsigned exact future A1 packet and minimal real operator preflight, with no actual approval or activation in H4.

## 5. Internal Phase H4-B — S3 genuine public market continuation

Preserve universe \`BTCUSDT, ETHUSDT, SOLUSDT\`; frames \`1d, 4h, 1h, 15m, 5m\`. QUANT Core alone owns 1D context, 4H regime, 1H setup, independent closed-15m trigger, 5m/quote actionability, 4H/1D obstacles, OI, funding, depth, mark, fees, SL/TP/net R, status and expiration.

H2-A accepted nominal Stage 2: **37 requests / 37 known IP-weight units + 3 fundingRate calls whose numeric general IP debit is UNKNOWN**. Canary + Stage 2 combined nominal 39 requests / 39 known units + 3 unresolved debits. Real market stages require **a new run authorized for both stages before dispatch**; a consumed Canary-only A1 run can never be upgraded.

Review authoritative available evidence for fundingRate general IP debit. Its funding-family 500 requests/5min/IP limit is **not** a numeric \`REQUEST_WEIGHT\` debit. Do not infer 0 or 1. If authoritative numeric debit is unavailable, keep \`FUNDING_WEIGHT_UNRESOLVED\`. Any altered route set or substitute field is a future **versioned scope/strategy contract proposal**, not silent automatic approval. Mark an absent B2-critical input \`UNKNOWN / NOT_EVALUATED / SOURCE_BLOCKED\` as genuinely required.

Provide exact proposed staged request list, numeric-known and unknown budgets, shared endpoint families (including OI 1000/5min/IP), egress and hard-stop handling, trusted latest K bars and availability windows, genuine provenance and source-to-B2 receipt integrity. Mock all physical transport. Test no lookahead, bad response, clock errors, funding gaps, NO_SETUP, WATCH, INVALID, SOURCE_BLOCKED, stale actionability and no invented EXECUTABLE.

Do not claim S3 live ready until **numeric evidence, exact full scope and Owner/0-C approval** exist.

## 6. Internal Phase H4-C — S4 Feishu production-safety defects and adapters

**Fix proposed H2-B production implementation, in an isolated derivative only**. Existing H2-B can recreate a replaced/deleted SQLite quota ledger and regain finite send allowance; a H3-B file-pin precheck has not been wired into actual sender. This is a P0 real-live blocker.

### C1 — durable one-attempt fencing
Bind exact H1 \`event_id\`, H2-B outbox digest, exact release/grant/run ID, recipient/channel, immutable provider UUID, protected enrollment, and independent durable quota witness. Check trusted state **before** quota use and immediately before any provider attempt. Missing/replaced database, inode change, rollback, crash before/after send, delayed ACK, duplicate worker, revocation or old approval must fail closed and never silently recreate budget. \`UNKNOWN_DELIVERY\` does **not** trigger blind retry or a new UUID. Preserve the single logical sender.

### C2 — production-compatible client (disabled)
Implement minimum versioned real Feishu/Lark client interface behind the **accepted canonical H1 renderer/outbox and H2-B sender**. Offline tests use fake credentials and a local mock; production factory cannot construct any external transport without future verified release+capability. Bind app, tenant, Owner app-scoped OpenID, p2p chat, single recipient, one provider attempt, stable UUID and explicit provider login/bootstrap budget. No group/broadcast, arbitrary network, model-selected send or Hermes native fallback. Provider ACK is not proof of human read.

### C3 — authenticated finite inbound
Create minimum isolated future ingress interface with signed/trusted provider callback identity, bound app/tenant/chat/Owner, replay protection, dedicated UID/UDS \`SO_PEERCRED\`, distinct durable inbound-turn and outbound-reply caps, finite startup/session lifetime, cancellation, teardown, typed failure/timeout. Real WebSocket and credential provisioning remain disabled. Deterministic model-free mock Owner inquiry and response must work.

Expose **exactly six read-only V1 callable/model-visible QUANT tools**, not general shell/browser/files/network/SQL/Feishu send/B3/TRADE:
\`list_active_signals\`,
\`get_signal_detail\`,
\`get_market_context\`,
\`get_latest_reprice\`,
\`get_signal_history\`,
\`get_strategy_summary\`.
\`request_reprice\` remains disabled. QUANT Core authority and frozen V1 untouched.

Test ledger deletion/replacement and rollbacks, same-path/new inode, startup race, wrong UID, callback spoof/replay, double reply, cap overspend, uncertain provider outcome, model absence and no resend. Distinguish **offline code corrected** from **real sender accepted and authorized**.

## 7. Internal Phase H4-D — S5 full offline chain

Compose the accepted source/B2 and protected H1/H2-B/H3/H3-B surfaces with H4 derivatives and one untrusted-model-free fallback path. Preserve immutable event/status/provenance and no second sender.

Mandatory deterministic scenarios:
1. Mock two-GET A1 \`NOT_EVALUATED\`, zero market cards.
2. Separately mocked future full-market stage with valid and incomplete data.
3. Actual B2 offline adapter outputs WATCH / EXECUTABLE / INVALID / NO_SETUP / SOURCE_BLOCKED according to fixtures.
4. H1 canonical digest and sender receive a Core-verified current eligible card **only if warranted**, or show truthful no-op/diagnostics.
5. H2-B corrected durable finite mock send attempt records ACK, rejection, or \`UNKNOWN_DELIVERY\`, without resend.
6. Authenticated fake Owner inbound p2p turn uses the exact six V1 tools and produces one bounded deterministic response.
7. Reprise stale/expired, invalidated, superseded, no-episode, unknown source, OI/funding gaps and replay after restart.
8. Distinct sample times (source availability/observation/Core evaluation/outbox/send/provider ACK/inbound/response) and freshness.
9. Synthetic +5/+10 snapshot/reprice retains \`SYNTHETIC_QA_ONLY\`; real reprice is never called.
10. Provider ACK != message read != actual trade; unknown outcomes stay unknown.

Do not merge real human feedback, synthetic tests, backtests and private account fills. No model dependency; optional future model is a distinct permission.

Give the Controller a future **single use bounded operator runbook** with discrete sign-off checkpoints. A real trial cannot be claimed complete from this synthetic pass.

## 8. Real-operation decision gates (outside H4 grant)

Create **separate unsigned** future packets and stop criteria:
- **S2-A1 Canary:** exact production release/scope/egress/run signatures, Owner eligibility, 2 GET/2 weight, no market/Feishu.
- **S3 market:** separate both-stage run from the start, fully known numeric weights and family limits, full source/causal scope.
- **S4 outbound:** one authorized deterministic private Feishu DM and exact sender/recipient/client/release, finite auth bootstrap, one attempt, no retry.
- **S4 inbound:** one bounded authenticated Owner private turn/reply and exact session/UID/channel limits, zero model requirement.
- **S5 first field trial:** actual genuine source→QUANT→Hermes→Feishu→authenticated human query response + classified real telemetry.
- **S6 recurring:** never authorized by H4; would require a future separate cadence, stop, budget and retention grant.

Evidence thresholds:
- \`OFFLINE_INTEGRATION_READY\`: synthetic all-path QA with no genuine service.
- \`PARTIAL_OPERATIONAL_BASELINE\`: separately authorized genuine Canary and/or Feishu smoke, but not full real source→recipient response.
- \`FIRST_REAL_H3_OPERATIONAL_BASELINE\`: independently accepted genuine source and QUANT state, real deterministic send evidence and authenticated Owner interaction, or clearly bounded truth about unavailable eligible events. Never fabricate a Core signal to meet a milestone.

One Canary does not authorize further GET. One Feishu ACK does not prove human read. A truthful NO_SETUP does not prove real signal-to-alert success. Pi P2 remains \`NOT_DISPATCHED\` and Owner-deferred until first qualified S5 actual-use evidence and a new dispatch.

## 9. Quality gates, delivery and independent review

Run all QA in isolated network namespace, plus clean/mixed reproducible candidate installation and source diff review. Check H2-B durable replacement, A1 SPENT/recovery, exact two mock GET, H2A/B5/B1/B2/B4 targeted regression, H1/H3 read-only V1 seven Python/Node cross-language goldens, H3-B identity/UDS tests, no private/TRADE imports, no real sockets or credentials, exact permission denial, expiration, idempotency, restart, simultaneous arrival and delayed ACK. Do not impose artificial PASS counts.

Capture exact PASS/FAIL/SKIP and original failures, hashes, timestamps, dependency SBOM/provenance, mock traces, no real network proof, negative and concurrency tests. Preserve accepted source releases unchanged. No worker self-acceptance.

**Required sealed outputs under H4 workroot:**
- \`H4_CONSOLIDATED_ARCHITECTURE_AND_SOURCE_AUDIT.md\`
- \`H4_S2_A1_PRODUCTION_PROVISIONING_READINESS.md\`
- \`H4_S2_ROLLBACK_AND_ENROLLMENT_SECURITY.md\`
- \`H4_S3_PUBLIC_MARKET_CONTINUATION_REVIEW.md\`
- \`H4_S3_FUNDING_WEIGHT_EVIDENCE_AND_DECISION.md\`
- \`H4_S4_H2B_LEDGER_SECURITY_FIX.md\`
- \`H4_S4_FEISHU_CLIENT_AND_INBOUND_COMPOSITION.md\`
- \`H4_S5_END_TO_END_OFFLINE_REHEARSAL.md\`
- \`H4_CAPABILITY_GATE_DECISION_MATRIX.md\`
- \`H4_FIRST_REAL_FIELD_TRIAL_OPERATOR_RUNBOOK.md\`
- \`H4_TELEMETRY_AND_OPERATIONAL_BASELINE.md\`
- \`H4_SECURITY_AND_QA_REPORT.md\`
- \`H4_RELEASE_AND_DEPENDENCY_PROVENANCE.md\`
- \`H4_OWNER_LOCAL_REQUIRED_INPUTS.md\`
- \`CONTROLLER_HANDOFF.md\`
- \`SHA256SUMS\`
- Isolated source, minimally versioned patch, wheel(s) where justified, offline mock adapters/fixtures, tests, CLI/runbook, unsigned future scope templates, structured QA evidence.

### Final disposition: ONE handoff in Chinese

Report one of:
- \`READY_FOR_CONTROLLER_REVIEW_OFFLINE_H4\`
- \`BLOCKED_MATERIAL_ARCHITECTURE\`
- \`BLOCKED_SECURITY\`
- \`BLOCKED_INPUT_WITH_OFFLINE_WORK_COMPLETED\`

Include actual executor ID, exact workroot, per-phase completion and residual HOLDs, all source/wheel/manifest hashes, independent-repeatable QA command and PASS/FAIL/SKIP, candidate real-client capability still disabled, whether H2-B replacement P0 was corrected in proposed code, remaining A1 dual-store rollback concern, authoritative evidence or remaining lack of numerical fundingRate debit, Owner-only missing production inputs, staged authorization packets and the **one next Controller decision**.

This H4 receipt authorizes all four internal **OFFLINE** engineering phases at once. No intermediate offline reauthorization is required. It does not authorize genuine S2/S3/S4/S5 calls, production release activation, private data, TRADE, Pi P2, QI1/QL1 or scheduled work.
