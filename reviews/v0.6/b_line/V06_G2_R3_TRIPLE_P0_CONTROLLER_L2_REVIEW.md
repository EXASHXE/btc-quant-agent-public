# v0.6 G2 R3 — Three Parallel P0 Deliverables Controller L2 Review

**L2 decision: `P0_A_REJECTED_PENDING_BOUNDED_REPAIR__P0_B_ACCEPT_FINDINGS__SOL_DRAFT_ACCEPTED_PROTECTION_BLOCKED__NO_EMPIRICAL_AUTHORITY`.**

## Immutable identity
- Code baseline `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`, method addendum `cf2d5cc33774cdcff7d709636305bba830e977ef`, P0 executor dispatch `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`.
- Gemini A `3b8befb0112cfe2d314ad65964762a3fb251e710` (implementation commit `3ebb7db9a1043e58843b518af9381218d9f25af1`): 2 commits, 22 changed paths including **one path outside allowed scope** `src/btc_quant_agent/strategy_research/__init__.py`; code implementation and hermetic fixture tests are real, not just prose. A local receipt says Python3.12/3.13 **28 tests PASS**. [Remote full-suite CI 37821635147](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37821635147) ran **2813 passed, 2 skipped, 9 warnings**, but its green means extant tests pass, NOT behavioral correctness.
- Gemini B `a0aacd105ac3f3173b15d91c869990748178e222`: 1 commit, 18 changed paths inside role B whitelist; independent oracle + manifest and static A comparator. Local Python3.12/3.13 **20 focused tests PASS**. [Remote full-suite CI 37824913667](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37824913667) **2805 passed, 2 skipped, 9 warnings**. B terminal **`P0_B_DISCREPANCY_BLOCKED`**, not independent behavioral PASS.
- Sol High `fc89f05014b61c51a55141cb419948f4eee9d8f3`: two commits, six authorized design/evidence paths; no code/market-body read/empirical backtest. [CI 37822422457](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37822422457) doc-only **mode none**, zero tests, success. Terminal **`G2_R3_PROTECTION_CONFLICT_REQUIRES_CONTROLLER`**; effective prereg **NO**. Local physical Parquet bytes/hash NOT VERIFIED. Sol original candidate registry unchanged.

## Cross-agent findings, provenance and acceptance

Independent B [static comparison receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/a0aacd105ac3f3173b15d91c869990748178e222/evidence/v0.6/b_line/g2_overnight_p0_b/A_IMPL_STATIC_COMPARISON_RECEIPT.json) identifies **8 mismatches**, including execution-science critical defects. Controller independently opened immutable GitHub source lines from A HEAD and confirmed the key mechanical contradictions:

| ID | What broke / severity | Controller action |
|---|---|---|
| A01 | Out-of-whitelist root `strategy_research/__init__.py` added; scope BLOCKER | Explicitly authorize **delete only**, inspect namespace import compatibility |
| A02 | BTC legacy manifest receipt says 2,933,280 instead of true manifest 2,934,720; exactly **1,440 missing minutes** in reported count; evidence BLOCKER | Correct metadata receipt in new immutable repair ledger; do not alter source manifest or market data |
| A03 | `ledger.py::_stage_1_available_messages` unconditionally creates new `Position(max_hold_ms=0)` from entry acknowledgment while Stage5 had already installed real 4h/12h position; early EXPIRY and zombie resurrection after immediate stop/TP; CRITICAL | Make ACK idempotent/typed; preserve economic position or settled closed state, no duplicate fee/position, assert exact 4h/12h hold and same-minute stop scenario |
| A04 | One `SignalGenerator` shared by candidate books; `_active_breakouts` keyed `(symbol,direction)` rather than candidate ID, 4h vs12h retest interference; CRITICAL | Separate candidate states, stable event identity/dedup, metamorphic test order reversal and 4h/12h isolation |
| A05 | Retest zone checks 1h bar range overlap, not required low/high **inside** exact band; breakout bar high/low omitted from initial stop extrema | Validate specified inclusive band and breakout-through-confirmation extrema for both sides |
| A06 | Mark update in Stage2 instead of required Stage1, freshness age from candle open rather than completed mark close | Freeze mark available_at, close timestamp vs open, no future mark leak; test boundary |
| A07 | Cooldown starts at exit ACK not economic exit; omitted last_exit and last_entry_4h dedup arguments to signal generator | Set explicit economic-exit ceil and availability lock, test cooldown, 4h dedup |
| A08 | Active exit cost reserve omits tick_size*quantity and does not retain appropriate funding/exit commitments | Reconcile reserved amount before/after pending ACK, test sharp loss and low equity |

**CI caveat:** running 2813/2805 existing tests on role branches did NOT exercise B's cross-branch static contradiction suite against A as a release gate. The B audit is the disambiguating result. An A patch without new adversarial regression tests and independent B re-audit cannot override this block. No full-suite tests should be repeated after every tiny edit; once per terminal implementation/review SHA is adequate.

## Why Gemini finished fast

Task scope was **offline synthetic engineering, not long-running historical strategy discovery**, and the 8-hour configuration was a **maximum**. A and B used short targeted local suites (28/20 focused tests); remote full-suite GitHub CI separately consumed ~14/15 minutes. Runtime alone proves neither task completeness nor research quality. A implemented substantive code but released too early with untested cross-candidate and acknowledgment interactions; B appropriately identified and blocked it. Sol delivered a DRAFT and correctly refused to convert an old v0.3 final holdout `[2026-02-01,2026-08-01)` into new R3 Feb-Apr development.

## Scientific/operational next steps

1. **Repair A R1 only**, same A branch/worktree with exact remote preflight, within existing research sidecar/test paths plus delete-only out-of-scope file. Do not use real data; author must explicitly test each B defect with red/green synthetic cases and preserve 8 fixed variants.
2. After A pushes exact repair SHA, independent B on its own branch must re-audit the **immutable repaired A SHA**, run synthetic oracle cross-comparisons, attempt negative cases and issue typed PASS/FAIL/INCOMPLETE; B must not change A. New exact repair SHA is mandatory, no unbound moving HEAD.
3. Controller L2 adjudicates both before any R3 original-price access, adopts Sol proposed Option A protected-safe 2021/2023/2025 development only if data source/comparability/licence/old research exposure are prospectively pinned. ETH/SOL multi-year availability remains unknown; old 2026 Feb-Jul BTC final holdout remains PROTECTED/DISPUTED. Prior v0.3 original dataset manifest is metadata only; local Parquet bytes NOT VERIFIED.
4. Separately register source/cost grade (proxy-only, fee/funding/tick/mark) and first-push exact prereg BEFORE actual market body rows. One finite development experiment, all variants and controls, no 360-day forward/no unknown price scanner, not alpha PASS.

`TESTNET=NOT_AUTHORIZED`; `REAL_FUNDS_WRITE_AUTHORITY=NONE`; `G1/G3/A-line` unchanged.