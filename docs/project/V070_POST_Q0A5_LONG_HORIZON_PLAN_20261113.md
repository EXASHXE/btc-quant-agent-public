## Controller status update — 2026-11-13

**P0 complete:** `ACCEPT_Q0A5_FULL_L0_OFFLINE_SCOPED` (local Controller decision `controller-decisions/V070_Q0A5_FULL_L0_CONTROLLER_CLOSURE_20261113.json`), built on accepted Windows G1 and WSL G2/G3. The long-horizon roadmap below is still the forward plan, but its P0 phase is CLOSED within synthetic three-symbol L0 scope. See [full closure and prioritized P1 clock/source blockers](V070_Q0A5_FULL_L0_CLOSURE_AND_P1_SOURCE_READINESS_20261113.md).

**Next P1:** Source/clock trust. Windows host source observed as Local CMOS Clock with Leap=3/Stratum=0 and strict UTC unqualified; Windows localized `w32tm` decode raises UnicodeDecodeError in `win_clock.py`. Synthetic Windows/WSL semantic parity is not UTC/real public Source qualification. Transport/access/rate/capture/retention designs and two separate L1 authorization envelopes remain open. Hydrogen may handle single-file decode-only L0-S test-led repair; Sol/Astra remain leads for trust/provenance/Outbox semantic changes when capacity available. V3.8 11-case synthetic study and 69/21/7 registry are **proposals only**, not real economic validation.

---

# Quant v0.7.0 — Post-Q0A5 Long-Horizon Roadmap (Controller proposal, 2026-11-13)

> **Status: PROPOSED ROADMAP / PROMPT-ONLY / NO EXECUTOR DISPATCH.**
>
> Canonical progress: local `controller-decisions/V070_Q0A5_G1_WINDOWS_NATIVE_SCOPED_CONTROLLER_ACCEPTANCE_20261113.json`, `controller-decisions/V070_Q0A5_FIX02_G2G3_SCOPED_CONTROLLER_ACCEPTANCE_20261113.json`. Scope is synthetic L0 only. Full G0–G4 `Q0A5` stage is **not yet accepted**. Neither real Source nor real Feishu is enabled or qualified.

## Owner-facing overview (中文)

产品目标是 **Binance USDT-M 只读 2–12 小时机会监控**：1D 背景、4H regime、已收盘 1H setup、已收盘 15m 入场触发、5m/quote 行动性。Feishu 最终用于通知可在 5–10 分钟内响应的人工交易者；绝不自动下单。先三标的 BTC/ETH/SOL 完成证据闭环，后扩展至 >=10 个高流动性标的。用户关注 ZEC/HYPE/INJ/ARB/ARIA/ERA/AAVE/INIT，但任何实盘覆盖应以当时 Binance 上架、数据权限、流动性和 Source 资格为准。

**Critical path:** 0) whole-Q0A5 L0 Controller closure → 1) clock/data Source qualification → 2) bounded real read-only 3-symbol pilot → 3) human notification channel canary → 4) prospective Shadow and actionable quality assessment → 5) universe expansion / Factor Registry / operations hardening. Factor and strategy research can run as independent L0 documentation but cannot substitute for real-source evidence.

Current G1 acceptance is evidence-based: Hydrogen reported native Windows 58/58 tests; Controller independently compared **287 actual NTFS staging files** and **5 wheel binaries** against inventories, read actual Windows SQLite/summary, validated WSL business summary parity, and reviewed 58 unique test receipts. Controller did **not** independently execute a second native Windows test process; the distinction remains recorded. Native G1 accepted is not full Q0A5 L0 acceptance.

## Phase-gated roadmap

| Phase | Work package / lead | Output | Objective exit gate | Forbidden inference |
|---|---|---|---|---|
| **P0 / immediately** | **Q0A5 G0–G4 full L0 Controller closure** (0-C; Hydrogen may prepare dossier) | One consolidated G0/G1/G2/G3/G4 matrix, hashes, Windows/WSL parity, prior Controller decisions, disabled R1.2 and reproducible mock receipts | 0-C independently evaluates integrated critical path, signs `ACCEPT_Q0A5_FULL_L0_SCOPED` or narrow `NEEDS_SPECIFIC_FIX` | Cannot claim real source, delivery, Alpha, M2 live |
| **P1** | **Host clock & Source readiness architecture** (Astra design if available; 0-C interim; Hydrogen simple inventory; Sol high-risk engineering) | Source/clock provenance, Windows vs WSL clock test matrix, causer/sequence/quote age and failed-clock diagnostics | Demonstrable trusted time basis; quote <=30s, current snapshot <=1s; 1H/15m completed candle causality; no WSL jitter unqualified silently converted to READY | Windows SQLite PASS does not imply host clock qualification |
| **P2** | **3-symbol real public Source bounded canary** (L1 once Owner sets scope; Sol implements, 0-C accepts) | Binance public USDT-M adapter/evidence replay; ledger/raw/manifest cross-check, rate/weight budget, OI/depth/funding where authorized, Source status matrix | Strict GET/weight caps, provenance/region/rights, clock fence, samples and veto behavior; unknown source is BLOCKED not NO_SETUP | Prior single-shot authorizations are not standing L1 grants |
| **P3** | **Feishu one-recipient real notification canary** (separate L1; Sol/0-C) | Secret-handling and opt-in channel envelope; precise provider response/UNKNOWN/TTL receipts | Recipient and payload agreement, one message/s, human delivery/read not claimed absent proof; no automatic resend for UNKNOWN | Mock PROVIDER_ACCEPTED is not real Feishu delivery |
| **P4** | **Prospective Shadow / V3.8 quality evaluation** (0-C study; Astra for architecture; Sol for code; Hydrogen fixtures/reports) | Pre-registered opportunity-card record, entry timing, SL/TP1-3, net fee-adjusted R, ATR buffer, 4H/1D obstacles, OI/order book evidence, timing delay, false negatives, regime | Sufficient clock- and source-qualified prospective cases with unmodified history, realistic costs and delayed human response; confidence intervals and negative-outcome attribution, no lookahead | No claims of positive Alpha or automatic execution |
| **P5** | **Universe expansion + Factor Registry / Strategy Lab** (Sol/Astra research architecture; Hydrogen registry/docs) | Bring additional liquid symbols on line only after 3-symbol gating; reconcile baseline 69 factors/21 strategies/7 combos; controlled ablation and orthogonal evaluation; latest 1H setup and 15m trigger | Per-symbol liquidity/freshness/rate-safe budgets, explainability, protected holdout separation, differential error metrics, no untested strategy activation | Backtest or test count is not prospectively validated profitability |
| **P6** | **Ops reliability, observer dashboard and release review** (Sol implementation; 0-C release) | Restart/clock-fail/Source-fail/Outbox-UNKNOWN drills, audit dashboard, retention, operator runbook, bounded alert runtime | Repeatable operator drill, real channel status separated from source/strategy status, human acknowledgment and risk parameters | No L2 trading authority, accounts or auto-orders |

### Queue sequencing and branch boundaries

- One P0 critical path; no duplicate ownership for Source adapters, Q0BC Outbox, Feishu or Shadow.
- **Hydrogen L0-S only** by default: source inventory, exact deterministic fixtures, documentation, SQLite inspection, harmless reproducibility scripts, test matrix and minimal known-contract one-file changes. For quota-blocked Sol tasks, produce an implementation-ready spec rather than silently changing persistence, clock/source trust or notification state machines.
- **Sol L0-M** when capacity returns: cross-platform persistence, Source/Outbox boundary, ingestion, scheduler and qualifying notification mechanics.
- **Astra L0-X** when available: host-time trust/provenance model, adaptive activation, prospective evaluation statistical design and major release gates.
- Controller 0-C owns dispatch, narrowing, independent acceptance, status labels and L1 gate escalation. All work must state base revisions, allowed writes, negative tests, STOP criteria, and no live API calls except under the explicit later L1 envelope.

### L1/L2 hard separation

- L0 offline authorization covers routine coding, docs, tests, synthetic market fixtures, mock provider and local reproducibility; no repetitive authorization requests.
- L1 first real public Binance capture requires **one bounded Owner operating-envelope decision** (venue/region/right/endpoints/universe/requests/retention/cancellation). L1 first real Feishu send requires a **separate** channel/recipient/secrets/hours/card-type/stop envelope. Neither is activated in this roadmap.
- L2 accounts, trading keys/orders, protected holdout, system-level clock/service changes and privileged host modifications remain prohibited without distinct authority. Automated trading is outside this product.

## Recommended next long-runner (Hydrogen, prompt-only)

**Task ID:** `V070-POST-Q0A5-L0-TO-SOURCE-READINESS-PREPARATION-01`.

Perform sequential L0-S packages within one isolated documentation/test-readiness workspace:
A. Consolidate the accepted G1 and G2/G3 evidence and unresolved whole-Q0A5 G0/G4 stage checklist; do **not** sign Controller decision.
B. Inventory Windows clock/WSL clock and read-only Source trust affordances through existing code, offline logs and host metrics only; no system changes or Binance HTTP.
C. Prepare reproducible synthetic negative fixtures for epoch/generation/15m-close boundary, stale quote, 1s snapshot, 30s quote, missing 1H setup, rate cap and R1.2 disabled, avoiding high-risk runtime edits.
D. Document the 3-symbol public-data canary L1 envelope as a proposal only, including Korea region/rights checks and OI/depth endpoint budgets; do not access APIs.
E. Document a separate Feishu human-canary L1 envelope with 1 message/s and provider/UNKNOWN/read distinctions; no send or secret reads.
F. Draft a Factor Registry and V3.8 study inventory anchored to actual 69/21/7 definitions; preserve controls and scientifically invalidated claims. If inventories cannot be found, report UNKNOWN instead of inventing factors.
G. Deliver exact owner-facing handoff, Controller risk matrix, stop criteria, status, and ready-to-dispatch Sol/Astra package specs. Controller 0-C retains full stage and L1 decisions.

**STOP** if work needs changing a high-impact time/source/ledger/Outbox/Feishu state machine, enabling real calls or privileged host operations. Do not launch another agent, and do not make background/recurring promises.

## Proposed success metrics / non-success metrics

Metrics: contract coverage, evidence rate per symbol/TF, source missing/unknown vs no-setup denominator, scan close-to-alert latency, stale quote rejection, 1 msg/s mock/live channel budget, no duplicate Outbox on replay, 4H/1D remaining-space checks, false-negative tracking, fee+slippage-adjusted net R, minimum ready-time for human response, and prospective consistency across regimes.

Separate dashboards:
1. **Engineering integrity** (pass/fail/restart/ownership).
2. **Data trust** (clock/source/rights/provenance/candles).
3. **Notification delivery** (provider vs human).
4. **Strategy economics** (prospective, risk-adjusted; unknown until observed).

L0 PASS must never be displayed as profitable strategy or as a real-time executable alert.

## State at authorship

- G1 Windows: `ACCEPT_G1_WINDOWS_NATIVE_OFFLINE_SCOPED` via independent artifact audit; native second-process rerun not done by Controller.
- G2/G3: `ACCEPT_G2G3_OFFLINE_SCOPED`.
- Q0A5 full G0–G4: **PENDING_CONTROLLER_INTEGRATED_REVIEW**.
- Real Source and Feishu: **NOT APPROVED IN THIS PLAN / BLOCKED**.
- `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false`.

This document is a roadmap, not an execution receipt or an external authorization.
