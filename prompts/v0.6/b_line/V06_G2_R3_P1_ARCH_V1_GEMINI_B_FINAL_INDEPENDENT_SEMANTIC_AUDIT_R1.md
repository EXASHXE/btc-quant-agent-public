# Gemini B — P1 Architecture V1 exact-SHA final independent semantic audit (one terminal pass)

**TASK_ID:** `V06_G2_R3_P1_ARCH_V1_B_FINAL_INDEPENDENT_SEMANTIC_AUDIT_R1`.
**Role:** independent adversarial execution/semantic verifier, not Gemini A implementation worker. No engineering patch authority, no real-data experiment.
**CONTROLLER_DISPATCH_SHA:** `5f9b7f75215b394ad86d49b468e7acd9a89c23a2` — verify real Controller-owned [decision and audit authorization](https://github.com/EXASHXE/btc-quant-agent-public/blob/5f9b7f75215b394ad86d49b468e7acd9a89c23a2/reviews/v0.6/b_line/V06_G2_R3_P1_ARCH_V1_A_FINAL_CI_CONTROLLER_L2_ACCEPTANCE_AND_B_DISPATCH_R1.md), not a mere hex string.
**Repository:** `EXASHXE/btc-quant-agent-public`.
**B owned worktree:** `/root/workspace/project/quant-v0.6/g2-overnight-verifier-b` (reuse existing **only if unchanged/clean**).
**B existing branch:** `feature/v06-bline-g2-overnight-verifier-b`.
**Exact B START/remote HEAD:** `068a4005f68b5ee4a970063cb1f3bc524a08784a`.
**A immutable audited HEAD:** `b5d34aacd36dc27454944a22436db555c3f6eeb8`.
**A architecture implementation ancestor:** `89d0c211cff96286203e4fb7459a51042c1257f1`.
**A pre-fix evidence:** `398e6bab0cdedf07a93827019ca4bf1bf913c7f9`.
**Original independently rejected A R2:** `2c60b0653d3619eedf457753511a9ecc84c1cd5b`.
**Frozen 8-candidate design SHA:** `e5b2006a89441f7eb2ec900e508aff451106b87a`.
**Method addendum SHA:** `cf2d5cc33774cdcff7d709636305bba830e977ef`.
**Model:** Gemini B; prioritize strict independent positive+adversarial executable proof, not paraphrasing the A report. Use one bounded session and publish.

## Step 0 — immutable binding / safe worktree

1. Read full immutable Controller decision at SHA `5f9b7f7...`, this separately pinned Prompt (provided in invoking message), prior B exact-source [R2 audit](https://github.com/EXASHXE/btc-quant-agent-public/blob/068a4005f68b5ee4a970063cb1f3bc524a08784a/docs/strategy_research/g2_r3/prep_b/repair_r2/B_R2_FINAL_CONTROLLER_HANDOFF.md), [old B positive/negative matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/068a4005f68b5ee4a970063cb1f3bc524a08784a/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/B01_B07_R2_INDEPENDENT_BEHAVIOR_MATRIX.json), and A's [current receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/b5d34aacd36dc27454944a22436db555c3f6eeb8/evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/ARCHITECTURE_SYNTHETIC_EXECUTION_RECEIPT.json). Bind exact blobs and terminal parent SHAs.
2. Verify GitHub remote origin, B local branch/HEAD/clean working tree and B remote branch HEAD both exactly `068a4005...`, and immutable A target is a descendant of original A via the two architecture commits + maintenance. If any B files changed by others or local worktree unowned/dirty, STOP `BLOCKED_IDENTITY_OR_SCOPE`; do not reset, stash, clean, force push or modify any other worktree.
3. Materialize ONLY A target source/tests via `git archive` or `git show` into a fresh safe ephemeral directory under `/tmp`, **outside** B/A worktrees and WITHOUT market data. Never execute an unspecified working A tree, never silently import locally installed stale package instead of exact A SHA. Bind `PYTHONPATH` to temp A root and verify `inspect.getfile(ReplayEngine)` or equivalent points at the exact archive.
4. **Allowed B edits only:**
   - `scripts/strategy_research/r3_verification/architecture_v1/**`
   - `tests/test_v06_g2_r3_verifier_architecture_*.py`
   - `docs/strategy_research/g2_r3/prep_b/architecture_v1/**`
   - `evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/**`.
   Your fixtures run/read immutable A source but no new code/test fixes on A; no write to original B R2 cases. B owned verification artifacts must describe source ref, exact line/call and actual observed outputs.
5. No raw real price/Mark/funding/OI/orderbook/aggTrade bodies, no private API credentials, old Final Holdout, A-line sealed results or strategy experiments. Nontrading synthetic only; TESTNET/LIVE none.

## Step 1 — independently verify A new correction, CI and method identity

- [A full CI run 37918930513](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37918930513) shows `SUCCESS`, `2844 passed/2 skipped/9 warnings`, Ruff and mypy `170 source files no issues`, compileall. Reconcile commit and workflow plan. **CI success is engineering evidence, not a semantic verdict.**
- Verify frozen `CandidateRegistry().list_candidates()` source returns exactly `STRUCTURAL_CONTINUATION` / `CLOSED_RETEST` × LONG/SHORT × 04H/12H, correct candidate family/horizons. Confirm correct relative parent tree, no drift to original design/registry/fees/PIT/holdout, and no new `c01_...` artifact names.
- A receipt has `CLOSED_RETEST_LONG_04H` and BASE `CLOSED_RETEST_LONG_12H` nonzero synthetic trades and cash reconciliation. Confirm from independently executed exact A source at current SHA, not from hard-coded receipt values; 12H STRESS is expressly geometry-ineligible and must stay retained as INELIGIBLE/WAIT, never silently labeled losing or dropped. Verify at least one actual `ReplayEngine.run_simulation` signal→order→fill→ACK→funding→exit→final flat; verify cumulative res/symbol and independent candidate book equality under input order permutations.
- Treat local `59 passed` for each 3.12/3.13 as reported executor tests unless independently re-run; full CI 2844 verified but only code-invariance, no independent oracle.

## Step 2 — mandatory adversarial matrix and positive behavior assertions

Add independent tests that CALL actual fresh A code. Do not copy A's new fixture unchanged; include alternative inputs and different expected values. Cover each:

| Critical ID | New independent synthetic checks / failure to seek | Pass only if |
|---|---|---|
| B01 | Same symbol delayed older mark and fresher mark arriving in reverse order; source same-close duplicates with conflicting prices/source IDs; mark effective available_at later than close; gap >120s; multisymbol interleavings | freshest causally eligible CLOSE chosen, never overwrite by late older close, conflicting same-close fails closed or deterministic source-authority rule, stale entry veto, no future OHLC leak |
| B02 | Fill/exit/funding ACK duplicated 2×/3×; same event ID changed payload; ACK arrives after close/reopen; order_id vs position_id identity collision | monetary and position effects applied once, different true owner events remain separate, contradictory reused ID rejects rather than silently merges |
| B03 | EXIT economic at S−1ms, ACK at S Stage1, Funding S Stage7; same symbol P1 close then P2 open in settlement window, differing quantities; disjoint older pending exit; duplicate S with reversed input order; funding ACK late | (position_id,S) separate charge, owner reserve retained through pending finalization, owner trade net and cash reconcile after late ACK, no previous owner overwritten |
| B04 | Intraminute SL and TP both touched, adverse gap, favorable target gap capped, minute-end economic exit and Ack delay, expiry 240m/720m after fill, 4h cooldown | never assumes favorable OHLC path, no lookahead, deterministic exit with correct clocks and no over-credit |
| B05 | pre-ACK economic fill q>0 then valid as-of Mark implies ≥125 USDT loss; same pending position with +125 gain; newly scheduled duplicate entry after kill; stale Mark while ACK late; committed gross/exposure reserve | negative pre-ACK exposure affects risk kill when visible; positive gain not spendable; no phantom capital, reservations not prematurely released, kill cancels future opens |
| B06 | breakout closed-hour H25, hours 26–29 skipped by cooldown/filters, H30 attempted stale retest; H28 third unconfirmed hour also forms fresh breakout, invalid intermediate extrema; swap all candidate evaluation order | elapsed real closed-hour window, state isolated by candidate/symbol/side, no retroactive confirmations; any third-hour new breakout must be explicitly justified by original method before calling it PASS |
| B07 | BTC owned reserve 0.4 USDT with 1.0 debit; unrelated ETH 2.0, latent exit ACK, cancellation/kill, future settlement; post-funding and terminal cash reconciliations; negative-before-clamp attack | BTC shortfall 0.6 recorded once to its fee/liability/cash, ETH reserve remains 2, aggregate equals per-owner sum, no orphan charged settlement IDs or negative clipping |

**Cross-stage tests are mandatory.** In particular B03/B05/B07 should run compound events at a single settlement with two positions, delayed exit ACK, duplicate funding ACK and another symbol reserved: the system must conserve `cash, costs, funding, risk` at EACH relevant phase, not merely a flat terminal `>=0`.

## Step 3 — methodological falsification concerns

1. **Regime/Retest freeze.** A code allows new breakout on the same third completed bar after prior retest expired; verify the accepted method explicitly allows this and cannot create same-event duplicate orders. If method unresolvable, return `ARCH_V1_B_EVIDENCE_INCOMPLETE`, not silently redefine frozen rule.
2. **Funding conservative ownership.** `[S-15000,S+15000]` is a bounded *uncertainty* window; if an intraminute interval's close is not known until 1m end, A Stage7 must not feed a future-sourced event into a pre-S decision. Economic charge and causal ACK timestamps must stay separate. Same-open exit/reentry may be forbidden by strategy scheduling; test ledger ownership as synthetic contract but do not interpret it as new strategy permission.
3. **Funding reserve and cash book.** Check position entry reservation conversion, remaining funding reserve at every S, cash charge exactly once and timed Funding ACK, surprise debit beyond owner reserve. If owner shortfall is merely subtracted from cash without an explicit auditable liability, record the exact conflict severity.
4. **Economic risk under delayed ACK.** Causally available marks and incomplete economic exposure must govern conservative decisions, but future bar high/low/close must never be usable at its current minute open. Check negative PnL from pre-ACK exposure before first ack and late-arrival marks.
5. **Actual nonzero Replay E2E.** A reused fixture has 240h warmup; verify generated completed 1h/4h indicators and timestamps, recorded entry and fee/funding vs source. Attempt one disjoint fixture with different sign/edge if affordable; if too costly, document coverage precisely, not a fabricated 8/8 full stress validation.
6. **Scientific/financial safety.** Frozen eight candidates, no real market outcome, no H41/H42 cross-import, cost parameters only proxies; P1 acceptance cannot prove expected profit or permit P4.

## Step 4 — test execution and finite audit budget

- Use Python3.12 test run for independently authored B-owned architecture suite against TEMP ARCHIVED A SHA; optionally Python3.13. Scope linter, compile, JSON parse and `git diff --check`.
- Do NOT run a repeat 15-minute full repository suite to prove A CI already succeeded, unless a newly witnessed distinct bug actually requires broader suite. Baseline run is pinned `37918930513`. Original R2 B independent suite was 35 green on its own immutable target, not proof for current A.
- One final independent semantic review only; no fix/retune commits to A and no iterative R4/R5 back-and-forth. Evidence package can include explicit blockers; terminate if fundamental ledger/state inconsistency.

**Deliver exactly:**
1. `docs/strategy_research/g2_r3/prep_b/architecture_v1/B_FINAL_INDEPENDENT_ARCHITECTURE_VERDICT.md`: exact provenance/CI, all B01–B07 positive/negative witness and 8-Stage timeline, A acceptance / blocker list by severity, as-of and reserve audit, P3 acceptability and fallback.
2. `evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B01_B07_FINAL_INDEPENDENT_BEHAVIOR_MATRIX.json`: at least one positive and one boundary/adversarial case per B01/B03/B05/B06/B07 plus B02/B04; `case_id, test_node, input_clocks, expected, observed, pass_or_blocked, a_source_sha`, no copying A observed claims as independent.
3. `evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B_FINAL_SYNTHETIC_EXECUTION_RECEIPT.json`: exact B start, A target, real Controller dispatch/prompt hashes, isolated tested module path, actual test commands and pass count, sample cost/reserve traces, total empirical/protected/exchange reads 0 within execution scope and environment assumptions.
4. `tests/test_v06_g2_r3_verifier_architecture_*.py` AND optionally supporting B-only independent test scripts in allowlisted B namespace.

**Required final verdict exactly one**:
- `ARCH_V1_B_INDEPENDENT_SEMANTIC_ACCEPTABLE_FOR_CONTROLLER` — all mandatory adversarial tests pass with exact A source, no unresolved material semantic/PIT/cost ledger contradictions; P1 eligible for Controller science/engine acceptance only.
- `ARCH_V1_B_SEMANTIC_BLOCKED_REPLAN_ALTERNATIVE_ENGINE` — at least one material fail/unsafe invariant; Controller terminates architecture route, not R4 patch.
- `ARCH_V1_B_EVIDENCE_INCOMPLETE` — unclosed actual behavior/protected authority or test coverage; no ACCEPT/P3; prioritize falsifiable exact gap and whether alternative engine needed.
- `BLOCKED_IDENTITY_OR_SCOPE` — branch/target/permission binding failure.
- `BLOCKED_NOT_PUSHED` — commit exists but remote not verified.

Finish without asking user to manually push: change only B-owned allowlisted files, `git diff --check`, create one coherent commit, push NON-FORCE to `feature/v06-bline-g2-overnight-verifier-b`, verify `git ls-remote` exact HEAD, parent = `068a4005...`, changed-file list and CI status. No local-only PASS. Report `TASK_ID, CONTROLLER_DISPATCH_SHA, PINNED_PROMPT_SHA, A_TARGET_SHA, B_START_SHA, B_FINAL_REMOTE_SHA, REMOTE_PUSH_VERIFIED, CI, FOCUSED_TESTS, B01_B07_VERDICTS, MATERIAL_BLOCKERS, TERMINAL_VERDICT`.

**Unchanged:** `P1_ACCEPTED=false` until Controller reviews B; `P2_SOURCE_ADMITTED=false`; `P3_FIRST_PUSHED_PREREG_SHA=NONE`; `P4_MARKET_BODY_AUTHORITY=NONE`; `TESTNET=NOT_AUTHORIZED`; `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
