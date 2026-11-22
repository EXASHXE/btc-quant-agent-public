# QUANT v0.8.0 — Owner Sequence: Hermes Operational First, Pi During Field Trial

- **Status:** ACTIVE / OWNER_DIRECTED / EXECUTION_SEQUENCE_ONLY
- **Owner update:** 2026-11-20, after P1 architecture acceptance and H1 P0 review
- **Applies to:** Controller 0-C, 1-A, Hermes H engineering and field-trial planning, future Pi P2 dispatch
- **Canonical docs:** docs/engineering; runtime evidence and Controller JSON remain in the v0.8.0 workspace
- **Supersedes:** the *forward-looking execution concurrency* in [the earlier Hermes-first / Pi-parallel plan](V080_HERMES_FIRST_PI_PARALLEL_PLAN_20261120.md). Historical H1/P1 worker assignments, acceptance and frozen V1 are not rewritten.

## 1. Owner's controlling decision

**Complete the Hermes + QUANT (H) route to an approved, usable real-operation loop first. Start actual Pi + QUANT P2 engineering only after that H loop has entered an authorized field trial and produced its initial operational feedback. Continue Pi offline development alongside ongoing Hermes field measurements, not alongside unfinished H1 integration.**

The already completed Pi P1 ADR is accepted ARCHITECTURE_ONLY and is preserved as a reference; do not start another Pi ADR, installation, P2 coding, runtime experiment or Pi Feishu deployment now. OpenClaw remains deferred.

Product priority is a real, human-usable QUANT market notification and read-only Feishu interaction workflow, not building and maintaining two unfinished Agent hosts.

This new sequencing is an Owner instruction about **future** work. It does not cancel, revise or retroactively de-authorize work that was already completed and accepted. It does not independently activate public network, Feishu, models, private account or TRADE.

## 2. Current evidence snapshot; recheck before every decision

- R1/B1–B4 scoped offline acceptance; B5 Phase A independently accepted OFFLINE_PHYSICAL_BINDING_READY, with genuine Phase B still NOT_AUTHORIZED.
- Pi P1: SCOPED_ACCEPTED_ARCHITECTURE_ONLY; Pi SDK v1.5.2 pinned from public source, not installed/run.
- Original Hermes H1: Controller HOLD_P0_CONTRACT_SEMANTICS_AND_GOLDEN_EXPORT despite 54 independently passing offline tests.
- **H1 P0 corrected package: independently accepted OFFLINE ONLY** by 0-C at 2026-11-20 18:25 HKT, receipt controller-decisions/V080_CONTROLLER_H1_P0_OFFLINE_REFERENCE_SCOPED_ACCEPTANCE_20261120.json. New isolated post1 wheel, 71/71 sealed files (manifest SHA256 90ff56de9175191e771b3de613aedf19267213ee842bec6f87b84817038268d4), independent 20 clean + 20 mixed + 23 Hermes = 63 PASS, Python/Node CROSS_LANGUAGE_MATCH_OK, seven vectors, and P0-C01/C02/C03 CLOSED_OFFLINE. Original H1 remains sealed historical evidence. This is NOT authorization for real Feishu/Binance/LLM.
- **P2 task draft:** a Controller-authored P2 task draft was briefly observed locally at 18:27 with READY_FOR_OWNER_FORWARDING / NOT_DISPATCHED, but it was not present in canonical tracked docs at final inspection. In any case, **the latest Owner H-FIRST execution choice overrides any proposed immediate P2 forwarding**. Do not send or run Pi P2 until H field-trial baseline and a fresh 0-C/Owner sequencing confirmation.
- Pi P2: OWNER_DEFERRED_UNTIL_H_FIELD_TRIAL / NOT_DISPATCHED. Its previous H1 interface blocker has been CLOSED_OFFLINE by independent Controller acceptance; the **Owner's sequencing gate is still active**. A task card being prepared or marked READY_FOR_OWNER_FORWARDING would not itself permit dispatch.

## 3. H-first delivery path and capability gates

| Stage | Objective and required evidence | Explicit exit | Who can activate |
|---|---|---|---|
| **H0 — Offline integration closure** | Corrected H1 post1 independently reviewed: P0-C01/C02/C03, Python/Node reference, Hermes/Feishu mocks, UDS and preservation | **COMPLETE: SCOPED_ACCEPTED_OFFLINE_HERMES_H1_REFERENCE_WITH_P0_FIXED_ONLY** | 0-C accepted offline evidence, not real service |
| **H1 — Genuine public-source readiness** | B5 Phase B exact official venue, eligible region/route, public GET/weight budget, trusted source/freshness and stop conditions | Separately accepted bounded real public canary; no automatic ongoing scan | Owner + 0-C distinct capability gate |
| **H2 — Real Feishu bounded activation** | Local bot setup by Owner, allowlisted private DM, recipient/app identity, secret protection, deterministic direct send, inbound Hermes read-only tools, model failure fallback and delivery ambiguity handling | Explicitly approved bounded real Feishu test and evidence | Owner + 0-C distinct Feishu gate |
| **H3 — Actual QUANT use and baseline collection** | Complete factual chain genuine market → QUANT card → deterministic H sender → private DM → human query/actionability check; collect real delivery/response latency, errors and user experience. Real notifications require an approved recurring collection/sending scope if beyond one-shot trials | An authorized field trial is genuinely underway and a first representative operational baseline exists, with known unknowns documented | No additional permission implicit; follow exact accepted run scope |
| **P2 engineering release** | H0 accepted (DONE) + H3 authorized field trial underway with initial actual baseline (PENDING) + fresh 0-C task scope/Owner deliberate forwarding | P2 offline coding may begin **while H3 continues**. Existing P2 READY draft alone does not satisfy Owner timing. No production sender change | Owner forwards after H3 begins; no auto-dispatch |

Stages H1 and H2 are independent capability grants and may be prepared separately. Neither can claim an end-to-end genuine-market notification without both qualified inputs and an approved sender. A no-setup genuine scan is a valid market result; do not fabricate EXECUTABLE or skip provenance rules to demonstrate functionality.

For H3, do not require a large statistically significant trading sample or profitable trades to begin P2. Require **initial usable operational evidence**: authenticated real channel interaction, a verified source-labeled QUANT read/response path within its approved data scope, deterministic send/receive telemetry and at least one human-query/reply or timeout/fallback sequence. Record what remains unobserved. Pi improvements are evaluated later through reproducible paired H/P fixtures and real H baseline; a first smoke test does not establish performance or profitability.

A one-off canary never implicitly permits continued recurring polling, automated reminders or unrestricted Feishu/LLM use. Owner/0-C must authorize any continuing cadence, service/recipient scope and termination conditions.

## 4. Architecture remains single-source and sender-owned

- QUANT Core is the only authority for market data, status, timestamps, reasons, Decimal prices/SL/TP/net R, versions, expiry, reprice and immutable journal.
- Hermes retains the one intended deterministic market-event outbox and single fenced Feishu sender, independent of any model's availability.
- Six Quant-Agent V1 tools are read-only. Model access to request_reprice, TRADE, private B3, general Shell, arbitrary network and files remains denied.
- Gemini/OpenAI auth is local Owner-provisioned and separately scoped, with no assumed Google AI Pro consumer API quota or unconditional ChatGPT OAuth right.
- Pi P2 is a **non-sending offline client/shadow candidate** that reuses independently accepted Hermes H1 golden vectors, V1 facade, renderer/outbox and identical fixtures. No second production bot, no dual-send, no auto-cutover.
- Real Hermes operational telemetry stays separated from synthetic QA. P2 cannot use private account payloads or live market calls as default fixtures.

## 5. What Pi learns from Hermes field use

During H3, collect issues and measurements for the future P2 task:
1. Feishu allowed user/DM interaction flows and misunderstood commands.
2. The six-tool request mix, model explanation correctness, refusal/fallback classes and actual token usage.
3. Source-to-outbox, ready-to-send, send-to-ack, inbound-to-reply p50/p95 where enough samples exist; otherwise use raw measurements and INCONCLUSIVE.
4. +5/+10-minute human actionability, expired/superseded alert suppression, duplicate and UNKNOWN_DELIVERY handling.
5. Operational installation, startup/restart, credential, upgrade, resource use and hands-on maintenance cost.
6. Information missing in V1 for actual user needs; any contract change requires a versioned decision and dual-reader fixtures rather than rewriting frozen V1.

After the first usable H baseline, Controller may issue a single integrated P2 **offline-only** package that consumes the accepted H1 reference and tests the Pi v1.5.2 SDK's active **and callable** tool inventories, hidden/deferred/MCP paths, host permissions, session isolation, mock provider and same event identities. P2 implementation may advance while Hermes stays in approved use. Pi adoption/cutover requires later comparable evidence and explicit Owner approval, not merely a passing prototype.

## 6. Controller responsibilities and dispatch discipline

- Mark future engineering queue **H_FIRST / P2_OWNER_DEFERRED**. The earlier plan title says parallel; it is historical and no longer defines current sequencing.
- H0 is complete. Do not dispatch P2, install Pi or commission another Pi architecture study until H3 actual-use baseline is established, even if a P2 draft is ready to forward.
- Immediately inspect the corrected H1 P0 workroot and latest Controller receipts; independently review if ready, without duplicating the existing worker.
- Prepare the bounded B5 and Feishu activations as separate scope-specific decisions. Never treat this document as activation.
- After H3 begins and telemetry arrives, assemble one field-feedback-derived P2 task card and request Owner forwarding. Preserve H-only production ownership during Pi experiments.
- Keep implementation work packages substantial and Controller reviews consolidated. This does not relax individual evidence or capability gates.

**Next action as of this document:** H1 P0 corrected OFFLINE reference is independently accepted. Controller 0-C should now prepare the H-only, separately authorized B5 Phase B genuine public canary and real Feishu private-DM limited activation, followed by actual Hermes field-trial telemetry. Do **not** forward P2 despite its prepared draft until the H real-use baseline exists.

## 7. Subsequent Trading Intelligence business-value roadmap (Owner 2026-11-21)

After an independently observed S5 first real Hermes loop, prioritize [QI1 AI Opportunity Intelligence and QL1 Signal Lifecycle/Outcome](V080_TRADING_INTELLIGENCE_PLATFORM_ROADMAP_20261121.md) as domain modules independent of the Hermes/Pi runtime. QI1 may pre-analyze WATCH candidates with validated evidence, bounded latency and model-free first-alert fallback. QL1 should preserve episode, delivery, model annotation, human response and observed hypothetical-vs-verified outcome axes; it feeds the historical/backtest **QB1** and experimental research **QR1**. Keep optional Pi P2 a deferred runtime comparison, not a blocker to QI1/QL1. Defer QN1 news and QM1 multi-venue until the core lifecycle, research and data contracts are demonstrably stable. Existing S0–S8 / Controller A1 gates and the frozen V1 remain unchanged.

## Latest H4 and offline-start status — 2026-11-21 19:58

H4 S2–S5 integration accepted OFFLINE ONLY after 336 Controller PASS and 103 sealed items. S2 real A1 two GET remains BLOCKED_PRODUCTION_AND_INPUT_NOT_AUTHORIZED, S3 fundingRate weight unresolved, S4 real Feishu identity/client not authorized and S5 real human-use baseline absent. The immediate priority is bounded Owner-local S2 readiness, not Pi P2. A task explicitly forwarded by Owner for OFFLINE work may start without a redundant Controller dispatch JSON under [Owner Direct Offline Protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md). Neither that offline start nor this H4 status grants real network access or self-acceptance.

## 2026-11-22/23 evidence sync — H-first remains controlling

Local optional Feishu onboarding Mode0 Core CLI and Mode1 Hermes six local reads are independently accepted **OFFLINE**. Mode2 real Feishu remains disabled. Sol S2 V2 is accepted as a synthetic default-disabled wheel; the genuine physical two-GET Canary still has no authorized real transport, eligible KR route proof or one-run signatures. Astra S3 study retains Plan A as the intended genuine B2 source contract but historical fundingRate debit `d` is unknown. See [latest verified progress / next gates](V080_PROGRESS_AND_NEXT_GATES_20261123.md).

Priority now: minimal Sol S2 physical-wire OFFLINE candidate parallel to minimal Owner/Neon KR-WSL2 evidence and Owner Feishu setup; **independent real S2 readiness/grant milestone** next; conditional Sol S3 zero-retry offline work does not replace the live gate. Local Mode0 observations can validate UX only; the genuine S5 H/Feishu human loop still needs separate S3/S4 grants and actual observed evidence. Pi P2 remains Owner-deferred until an initial H field baseline.
