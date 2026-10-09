# G2 R3 P1 Gemini A — Architecture V1 final CI/type and evidence-truth closure (one same-task maintenance pass)

**TASK_ID:** `V06_G2_R3_P1_ENGINE_ARCHITECTURE_REBUILD_V1` (same task, no new engineering architecture grant).
**NEW CONTROLLER_DISPATCH_SHA:** `dca82909aeaef380a5c2e9866238ccbbe0114fad`, verified [L2 adjudication](https://github.com/EXASHXE/btc-quant-agent-public/blob/dca82909aeaef380a5c2e9866238ccbbe0114fad/reviews/v0.6/b_line/V06_G2_R3_P1_ARCH_V1_AND_SOL_SCIENCE_CONTROLLER_L2_ADJUDICATION_R1.md).
**Existing worktree:** `/root/workspace/project/quant-v0.6/g2-overnight-discovery-a`.
**Existing branch:** `feature/v06-bline-g2-overnight-discovery-a`.
**Exact required START HEAD:** `398e6bab0cdedf07a93827019ca4bf1bf913c7f9` (parent implementation `89d0c211cff96286203e4fb7459a51042c1257f1`, prior original A R2 `2c60b0653d3619eedf457753511a9ecc84c1cd5b`).
**Original ARCH controller authority:** `e5fcd76370a1b03d7d83b825af6a8cac842b1ae5`; **original detailed implementation prompt:** `35575f11772dba871b079b0b7f6a8c7ac32e2f30`.
**Frozen eight design:** `e5b2006a89441f7eb2ec900e508aff451106b87a`, current real source registry `src/btc_quant_agent/strategy_research/r3_overnight/candidate_registry.py`.
**Independent B original blocked evidence:** `068a4005f68b5ee4a970063cb1f3bc524a08784a`.

## No new scope, no optional extra audit cycle

This is ONE FINITE same-architecture maintenance correction **before** a single final independent B behavior audit. Source, independent B and Sol review stay immutable; old Holdout and all empirical prices/funding bodies forbidden. No new strategy, data-source, pseudo-positive evidence or substantive redesign. DO NOT start R4/R5 repair series.

**Preflight:** verify clean original task-owned local branch/worktree, exact A remote HEAD `398e6bab...`, repo remote identity, actual Controller dispatch SHA and pinned prompt. Refuse drift/dirty state as `BLOCKED_SCOPE_OR_GIT`; no resets, stashes, cleans, force push, other worktrees.

**Allowed modified paths only:**
- `src/btc_quant_agent/strategy_research/r3_overnight/ledger.py` — mechanical type fix **ONLY**, no behavioral change.
- `tests/test_strategy_research_r3_architecture_invariants.py` — positive production-path synthetic executable evidence strengthening.
- `evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/ARCHITECTURE_SYNTHETIC_EXECUTION_RECEIPT.json` — replace incorrect facts with actual measured results and correct eight IDs, retain original artifact history in Git.
- `evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/B01_B07_ARCHITECTURE_BEFORE_AFTER_MATRIX.json` — update only actually reverified case/run references and statuses; NEVER retroactively label missing executions PASS.
- `docs/strategy_research/g2_r3/prep_a/architecture_v1/ENGINE_EVENT_LEDGER_DESIGN_AND_HANDOFF.md` — concise appendix logging corrected evidence semantics, *not* new engineering design or altered method.

**Everything else forbidden** incl candidate registry/formulas, H40 golden, CI selectors, original B tests or evidence, P2, A-line, protected data and accounts.

## Required Step 1 — Fix new CI type failure correctly

At [A exact-head CI 37910374856](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37910374856), `mypy` found exactly one **new** error:
`src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:904: Incompatible types in assignment (expression has type "None", variable has type "Position") [assignment]`.

At the `Stage7` funding attribution lookup, retain runtime flow but bind `pos: Position | None = None` (or equivalent type-correct annotation without changing branching) and verify mypy over production package. Do NOT suppress with `# type: ignore`, `Any`, mypy settings edits, or broad source churn. Actual commands: `mypy` (same as CI) + Ruff changed paths + Python 3.12 architecture/R3 focused tests. This should not be misclassified as inherited H40: it is a **new A code error**.

## Required Step 2 — Correct provably FALSE candidate identity receipt

The current receipt `candidate_registry_integrity.candidates` wrongly lists eight `c01_donchian...`, `c02_bollinger...`, ... `c08_ema_cloud...` names. Those are not this frozen R3 strategy campaign. The ACTUAL authoritative `CandidateRegistry().list_candidates()` returns exactly:
- `STRUCTURAL_CONTINUATION_LONG_04H`
- `STRUCTURAL_CONTINUATION_LONG_12H`
- `STRUCTURAL_CONTINUATION_SHORT_04H`
- `STRUCTURAL_CONTINUATION_SHORT_12H`
- `CLOSED_RETEST_LONG_04H`
- `CLOSED_RETEST_LONG_12H`
- `CLOSED_RETEST_SHORT_04H`
- `CLOSED_RETEST_SHORT_12H`

Generate the receipt's `candidates` from actual imported `CandidateRegistry` at the tested source commit, assert exact set/order and 8 members, and record a machine `registry_source_path`, frozen design SHA and candidate IDs/receipt timestamp. Do not edit registry to match false names. Correct or qualify any other machine claim inconsistent with actual executed source/test.

## Required Step 3 — Nonempty synthetic trading E2E, not an invented accounting pass

Current `flat_book_algebraic_reconciliation` in `ARCHITECTURE_SYNTHETIC_EXECUTION_RECEIPT.json` is 10000→10000 with `net_closed_trades_pnl_usdt=0`, fees=0, funding=0, no trade. This proves only an EMPTY book.

Keep that zero/no-fill test as separate honest case. Add a **second executable synthetic** test that actually invokes the real `ReplayEngine.run_simulation` code path with valid completed synthetic minute bars (and required Mark availability/indicator warmup), then passes a signal, pending order, actual economic fill, late ACK, position holding interval with funding (if eligible by exact S), exit via true production stop/target/time logic, exit ACK and terminal settlement. Capture actual trade_id, position_id, quantity, entry/exit timestamps, realistic original BASE/STRESS fee and expected funding, `cash_final - cash_initial == Σ finalized trade net`, terminal zero owner reserves/pending obligations, and exact freeze eight IDs. Cover at least one LONG or SHORT eligible 4h case; do not alter indicator/fee/ATR/SL/TP/candidate conditions or reinterpret 12h stress ineligibility to manufacture a pass.

If a full real-signal E2E cannot be triggered with lawful synthetic warmup in this ONE bounded maintenance pass, **do not fake it**. You may additionally demonstrate a partial real `VirtualBook.step_minute_open` synthetic lifecycle (with real order/ACK, actual trade and funding) but label that `BOOK_LEVEL_E2E_ONLY`; mark `REPLAY_SIGNAL_LEVEL_E2E_INCOMPLETE` and return `ARCH_V1_EVIDENCE_INCOMPLETE_FOR_INDEPENDENT_REVIEW`, not READY. Never assert old buggy results as expected positive success.

Also validate algebra on MULTI-POSITION owner reserve and cross-asset pending liabilities: `R_f == Σ per-owner outstanding reserve`, not just `R_f >= 0`. Complete original B01/03/05/06/07 adversarial rerun and B02/04 guards against real source. Mark any missing test `INCOMPLETE`; cannot claim all seven PASS solely from 11 positive tests and empty book. No market data bodies, no real OI/Funding.

## Required Step 4 — Machine artifacts must be factual

Receipt must independently list:
- `controller_dispatch_sha=dca82909...`, `original_arch_controller_sha=e5fcd763...`, immutable prompt link/SHA, actual A start and implementation commit, the real 8 strategy IDs.
- Exact pytest nodes/commands, 3.12 and 3.13 results IF RUN, Ruff, mypy, realistic CI state. Do not claim `mypy PASS` until actually run; `REMOTE_CI` is PASS/FAIL/PENDING matching GitHub.
- Two separately named fixtures: `empty_book_case` and `nonempty_executed_book_case`; all amounts/IDs/timestamps derived from observed code, no invented placeholders. Note if synthetic Funding ACK remains pending: terminal flat cash equality only after ACK.
- An honest B01–B07 positive counterexample matrix, source lines and statuses; no claim that 57 tests prove 57 separate adversarial cases.
- Scoped protected price body reads=0, protected A-line/holdout reads=0, real exchange calls=0, no direct user capital writes.
- `artifact_self_sha` must not equal its unknown same-commit SHA; use tested source/previous implementation SHA then actual remote SHAs in terminal receipt.

**Do not touch H40 golden or legacy six Ruff evidence findings.** CI may later fail on inherited H40 after mypy pass; report this honestly, with exact pytest numbers if CI finishes. No unnecessary repeated full suite.

## Required terminal and auto-delivery

After focused tests and receipt validation, use exactly original A branch; `git diff --check`, check names allowlist, commit **one coherent scoped correction**, push non-force, independently `git ls-remote` match HEAD, parent and paths. Never claim READY before real remote push.

Return:
`TASK_ID`, `CONTROLLER_DISPATCH_SHA`, `PROMPT_SHA`, `START_SHA`, `FINAL_PUSHED_SHA`, `PARENT_SHA`, `REMOTE_PUSH_VERIFIED`, `mypy`, `focused_pytest`, `CI`, `registry_IDs_valid`, `replay_signal_level_E2E_trade_count`, `book_level_E2E_trade_count`, `fees_paid`, `funding_paid`, `reserve_conservation`, `B01_B07`, `terminal_verdict`.

Terminal verdict allowed:
- `ARCH_V1_SYNTHETIC_READY_FOR_FINAL_INDEPENDENT_B_AUDIT` if mypy/positive evidence good (independent B still required);
- `ARCH_V1_EVIDENCE_INCOMPLETE_FOR_INDEPENDENT_REVIEW` if no convincing nonempty ReplayEngine source-path evidence;
- `ARCH_V1_IMPLEMENTATION_FAILED_REPLAN_ALTERNATIVE_ENGINE` if the frozen source cannot preserve invariants with bounded work;
- `BLOCKED_SCOPE_OR_GIT` or `BLOCKED_NOT_PUSHED` as needed.

**Bound:** one same-task CI/evidence correction, then one independent B review; material B failure ends P1 route, no recursive micro-patches.
