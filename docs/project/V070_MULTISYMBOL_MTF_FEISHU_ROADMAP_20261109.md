# Quant v0.7.0 — Multi-Symbol Intraday MTF + Feishu Operational MVP Roadmap

> **LATEST 2026-11-11 OWNER WORKFLOW / MVP CLOSURE:** [Current MVP Home](V070_MVP_CLOSURE_HOME_20261111.md) · [Lean delegated execution](V070_EXECUTION_DELEGATION_POLICY_20261111.md) · [Three Gemini report review and fast roadmap](V070_GEMINI_PREFLIGHT_REVIEW_AND_FAST_MVP_PLAN_20261111.md) · [New 0-C start](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261111_MVP_CLOSURE.md). Routine offline coding, mock tests, documentation and Codex/Gemini coordination no longer require approval for every task/SHA. Earlier 2026-11-09 PROMPT-ONLY restrictions are superseded for such work. Actual Source/Feishu external activation and privileged/account/financial actions remain separate gates. Q0BC positive semantic proof is still blocked on Controller provenance; Source remains unqualified.

**Date:** 2026-11-09. **Controller:** 0-C. **Status:** Owner priorities adopted; stages are planned, not falsely marked released. [Handoff Home](V070_HANDOFF_HOME_20261109.md).

> **POST-Q0 DELIVERY UPDATE — 2026-11-09:** All three Q0A/B/C workers completed. Q0A: 67 PASS/11 SKIP; 120021.7979ms strict process timeout failed, current Source still BLOCKED, 45 generated parent caches require reconciliation. Q0B: 100 worker-reported PASS and 209 SHA verified; Q0C: 37 worker-reported PASS and 24 SHA verified. Q0B/C formal Controller acceptance and Q0D integration are not complete. **Owner requires PROMPT FIRST and fresh approval before any task, even offline worker/tests.** [Updated bootstrap](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261109_Q0_POST_DELIVERY_READONLY.md).

## North star and invariant

A bounded read-only market monitoring engine should find genuinely actionable **2–12h** opportunities, with eligible manual overnight extension up to 24h, and notify the Owner using Feishu while the plan remains valid for a **5–10 minute** human response. No account credentials, orders or auto trades. Time and source evidence are independent of strategy attractiveness.

## Product critical path

Eligible Universe → admitted market data → 4H regime/structure → 1H setup (WATCH) → completed 15m entry confirmation → fresh quote/5m cost and path revalidation → ENTRY_READY → durable outbox → Feishu → human manual trade → forward Shadow → research.

1D contextualizes risk and major levels; not a hard daily/4H alignment prerequisite. 5m is for validation rather than strategy direction. Real-time 5m checks are allowed only on prequalified candidates with bounded rates.

## Gates and owners

| Stage | Priority | Workstream / owner | Acceptance / stop |
| --- | --- | --- | --- |
| **Q0-A / Q0A2 proposed** | P0 | Q0A worker finished; next improvement requires fresh Owner approval | JUnit 67 PASS/11 SKIP, full-process 120s exceeded by 21.8ms; current/retention, provenance and fixed NTFS writer/race still blocked; 45 `.pyc` incident |
| **Q0-B** | P0 | Q0B worker finished; independent 209 SHA verified; separate formal 0-C acceptance pending | 100 tests worker-reported, NOT independently rerun; synthetic-only 1H/15m |
| **Q0-C** | P0 | Q0C worker finished; independent 24 SHA verified; formal 0-C acceptance pending | 37 tests worker-reported, NOT independently rerun; mock provider only |
| **Q0-D proposed** | P0 | Full task prompt only; **no worker authorized** | After separate Q0B/C scoped acceptance and fresh Owner approval, synthetic Source→MTF→outbox→Shadow→HTML with restart, anti-duplicate and negative paths |
| **Q1** | P0 | 0-C approves new finite real Source and actual Feishu channel separately | Real signed-off 3-symbol Source→genuine plan/NO_SETUP; real Feishu provider acceptance evidence and accurate statuses; no account action |
| **Q2** | P0/P1 | Liquid universe & bounded scheduler | 10 symbols first, then ~20, optional 50; official quota weight, cache/recovery/isolated per-symbol failure and 5-minute candidate revalidation |
| **Q3** | P1 | Regime/multi-strategy study | Trend×volatility with hysteresis; S1 only production candidate; S2/S3/S4 research-only |
| **Q4** | P1/P2 | Shadow, independent economics, safe refactor | 5/10-minute actionability after alerts; no-fill/missed/ambiguous counts; safe code reduction; C V1 preserved, C V2 power/cluster independently proposed |

## Cadence and notification contract (design targets, not a standing live permission)

- Universe status/volume discovery: every 6–12 hours within approved endpoint/cache permissions.
- 4H regime: once after each completed 4H close.
- 1H setup: after completed 1H close; WATCH may be recorded without 15m.
- 15m entry trigger: on completed 15m close, only for valid prior 1H WATCH; never treat 15m as independent entry strategy.
- Current-price eligibility: around every 5 minutes only for near-actionable candidates, with bounded HTTP/cache and fresh quote source proof.
- ENTRY_READY notification: after all gates, queue promptly. Target P95 signal-to-provider-accepted ≤120s to be measured; this is **not** evidence of human delivery/read.
- Expired/invalidated alerts: send only for already-notified candidates and only when fresh trusted evidence supports state change. Suppress duplicates and alert floods.

## Product priorities and safe reductions

Prioritize correctness and first useful live vertical slice before large refactors. Keep current append-only storage, causality rules, Shadow and dashboard. After integration, audit 55 SHA-identical file groups, 90 duplicate copies and competing CLI/Source/render paths in small reviewable PRs, with package/hash and original sealed-evidence preservation tests.

The scientific protocol is separate: DeepSeek reports excessive C week-connected clustering and a conservatively large estimated required sample (~15k independent clusters under current Hoeffding assumptions). Reproduce independently, retain frozen C V1, and predeclare any separate V2 evaluation. More signals do not prove alpha.

## Release checklist

- Source rights, time, clocks and lineage independently valid for **new** exact sessions; no protected-holdout reads.
- No lookahead at any 1D/4H/1H/15m candle boundary; quote and spread freshness explicit.
- No hardcoded mandatory BTC/ETH/SOL batch membership after universe extension; each symbol handled independently except global time/source veto.
- Deterministic risk/geometry, costs, expiry, rate limits, missed entry, STOP/no-chase and ambiguous outcomes.
- Synthetic/real evidence class cannot be silently upgraded and does not reach the same alert destination as actionable signals without authorization.
- Feishu protected configuration, provider result/UNKNOWN semantics, durable alert outbox, restart and suppression proven.
- Real provider accepted is distinct from user read, user decision, orders and realized PnL; no trading actions performed.
- Public code snapshot never a substitute for 0-C integration acceptance or successful native runtime.

## Owner decisions required later, not before offline work

Confirm the intended Feishu recipient/group and protected webhook setup; approve a bounded real message test and real data session with current venue rights/region/retention, exact endpoints/symbols/time/output/caps. No blanket approval is inferred from this plan. Controller should continue safe offline integration and independent acceptance without repeated ordinary permissions.
