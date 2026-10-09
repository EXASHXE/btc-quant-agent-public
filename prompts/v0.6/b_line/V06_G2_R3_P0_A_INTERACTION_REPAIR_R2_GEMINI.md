# V06 G2 R3 P0 — Gemini A bounded cross-stage ReplayEngine / Ledger Repair R2

**ACTIVE IMPLEMENTATION DISPATCH.** This is the **one** consolidated post-B-R1 synthetic engineering repair, not a strategy search, source admission or empirical replay.

## 0. Immutable Controller authority and binding

- **TASK_ID:** `V06_G2_R3_P0_A_INTERACTION_REPAIR_R2`
- **REPOSITORY:** `EXASHXE/btc-quant-agent-public`
- **CONTROLLER_DISPATCH_SHA:** `218c126c9fd5395767fa27af984bf14b265c4a8f` (real immutable Controller decision commit; verify Git object and [Controller L2 adjudication](https://github.com/EXASHXE/btc-quant-agent-public/blob/218c126c9fd5395767fa27af984bf14b265c4a8f/reviews/v0.6/b_line/V06_G2_R3_P0_B_REAUDIT_CONTROLLER_L2_ADJUDICATION_AND_A_R2_DISPATCH.md)).
- **Original A branch:** `feature/v06-bline-g2-overnight-discovery-a`
- **START_SHA:** `5c542edd418a74b440162610fd540b1f01e423d3`, exact remote A branch HEAD expected at dispatch.
- **B finding source (immutable):** `f1ec703b7c7276582f324ac25b9d1000f1b5ef14`. [B matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/f1ec703b7c7276582f324ac25b9d1000f1b5ef14/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r1/A01_A08_INDEPENDENT_MATRIX.json), [synthetic receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/f1ec703b7c7276582f324ac25b9d1000f1b5ef14/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r1/INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json), [B independent repro test](https://github.com/EXASHXE/btc-quant-agent-public/blob/f1ec703b7c7276582f324ac25b9d1000f1b5ef14/tests/test_v06_g2_r3_verifier_repair_r1_reaudit.py).
- **R3 method:** `cf2d5cc33774cdcff7d709636305bba830e977ef`; **8 original candidates:** `e5b2006a89441f7eb2ec900e508aff451106b87a`; **code base:** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`.
- **Authority precedence:** pinned Controller adjudication + original accepted R3 frozen method; if a frozen clock/settlement rule is inconsistent, return `BLOCKED_SPEC_CONFLICT` with smallest counterexample instead of silently altering experiment definitions.
- **Prompt identity:** use THIS prompt's actually published commit ref (shown in link supplied by Controller) and its Git blob. The dispatch SHA above points to the Controller authority, not an invented commit containing this later Prompt.

## 1. Worktree and branch ownership

**Reuse**, without deletion or reset, the existing `~/workspace/project/quant-v0.6/g2-overnight-discovery-a` and its original A branch; do not start a new checkout. Inspect read-only:
```bash
set -euo pipefail
ROOT="$(cd "$HOME/workspace/project/quant-v0.6" && pwd -P)"
WT="$ROOT/g2-overnight-discovery-a"
BRANCH="feature/v06-bline-g2-overnight-discovery-a"
START_SHA="5c542edd418a74b440162610fd540b1f01e423d3"
test -d "$WT" || { echo BLOCKED_WORKTREE_MISSING; exit 2; }
test "$(git -C "$WT" branch --show-current)" = "$BRANCH" || { echo BLOCKED_WRONG_BRANCH; exit 2; }
test "$(git -C "$WT" rev-parse HEAD)" = "$START_SHA" || { echo BLOCKED_LOCAL_DRIFT; exit 2; }
test -z "$(git -C "$WT" status --porcelain=v1 --untracked-files=all)" || { echo BLOCKED_DIRTY_OWNER_STATE; exit 2; }
remote="$(git -C "$WT" remote get-url origin)"
case "$remote" in
  'https://github.com/EXASHXE/btc-quant-agent-public'|'https://github.com/EXASHXE/btc-quant-agent-public.git'|'git@github.com:EXASHXE/btc-quant-agent-public.git'|'ssh://git@github.com/EXASHXE/btc-quant-agent-public.git') ;;
  *) echo BLOCKED_REMOTE_IDENTITY; exit 2;;
esac
test "$(git -C "$WT" ls-remote --heads origin "$BRANCH" | awk '{print $1}')" = "$START_SHA" || { echo BLOCKED_REMOTE_DRIFT; exit 2; }
```

Inspect the immutable Controller SHA, this prompt from its pinned published ref, and immutable B receipt. Do **not** open live Gemini B/Sol worktrees, copy their ephemeral evidence into A source, or write to root sibling checkout. Serialize shared Git object fetch only if necessary. Do not inspect credentials or private exchange services.

**Allowed changed paths ONLY:**
- `src/btc_quant_agent/strategy_research/r3_overnight/**` (original eight-candidate design and parameters must remain unchanged)
- `tests/test_strategy_research_r3*.py`
- `docs/strategy_research/g2_r3/prep_a/repair_r2/**`
- `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r2/**`

No modifications under B `scripts/strategy_research/r3_verification/**`, B tests, original B evidence, original A R1 evidence, CI harness, H40 scientific golden, A-line, mainline, data, manifests, RC2, secrets or exchange keys. No protected or real market bytes, no network API calls beyond GitHub Git/CI.

## 2. Deliverable: fix all seven dynamic interactions as **one coherent change**

Start from B matrix and independently validate each source link; implement causally minimal engineering fixes, **not** changing eight frozen candidates, fees, risk tolerance, trade horizons, the 5% reserve, funding proxy rates, or pass thresholds.

### B01 (CRITICAL) — causal Mark Price stream
Existing ReplayEngine passes a MarkBar1m with timestamp at bar open O only to the same minute O, whereas Stage1 demands completed close O+60s and available_at<=O; thus its `last_available_marks` stays empty. Build a deterministic bounded pending/available mark stream or equivalent by **effective availability** with both `close_ms <= current_open_ms` and `available_at_ms <= current_open_ms`. Never use close/high/low of current/future bar. Preserve 120s mark freshness fail-close and symbol isolation; test arrival exactly close, delayed arrival, future, duplicate, missing, stale, and out-of-order marks. A synthetic ReplayEngine run must prove at least one mark is admitted when eligible, never before eligible; suitable positive controlled fixture must reach a genuine entry rather than an empty run.

### B02 (HIGH) — ACK idempotency
Introduce stable exactly-once acceptance identities for entry/exit/funding ACKs, including repeated delivery, delay, order inversion and stale closed positions. One economic event => one cash/fee/funding/commitment effect. A distinct new order or settlement remains valid. No zombie position or resurrection, preserve 4h/12h hold and legitimate fees on both sides; test repeated ACK delivery after terminal close and kill.

### B03 (HIGH) — hourly settlement ownership at exact boundary
Use frozen `[S-15_000, S+15_000]` ownership interval and explicitly defined economic position lifetime including same-minute SL/TP at S. Existing strict inequality misses preceding-minute edge; Stage6 deletion before Stage7 can also erase owing positions. Model occupancy via bounded immutable event-time exposure history/transition records or equivalent sufficient approach, **not** post-event future-knowledge leaks, false strict time precision or changing settlement schedules/fees. Prove just-before, at, just-after S, closed-before-window, and duplicate settlement IDs. If the accepted method does not resolve OHLC-only intraminute ambiguity, pick explicitly conservative contract-compatible ordering and document it; otherwise `BLOCKED_SPEC_CONFLICT` without misleading PASS.

### B04 (HIGH) — economic exit timestamps/cooldown
Do not stamp intraminute SL/TP at minute OPEN from a full-minute OHLC bar as if the price event was known then. Use a conservative deterministic minute-end effective timestamp / explicit resolution bound consistent with frozen method, prevent future outcome disclosure at prior opening, anchor `holding_minutes`, exit ACK availability, decision/cooldown checks consistently. Test same-bar SL/TP conflict (SL first), adverse opening gap, one-minute and 4h/12h expiry and previous-vs-next-hour decision clocks. This is about correcting semantics, not tweaking thresholds.

### B05 (HIGH) — economic vs available equity and kill reservation integrity
Decision equity must honor frozen ACK availability; economic exposure/risk must not vanish if an ACK is delayed. Keep distinct economic vs available PnL/obligations, preserve pre-ACK safety and conservative loss control without double counting. Drawdown kill cancels pending orders **but must not pre-release live exit/funding obligations**; each reserve exactly once when appropriate ACK is recognized. Assert no negative commitments, no phantom availability, no zombie, zero live reserve on fully reconciled flat book, insolvency fail-closed and no fresh entries after kill.

### B06 (MEDIUM / mandatory) — retest state progression
Maintain `bars_since_breakout`, 3-hour eligibility and all relevant intervening extrema for **each completed post-breakout hourly bar**, even when EMA or vol filters fail at an intermediate hour; filter failure cannot create a time skip or new confirmation. Avoid repeated advancement for same completed hour or shared state across 04H/12H, LONG/SHORT. Prove one failed hour, >3 elapsed hours, deep wick, opposite EMA, candidate permutation and rebound after invalid intermediate hour.

### B07 (CRITICAL) — funding reserve conservation
Align position-level reserved funding and aggregate `funding_reserve_rf` for each charged settlement, economic close, deferred funding ACK, repeated funding ACK, forced kill and terminal cash reconciliation; never release more than reserved, leak residual charge or silently allow negative reserve. Cash settlement should be counted once on ACK without letting late ACK create spendable phantom equity. Assert source/destination conservation with Decimal exactness.

## 3. Mandatory tests and evidence (L0/L1 developer)

Use A's existing 35 targeted tests **plus** new targeted metamorphic/integration cases in allowlisted test paths. Need a **real synthetic** `ReplayEngine.run_simulation` end-to-end path (input synthetic bars/marks only) showing nonzero causally eligible marks and a controlled successful signal/entry when geometry permits, plus 4h/12h holding and ledger reconciliation. Reject tricks like forcing `last_available_marks` from outside and calling that an integration PASS.

B re-audit test files were written to **assert R1 bugs exist**; obtaining PASS from them unchanged is NOT repair evidence. For each B01–B07 first document old R1 observed failing invariant, then add a separate **positive behavior invariant** in A R2 tests asserting correct after-state, not literal `0 marks`, double fee, negative reserve or leaked funding. Repro may be copied as conceptual synthetic fixtures only, not altering B code/owned worktree.

Recommended invariant checklist:
- Timeline trace with `bar_open_ms, bar_close_ms, available_at_ms, decision_ms, economic_entry_ms, economic_exit_ms, ack_ms, funding_S` and strict causal ordering.
- Mark accepted/as-of and stale/future rejection before any order sizing.
- Economic versus acknowledged positions, closed IDs, idempotent ACK repeated 2×/3×, and correct single fee.
- Funding occupancy [S-15s,S+15s], repeated S ownership, aggregate reserve conservation, no negative reserves on kill.
- Fixed eight IDs unchanged, 04H/12H horizons, no candidate state sharing or symbol state bleed.
- State permutation and deterministic receipt repeatability under BASE and STRESS, WAIT/no-fill/loss and adverse gap.
- Focused targeted Py3.12/Py3.13 (when present), Ruff/compile, changed JSON evidence parse and `git diff --check`.

Create these immutable **new** R2 paths:
- `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r2/R2_B01_B07_BEFORE_AFTER_MATRIX.json`
- `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r2/R2_SYNTHETIC_EXECUTION_RECEIPT.json`
- `docs/strategy_research/g2_r3/prep_a/repair_r2/R2_CONTROLLER_HANDOFF.md`

In evidence state known vs inferred distinctly, include exact tested identity SHA / evidence git blob/sha, each invariant test name, actual test and CI status, per-case expected vs observed values and any incomplete case. Preserve all existing receipts.

## 4. Stop-loss and auto-push

One cohesive R2 fix package with at most **one** same-scope iterative local correction after initial focused tests; no new seven-way dispatches and no retuning. If critical clock, funding or book invariant still fails, return `R2_BLOCKED_REPLAN_REQUIRED`, do not claim `ENGINE_PASS`.

On completing scoped checks:
1. Verify clean scope with `git diff --check`, `git diff --cached --name-status` and changed path allowlist.
2. Commit all owned code/tests/new R2 evidence on existing A branch and proactively **`git push -u origin feature/v06-bline-g2-overnight-discovery-a` without force**. Do not wait for user instruction. If Git/network fails: `BLOCKED_NOT_PUSHED`.
3. `git ls-remote --heads origin ...` to confirm exact terminal SHA, parent ancestry, changed files and no extra mutation. Report `REMOTE_PUSH_VERIFIED=true`, branch, source commit, evidence commit (if distinct), terminal SHA, original START_SHA, real CONTROLLER_DISPATCH_SHA, scoped PASS/FAIL evidence, CI link/conclusion if available.
4. Terminal is ONLY `R2_SYNTHETIC_REPAIR_READY_FOR_INDEPENDENT_B_REVIEW`, `R2_BLOCKED_REPLAN_REQUIRED`, `BLOCKED_SPEC_CONFLICT`, `BLOCKED_SCOPE_OR_GIT`, or `BLOCKED_NOT_PUSHED`. Passing implementation tests is NOT Controller P1 acceptance.
5. A's terminal push gets **one** independent Gemini B/Sol changed-path re-audit. If that finds material residuals, Controller re-plans the engine architecture instead of an open-ended patch cycle.

**Prohibited:** empirical historical price/mark/funding reads, protected holdouts, re-use of A-line scientific outcomes, unfreezing candidate list, authentic exchange API order access, OpenAI/Feishu credentialed trading, TESTNET or LIVE. `EMPIRICAL_PRICE_BODY_AUTHORITY=NONE`; `G4_TESTNET=NOT_AUTHORIZED`; `REAL_FUNDS_WRITE_AUTHORITY=NONE`; `AUTONOMOUS_LIVE=FORBIDDEN`.
