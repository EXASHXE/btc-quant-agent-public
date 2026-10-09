# B-line v0.6 — Gemini B independent re-audit L2 adjudication and bounded A Repair R2 dispatch

**Decision:** `P1_REPAIR_REQUIRED__B_R1_EVIDENCE_RECEIVED__AUTHORIZE_SINGLE_BOUNDED_A_R2`. This is a Controller docs-only gate; it is NOT G2 engine acceptance, empirical data admission, Alpha, TESTNET, or LIVE authorization.

## Authority / exact identity

- Main v0.6 code HEAD: `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`.
- Gemini A current verified branch HEAD and **repair start**: `5c542edd418a74b440162610fd540b1f01e423d3`.
- Gemini B independent terminal review branch: `feature/v06-bline-g2-overnight-verifier-b@f1ec703b7c7276582f324ac25b9d1000f1b5ef14`, direct child of `a0aacd105ac3f3173b15d91c869990748178e222`; six changed paths within B allowlist.
- B final verdict: `P0_B_REPAIR_DISCREPANCY_BLOCKED`. [Finding matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/f1ec703b7c7276582f324ac25b9d1000f1b5ef14/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r1/A01_A08_INDEPENDENT_MATRIX.json); [observed synthetic receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/f1ec703b7c7276582f324ac25b9d1000f1b5ef14/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r1/INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json); [GitHub CI 37879674645](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37879674645) SUCCESS, full manual suite skipped. B reports focused independent suites 26/26 on Python 3.12 and 3.13; A isolated secondary suite 35/35. Test-green did not mean engine behavior PASS.
- Original B audit authorization `3fb4508110c031eb0ff9226a7e42d918684c554f`; corrected prompt identity Controller commit `ffd10e0693dea106c744dc4b9aa904c4526863f6`. This B deliverable is eligible as blocking evidence; its original evidence still cites original dispatch SHA, and the corrective binding is separately published.
- Frozen eight-candidate registry `e5b2006a89441f7eb2ec900e508aff451106b87a`; accepted R3 method `cf2d5cc33774cdcff7d709636305bba830e977ef`.

## L2 finding disposition

**Accepted repaired subset (scoped synthetic):** A01 import/scope, A02 BTC manifest correction, A04 candidate isolation. Do not reopen or erase historical receipts.

**Seven observed blocking interactions warrant a single engineering pass:**
1. B01 **CRITICAL**: `ReplayEngine.marks_by_minute` emits current bar with `timestamp_ms=O`, but Stage1 requires completed/available mark close `O+60s <= O`. A as-of queue keyed by completed-close and availability must be causally corrected; prove future/unavailable marks are excluded and stale marks halt.
2. B02 **HIGH**: entry/exit/funding ACK duplicate messages can settle cash/fee twice; stable idempotence per distinct receipt (preserving legitimate separate fees/events).
3. B03 **HIGH**: settlement boundary `[S-15s,S+15s]` can be omitted at `S-60s`/same-minute exits. Preserve frozen ownership rule without post-outcome redefinition, use explicit bounded causal event semantics and once-only settlement IDs.
4. B04 **HIGH**: intraminute OHLC-proxy SL/TP recorded at bar open gives zero holding and 60s early cooldown. Under interval ambiguity use a deterministic conservative economic exit bound, not invented high-frequency fill times; align `decision_time_ms`, `available_at_ms`, ACK and cooldown.
5. B05 **HIGH**: risk valuation of unacknowledged positions conflicts with frozen decision-equity semantics; kill latch clears live commitments before eventual exit ACK, leading to negative reserves. Separate economic/decision books and exactly-once commitment release; no equity gain from missing ACK.
6. B06 **MEDIUM but mandatory before acceptance**: every elapsed post-breakout hour must advance the three-bar retest window and stop extrema even when its contemporaneous vol/EMA filter fails. Such hours are NOT eligible confirmations; never resurrect canceled/expired state.
7. B07 **CRITICAL**: cumulative funding charge consumes position funding reserve but not book aggregate, leaving positive leaked reserve on flat book. Enforce `book aggregate == sum(active+pending per-event reserves)` through settlement, close, ACK, timeout, kill, duplicate and restart.

Evidence source aligns with core implementation: `replay_engine.py` `marks_by_minute`, `ledger.py` Stage1/2/6/7, `signals.py` retest filtering. For a contested clock/settlement edge, produce source/contract discrepancy and fail closed rather than redefine R3 frozen parameters to make tests green.

## Bounded execution authorization — no recursive audit loop

**TASK_ID:** `V06_G2_R3_P0_A_INTERACTION_REPAIR_R2`.

**Binding:** `CONTROLLER_DISPATCH_SHA` is the immutable Git commit that publishes THIS document, and must be verified before execution. A separate implementation Prompt will be published at its own immutable `v0.6-docs` commit referencing that genuine Controller dispatch SHA. Both pinned documents MUST exist before work starts. No fake SHA / floating prompt reference.

**Executor:** Gemini A, **reuse existing** `~/workspace/project/quant-v0.6/g2-overnight-discovery-a` on `feature/v06-bline-g2-overnight-discovery-a`, exact start `5c542edd418a74b440162610fd540b1f01e423d3`. Do not reset, clean, stash, force-push, create competing A branch, or edit other worktrees. Halt on unowned dirty changes or branch drift. Keep operations inside that owned task worktree.

**Allowed writes:** `src/btc_quant_agent/strategy_research/r3_overnight/**`, `tests/test_strategy_research_r3*.py`, `docs/strategy_research/g2_r3/prep_a/repair_r2/**`, `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r2/**`. This is a **bounded new synthetic engineering task**; do not alter other source, CI selection, root configs, B or Sol branches/evidence, candidate registry IDs, frozen strategy rules, market data or history.

**One coherent repair pass** across B01–B07; allow at most **one** same-scope local correction after focused validation in this dispatch. No repeating 7 separate new prompts. At terminal, one independent B changed-behavior adjudication and Controller L2 decision. If material defects persist, stop the R2 repair chain and return `REPLAN_ENGINE_ARCHITECTURE` for a bounded higher-effort redesign rather than iterate R3/R4 endlessly.

**Mandatory evidence:** original B reproduction behavior observed failing on A R1, then post-repair positive invariants (a passing B regression asserting a bug still exists is NOT a proof of correction); synthetic end-to-end ReplayEngine from eligible marks/price generates stable nonzero admissible mark availability and at least one deterministic candidate fill in a controlled signal fixture; stale/future embargo, ACK duplication/reorder, same-minute SL/TP and settlement ±15s, 4h/12h expiry, retest window progression, kill/no-negative reserves, cash/funding/fee exact-once accounting, candidate permutation/metamorphic baseline+stress. Emit per-defect old/new traces, event clock ledger, 8-candidate counters, source SHA, tests, and one terminal verdict. If no isolated synthetic end-to-end execution possible, `INCOMPLETE_DYNAMIC_CROSSCHECK` (not PASS).

**Verification economy:** developer L0/L1 focused tests and relevant Ruff/compile; one terminal CI L2 plus one independent B behavioral audit. No full repository pytest on every edit. Report inherited H40 debt; do not modify golden. Auto-commit/push only to original A branch (non-force); verify remote SHA, parent ancestry, allowed changed files, test receipts, CI. `BLOCKED_NOT_PUSHED` unless confirmed.

## Other gates unaffected

P2 remains `LOCAL_ROOT_UNKNOWN` with a single owner-supplied canonical root decision, or terminate local search and separately authorize a fixed fallback. No empirical market-body read, download, global data scan or protected holdout read is authorized by this review or A repair. No P3 prereg, P4 replay, G4 TESTNET or real-money writes.

**Authorizations:** `EMPIRICAL_PRICE_BODY_AUTHORITY=NONE`; `G4_TESTNET=NOT_AUTHORIZED`; `REAL_FUNDS_WRITE_AUTHORITY=NONE`; `LIVE_APPROVAL_ONLY=NOT_AUTHORIZED`; `AUTONOMOUS_LIVE=FORBIDDEN`.
