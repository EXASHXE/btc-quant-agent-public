# Quant v0.7.0 — Independent Architecture and Research Convergence (2026-11-02)

**Canonical:** `docs/engineering`. **Decision status:** proposed Route B for Controller 0-C to verify and dispatch; NO implementation, native source permission, trading permission, or economic qualification is established by this document.

## Provenance and precedence

- Gemini Argon and Claude submitted independent external reviews on 2026-11-02. Their reports are Owner-supplied inputs, NOT implementation receipts.
- Gemini reported code-level inspection of the frozen source snapshot; Claude explicitly disclosed it could read project documentation but not Python files. Their confidence levels differ.
- The strategic advisor independently inspected GitHub source at `snapshot/v070-l4-session04-long-20261102` (commit `ab5a9be2f520f82a6e77d62d632f1a70a88164b3`).
- Reviewer-friendly source + docs projection: `review/v070-source-shadow-docs-20261102`, commit `3d314ac3e70bb3247b4f3266d2f8e8905bd44438`. **Not an integrated executable.**
- Latest independently inspected LOCAL Session04 receipt: `l4-readonly-source-canary-01/SESSION04_AUTHORIZATION_CLOSURE_FINAL.md` and `SESSION04_AUTHORIZATION_CLOSURE_ACCEPTANCE.json`, recorded 2026-11-02T03:37:15Z. It says `READY_FOR_OWNER_SIGNING`, no real signer, grant, UTC window, Session04 output or native request.
- The Owner subsequently reported "Session04 signing closure and single native diagnostic completed." This claim has **NOT** yet been reconciled against an accepted later native report. See [Evidence reconciliation](V070_SESSION04_EVIDENCE_RECONCILIATION_20261102.md). The reported completion MUST NOT silently overwrite the verified local receipt.

## Product objective and evidence tiers

`genuine bounded public input -> trustworthy Source/clock/journal -> L23 single-playbook state -> WATCH/ARMED + market-side geometry -> actual subsequently received 1/3/5-minute quote checks -> existing local dashboard -> prospective usefulness/cost evaluation`.

Four separate gates:
1. BBO-only native **diagnostic** health: telemetry, queue, budget, provenance, replay.
2. Multi-feed real **Source qualification**: market/public WS routes, completed 1m/5m bars, continuity and clocks.
3. Market-side **Shadow advisory**: genuine WATCH/ARMED/expired/veto/conditional survival; no implied account permission.
4. **Account/economic**: user-reported vs exchange-verified fills, capital, margin and slippage/funding. UNKNOWN/ACCOUNT_VETO until explicit evidence; never fake net PnL or Alpha.

## Independent reviews — consensus

Both recommend **Route B: minimum integrated vertical slice** over running disconnected Session04/LONG indefinitely or rewriting the entire system.
- Two separated snapshots are not one working source-to-dashboard runtime; reconcile Source Session04 instrumentation with LONG feature/selector/Shadow/view behavior in one isolated integration workspace.
- Genuine Session03 stopped `PARTIAL/BACKPRESSURE_BLOCKED` at queue 128: 9,153 BBO WS frames, 5,246 clock-qualified BBO, 147 raw/normalized pairs. Root cause of the original native stall remains UNKNOWN.
- Source per-frame SQLite and `PublicJournal._write()` transaction boundaries are verified fragile code paths; profile and narrowly remediate with deterministic replay/stall/crash tests before assuming their contribution to the native failure.
- Focus on one market-side playbook (initially `trend_pullback`) across BTC/ETH/SOL, realistic `NO_SETUP`, stale quote veto and subsequently received 1/3/5-minute opportunity survival, reusing existing `latest.json` / HTML dashboard.
- Shift product value from unproven 4–24h BTC directional Alpha claims toward trustworthy opportunity-quality/survival and human position-risk advice; research funding/basis carry as a **separate, non-blocking mechanism**, not an established profitable strategy.

## Reconciled code-level findings

**Verified from remote source:**
- `canary/control.py:BudgetGuard.data_message()` invokes a precheck and charged SQLite transaction on each admitted WS data message. `CanaryStore` creates a `canary_budget(scope,mono_ms)` index while the cleanup predicates only on `mono_ms`: investigate query plans and tail latency.
- `canary/public_journal.py:PublicJournal._write()` starts `BEGIN IMMEDIATE` before JSON encoding, gzip compression, `used()` directory inspection, file and directory fsync, and then performs an additional metadata update transaction. Minimize lock-held work only after proving hash-chain, allocation, concurrent-writer, crash/orphan recovery and byte replay safety.
- `platform/selection/selector.py` returns unavailable cross-sectional ranks when 3 < minimum 10 and filters formally selected setups with vetoes. **But** `PublicEngine.discover()` still creates WATCH episodes from `candidates`; it is false to say that WATCH lifecycle code cannot run at all. Separate market-side conditional evidence from rank/account/order eligibility; never fabricate the ten-member denominator.
- LONG snapshot `configs/canary/endpoints.json` already specifies `/public/ws/{symbol}@bookTicker` and `/market/ws/{symbol}@kline_{interval}`; LONG grants permit TWO connections. Verify actual transport construction and route tests; avoid an unsupported claim that routing is absent.
- `source-session04/public_data.py` contains an older fixed START/END bar-boundary check, while LONG uses dynamic `start/end` in its corresponding path. Resolve this in any consolidated future-dated runtime.
- `clock_eligibility.py` has a 300,000 ms signed handoff bundle limit; that is distinct from LONG's fresh native clock probes. An optional split of historical attestation lifetime vs live probe freshness requires a specific threat-model and signed-contract review, not an automatic extension.

**Not yet established:**
- Which of SQLite, fsync, scheduling, burst arrival, host time discontinuity or interacting tails caused the exact Session03 native stop.
- Exact latency/throughput speedups from any proposed patch.
- Any single unified Source+LONG release, qualified multi-feed run, live Shadow advisory, 1/3/5-minute real survival estimate, or after-cost Alpha.

## Disputed proposals and decision

| Proposal | Controller disposition |
| --- | --- |
| Narrow transaction/index/connection/journal optimization with stage timings, offline replay and crash tests | **PRIORITY M1, evidence-gated** |
| Single isolated integration worktree: merge Session04 telemetry with LONG L23/Shadow/dashboard, reconcile divergent windows and manifests | **PRIORITY M1** |
| One-playbook, three-symbol market-side state and opportunity survival with separate account veto | **PRIORITY M1** |
| Previously completed 5m-bar REST startup warmup | **OFFLINE MOCK NOW**; live pre-start lookback only if exact new Owner data scope, PIT availability/receipt and limits are approved |
| WS route review | **VERIFY**, since LONG already declares both /public and /market and two connections |
| Latest-wins conflation, delayed per-frame charging, group-commit semantics | **DEFER pending strict durability, raw/event loss, budget and changed-admission contract proofs/approval** |
| Change 50ms sticky hard stop to resumable clock epochs | **DO NOT APPLY by default**; independent safety contract and Owner decision |
| Extend 300s signed historical attestation validity to 24h or remove fingerprints | **DEFER**; risk analysis, fresh native probes and signed contractual amendments required |
| 10+ assets, all 21 strategies, more generic factor work, third dashboard, full asyncio/Kafka rewrite | **NOT ON M1 CRITICAL PATH** |
| Funding/basis carry monitoring and user-reported position risk | **NON-BLOCKING research/product backlog**, cost/source/PIT checks before deployment |

## Three acceptance milestones (no live activity is authorized here)

**M1 — OFFLINE integrated Source→Shadow vertical slice and narrow hot-path repair.**
Controller checks actual local worker locks, dirty trees, code diffs and newer accepted receipts. Produce one coherent Codex mandate in a new isolated workspace; preserve sealed Session03, pure offline tests and full stage accounting. Acceptance: code conflict map; unchanged canonical raw/normalized hashes or explained identical canonical replay semantics; crash/orphan reconciliation; baseline vs fixed P50/P95/P99/HWM, injected 2s stalls/disk/lock bursts; exact two WS routes; one-playbook WATCH/ARMED/veto + 1/3/5 newer-quote replay + existing local dashboard, no misleading account status.

**M2 — One independently authorized bounded native diagnostic, only after status reconciliation.**
If a newer genuine signed native Session04 acceptance EXISTS, validate its authority, exact source/hash/window, immutable report/receipt seal, queue/latency/replay and mark either PASS/PARTIAL/BLOCKED, and **do not replay a consumed one-shot**. If no verified later receipt exists, retain `READY_FOR_OWNER_SIGNING` and propose a new exact ≤180s diagnostic owner decision; never self-sign, fabricate, or launch. A diagnostic pass is not full Source qualification.

**M3 — Distinct finite multi-feed Source plus concurrent local Shadow.**
Requires a separately signed exact LONG authority, native clock proof and eligible Source. First bounded authentic 3-symbol multi-feed observational window, including separately authorized pre-start bar warmup if needed; yield local dashboards from first qualified completed bars; then extend to ≤48h based on objective evidence. Report real watch/no-setup/veto/revalidation counts and censored/UNKNOWN, not fake fills or PnL.

## Roles and dispatch

- **Owner:** goals, explicit new permissions, launch windows, signing identity/public trust, protected data, account/trading approvals.
- **Controller 0-C:** ONLY roadmap owner, single queue, conflict/lock check, cohesive Codex task allocation, evidence-based acceptance.
- **1-A / Strategic Advisor:** independent strategy, architecture, scientific and product challenge; no competing implementation dispatch queue.
- **Codex:** one coherent authorized offline engineering phase; report code, tests, perf, run state and preservation. No unauthorized market collection.
- **Gemini, Claude, Opus:** optional consultative review, no automatic authority or repeated approval requirement.

## Research priority

1. Product measurement: `Opportunity Survival Meter` 1/3/5 minutes after truthful candidate observation; exact quote chronology, spread/staleness/no-chase, censoring and assumed human response.
2. Initial `trend_pullback` only as an engineering and prospective falsification playbook, not a declared return-generating edge.
3. Funding/basis carry and funding/OI crowding **hypotheses**, source/access/cost requirements and feasible manual horizon; do not use paid CoinDesk or proprietary data by default.
4. Defer 10+ cross-sectional strategies, new broad historical trials, PRIMARY, protected 2024+ and FINAL_HOLDOUT.

## Reference links

- [Current status](V070_SOURCE_TO_ADVISORY_CLOSURE_STATUS_20261102.md)
- [Session04 evidence discrepancy](V070_SESSION04_EVIDENCE_RECONCILIATION_20261102.md)
- [Roadmap](V070_ADVISORY_ROADMAP.md)
- [Handoff](V070_CURRENT_STATE_AND_HANDOFF.md)
- [0-C launch prompt](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C.md)
- [1-A launch prompt](../../prompts/v0.7/V070_NEW_CHAT_1A.md)
