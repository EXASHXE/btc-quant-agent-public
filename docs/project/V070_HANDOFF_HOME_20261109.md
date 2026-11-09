# Quant v0.7.0 — Active Handoff Home / 新对话入口

**Updated:** 2026-11-09 (Asia/Singapore +08:00)
**Canonical documents:** GitHub [docs/engineering](https://github.com/EXASHXE/btc-quant-agent-public/tree/docs/engineering).
**Status:** product plan ACTIVE; latest engineering deliveries have differing acceptance levels. This handoff page is the single preferred startup index for new conversations.

> **NEW OWNER RULE — 2026-11-09:** Subsequent work is **PROMPT FIRST**. Without fresh explicit Owner approval for the exact action, no Codex/Gemini worker dispatch, test/script execution, live source scan, Feishu send, OS change, deployment, code edit, GitHub update or scheduled task. Previous standing offline authority is superseded. This document-only update was specifically requested.
>
> **CURRENT Q0 SNAPSHOT (2026-11-09 16:48 +08:00):** Q0A/B/C worker processes completed (exit 0), no Codex worker was active. Q0A: 67 PASS / 11 SKIP, SHA 54/54; native timeout 120,021.7979ms **exceeds** 120s; 45 out-of-scope parent `.pyc` files, unchanged 332 original O code hashes. Q0B: worker 100 PASS, independent 209/209 manifest hashes; Q0C: worker 37 PASS, independent 24/24 digest hashes. Q0B/C tests not independently rerun and **formal 0-C acceptances pending**. Current real Source/MTF/Feishu/Shadow remain unqualified.

## 1. Start here

| Conversation | Role | New-chat bootstrap |
| --- | --- | --- |
| **Controller 0-C** | Sole engineering dispatcher, Controller acceptance, bounded execution and integration | **[Open CURRENT 0-C new-chat prompt](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261109_Q0_POST_DELIVERY_READONLY.md)** |
| **Strategic Advisor 1-A** | Independent Owner-facing architecture, quant-science and release challenger; not a second worker dispatcher | **[Open full 1-A new-chat prompt](../../prompts/v0.7/V070_NEW_CHAT_1A_20261109_Q0.md)** |

Copy the complete relevant Markdown prompt into a *new* conversation. The new-chat prompts link back to this home and mandate checking later evidence before asserting unchanged status. Existing 2026-11-02 prompts are historical, not current Q0 starting points.

## 2. Project and roles

- [Verified status, acceptance boundaries and Q0 packages](V070_STATUS_AND_WORKPACKAGES_20261109_Q0.md)
- [Operational MVP roadmap — multi-symbol, 4H/1H/15m, Feishu](V070_MULTISYMBOL_MTF_FEISHU_ROADMAP_20261109.md)
- [Active role matrix and evidence/dispatch ownership](../roles/V070_ACTIVE_ROLE_MATRIX_20261109.md)
- [Controller 0-C role](../roles/V070_CONTROLLER_0C_ROLE_20261109.md)
- [1-A independent advisor role](../roles/V070_CHATGPT_1A_STRATEGIC_ADVISOR.md)
- [Canonical branch policy](V070_DOCUMENTATION_BRANCH_POLICY.md)
- [Long-history Program A–P status (historical, superseded for current Q0)](V070_STATUS_AND_HANDOFF_20261109.md)
- [Independent deep code-review prompt](../../prompts/v0.7/V070_EXTERNAL_FULL_CODE_STRATEGY_REVIEW_20261109.md)

## 3. Source code — separate from documentation authority

- **[Current review branch, O baseline plus S/Q0B/Q0C source packages](https://github.com/EXASHXE/btc-quant-agent-public/tree/review/v070-q0-s-mtf-feishu-offline-20261109)**. Incremental package root: [review-packages/](https://github.com/EXASHXE/btc-quant-agent-public/tree/review/v070-q0-s-mtf-feishu-offline-20261109/review-packages). Publication commit: [e704a6e](https://github.com/EXASHXE/btc-quant-agent-public/commit/e704a6ef872f0c4e45ef9fb8bcbf368f1b03e87d).
- [Program O full offline-accepted application source](https://github.com/EXASHXE/btc-quant-agent-public/tree/review/v070-q0-s-mtf-feishu-offline-20261109/v070-app). Historical offline implementation, not a live qualified release.
- [Program S accepted offline Windows handoff source](https://github.com/EXASHXE/btc-quant-agent-public/tree/review/v070-q0-s-mtf-feishu-offline-20261109/review-packages/program-s-windows-offline) — 0-C accepted **only offline historical audit and simulated handoff**, current real Source blocked.
- [Q0B intraday multi-timeframe S1 source](https://github.com/EXASHXE/btc-quant-agent-public/tree/review/v070-q0-s-mtf-feishu-offline-20261109/review-packages/q0b-mtf-offline-pending) — worker delivered; **Controller acceptance pending**.
- [Q0C Feishu durable outbox source](https://github.com/EXASHXE/btc-quant-agent-public/tree/review/v070-q0-s-mtf-feishu-offline-20261109/review-packages/q0c-feishu-offline-pending) — MOCK only; **Controller acceptance pending**.
- [Source SHA-256 and code-export status manifest](https://github.com/EXASHXE/btc-quant-agent-public/blob/review/v070-q0-s-mtf-feishu-offline-20261109/review-packages/REVIEW_MANIFEST.json).

These are **public-safe unintegrated review exports**, not the canonical application integration branch. They are not a proof of live deployment, successful actual Binance scan, executable trade edge, actual Feishu delivery or source/economic qualification. All canonical planning and role updates live only on docs/engineering.

## 4. The Owner's current product contract

**Goal:** bounded, reliable read-only crypto intraday multi-symbol monitoring and genuine timely Feishu notification of credible trade opportunities; Owner manually opens trades within approximately 5–10 minutes after an actionable alert. Primary holding 2–12h; predeclared optional overnight up to 24h. No auto order execution.

- 1D: higher-level context and risk only.
- 4H: trend/range regime and major structure.
- 1H: candidate strategy setup and structural plan.
- 15m: *completed-bar* entry confirmation and ENTRY_READY promotion.
- Latest price/5m: revalidate actionability and invalidation; no standalone trade direction.
- Initially S1 trend pullback only; S2 breakout/retest, S3 range mean reversion, S4 failed breakout remain research hypotheses.
- Staged universe: 3-symbol first authentic slice → at least 10 liquid symbols → ~20 selected → up to 50 after capacity, quota and source-rights evidence.
- Signals: WATCH, ENTRY_READY, INVALIDATED/EXPIRED, NO_SETUP, SOURCE_BLOCKED/UNKNOWN. Feishu entry alert requires fresh admissible Source, 5–10m surviving entry validity and deterministic risk/cost controls.
- Compare Quant's actual prospective value to the Owner's useful but not economically certified ChatGPT V3.0 monitor; do not claim superior win rate from more code.

## 5. Verified status snapshot (do not promote)

| Delivery | Latest evidence | Current authority |
| --- | --- | --- |
| Program O offline product | 672 distinct offline regression cases; Controller-accepted scoped | **Accepted offline**, no strict real Source/Shadow |
| Program N real public transport | 22 real HTTP 200 GETs; clock fail-closed before admission; raw subsequently scoped-purged | Real market scan **not qualified** |
| Program P2 WSL clock stop | Failed at ~3.29s, rolled back; Controller scoped receipt exists | Host still **not qualified** |
| Program S Windows handoff | 26 Windows, 11 WSL, 672 O tests; 1195 QPC samples over 120.025s; 14 fabricated TLS requests | Controller decision **2026-11-09 08:03 UTC: offline historical audit only**; current Source blocked |
| Q0B intraday MTF | Worker claims 100 offline pytest with fixtures, 1H/15m WATCH/READY, 3/10/50 budgeting | **Pending independent 0-C review and integration** |
| Q0C Feishu outbox | Worker delivered SQLite durable MOCK adapter, guarded notifications and examples | **Pending independent 0-C review; no real Feishu transport** |
| Q0A Windows Source closure | Worker completed but strict native 120s deadline and present/source/NTFS gates fail | **SOURCE_BLOCKED; acceptance pending** |

**Global:** SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; current real market advisory/alert=NOT READY; ACCOUNT_UNKNOWN/ACCOUNT_VETO. No real trading/positions/orders.

## 6. Next Controller action / no duplicate worker

0-C should read the local actual receipts, check active writers/locks, independently review pending Q0B/Q0C for accept/reject with explicit tests and cross-integration compatibility, reconcile Program S scope, and plan one bounded Q0A closure plus narrow integration gate. No worker may self-accept. Do **not** dispatch duplicate Q0B/Q0C before inspecting their new deliveries.

Priority: **trusted Source → accepted 4H/1H/15m pipeline → test-safe Feishu outbox → bounded authorized real data and provider delivery → forward Shadow**. Avoid large refactors before the first true end-to-end outcome.

## 7. Permissions and safety

Standing approval covers scoped offline coding, static audit, tests, mock transport, documentation and Controller task coordination. Real Binance captures, long-running monitors, actual Feishu delivery, host-service changes, protected data and new Source/region/retention scope require their own checks and precise authorization. Historical PRIMARY/holdout prohibitions remain. No API trading key, account action, fund movement or autonomous execution. A copied prompt or a public GitHub branch conveys no runtime authority.
