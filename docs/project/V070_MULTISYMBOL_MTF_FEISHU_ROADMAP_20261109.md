# Quant v0.7.0 — Multi-Symbol Intraday MTF + Feishu Operational MVP Roadmap

**Date:** 2026-11-09. **Controller:** 0-C. **Status:** Owner priorities adopted; stages are planned, not falsely marked released. [Handoff Home](V070_HANDOFF_HOME_20261109.md).

## North star and invariant

A bounded read-only market monitoring engine should find genuinely actionable **2–12h** opportunities, with eligible manual overnight extension up to 24h, and notify the Owner using Feishu while the plan remains valid for a **5–10 minute** human response. No account credentials, orders or auto trades. Time and source evidence are independent of strategy attractiveness.

## Product critical path

Eligible Universe → admitted market data → 4H regime/structure → 1H setup (WATCH) → completed 15m entry confirmation → fresh quote/5m cost and path revalidation → ENTRY_READY → durable outbox → Feishu → human manual trade → forward Shadow → research.

1D contextualizes risk and major levels; not a hard daily/4H alignment prerequisite. 5m is for validation rather than strategy direction. Real-time 5m checks are allowed only on prequalified candidates with bounded rates.

## Gates and owners

| Stage | Priority | Workstream / owner | Acceptance / stop |
| --- | --- | --- | --- |
| **Q0-A** | P0 | 0-C oversees accepted S offline base; bounded Source/clock/custody remedy | Independent current/retention anchor, external provenance, no-follow/race checks, whole-process deadline and explicit rights; SOURCE_BLOCKED until proven |
| **Q0-B** | P0 | Q0B worker delivered; 0-C independent acceptance pending | New MTF S1, correct completed 1H/15m causality, watch/ready and 1H-only control, 100-worker-test claim independently reproduced |
| **Q0-C** | P0 | Q0C worker delivered; 0-C independent acceptance pending | Durable mock Feishu outbox, TTL, idempotency, UNKNOWN_DELIVERY, 5–10m actionability; no real delivery |
| **Q0-D** | P0 | Integration worker after Q0B/Q0C admission and source interfaces review | One synthetic, end-to-end Source→MTF→outbox→Shadow→HTML run with restart/anti-duplicate, negative/partial-failure paths |
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
