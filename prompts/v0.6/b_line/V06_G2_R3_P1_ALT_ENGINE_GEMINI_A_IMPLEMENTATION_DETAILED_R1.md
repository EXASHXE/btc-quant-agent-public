# Gemini A — v0.6 G2 R3 P1 CLEAN alternative event-journal engine implementation (ONE coherent build)

**Role:** implementation worker. This is a **NEW PACKAGE**, not R4/R5 mutation of failed old VirtualBook. All actions are synthetic-only and bounded.
**TASK_ID:** `V06_G2_R3_P1_ALT_ENGINE_GEMINI_A_IMPLEMENTATION_R1`.
**CONTROLLER_DISPATCH_SHA:** `70236530a0bc1927772493c80ea1f00495088034` — independently verify [real Controller implementation authorization](https://github.com/EXASHXE/btc-quant-agent-public/blob/70236530a0bc1927772493c80ea1f00495088034/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_IMPLEMENTATION_CONTROLLER_DISPATCH_R1.md).
**Controller AM01/AM02 SPEC FREEZE SHA (method R1.2):** `821d23427a5f6d0b4635f32f226ddc779358ab72` [read completely first](https://github.com/EXASHXE/btc-quant-agent-public/blob/821d23427a5f6d0b4635f32f226ddc779358ab72/reviews/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_AM01_AM02_CONTROLLER_SPEC_FREEZE_R1.md).
**Sol exact architecture SHA:** `c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01` [full design](https://github.com/EXASHXE/btc-quant-agent-public/blob/c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01/docs/strategy_research/g2_r3/p1_alt_engine_sol_r1/ENGINE_OPTION_DECISION_AND_EVENT_LEDGER_DESIGN.md), [machine 17 invariants, T01–T34 exact inputs and outputs, interfaces and allowlist](https://github.com/EXASHXE/btc-quant-agent-public/blob/c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01/evidence/v0.6/b_line/g2_r3_p1_alt_engine_sol_r1/ENGINE_OPTIONS_AND_INVARIANT_ORACLE_MATRIX.json).
**Original 8 IDs/formulas:** `e5b2006a89441f7eb2ec900e508aff451106b87a`; accepted limited PIT/cost R1.1 `cf2d5cc33774cdcff7d709636305bba830e977ef`, **new prospective R1.2 has precedence for the two explicitly documented changes**.
**Failed original A implementation evidence SHA:** `b5d34aacd36dc27454944a22436db555c3f6eeb8` (read-only pure values only; no mutable lifecycle). **Independent B failure:** `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7`.
**REPOSITORY:** `EXASHXE/btc-quant-agent-public`.
**IMPLEMENTATION BRANCH:** `feature/v06-bline-g2-r3-p1-alt-engine-gemini-a-r1`.
**Exact START/parent CODE BASE (NOT Controller dispatch SHA):** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`, current original `v0.6`. Branch already exists remotely at this SHA.
**New worktree proposal:** `/root/workspace/project/quant-v0.6/g2-p1-alt-engine-gemini-a-r1`; create only after confirming clean/unoccupied.
**TASK END:** non-force commit/push + remote exact SHA verification, no automatic science or engine approval.

## 0. Preflight: verify identities, protect A/B and market data

Execute in order:
1. `git ls-remote` for repo and new implementation branch; assert it equals exact `e0ff8c...`. Compare GitHub's immutable original Sol design and Controller R1.2/dispatch SHA to supplied links. Read this exact pinned Prompt from the immutable SHA supplied in handoff, *not* a floating branch. Test `git status --porcelain`; do not reset/stash/clean forcefully if dirty/owned by another task. If any binding fails: `BLOCKED_IDENTITY_OR_SCOPE`.
2. Use **separate new sibling worktree** for implementation branch, never `g2-overnight-discovery-a`, `g2-overnight-verifier-b`, `Quant-agent-sanitized`, P2, Sol alternative-design worktree. Branch from CODE baseline, not from docs commit; record Controller dispatch SHA separately in metadata.
3. No market/Mark/Funding/OI/orderbook/aggTrade CSV, Parquet, ZIP, downloaded historical body, remote exchange endpoint, A-line sealed result, old BTC final holdout, credentials, live/testnet, trading calls, price updates or actual backtests. ALL testing uses explicitly generated **in-memory** synthetic minute bars + proxy rates. No source-body discovery; no P2/admission modifications.
4. Allowed new/modified files ONLY:
   `src/btc_quant_agent/strategy_research/r3_alt_engine/**`;
   `tests/test_r3_alt_events_money.py`;
   `tests/test_r3_alt_clock_execution.py`;
   `tests/test_r3_alt_retest_replay.py`;
   `scripts/strategy_research/r3_alt_engine/run_synthetic.py`;
   `docs/strategy_research/g2_r3/p1_alt_engine_impl_r1/**`;
   `evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/**`.
   **Forbidden:** any existing production files outside new package, original A/B test or evidence changes, H40 golden/workflows, root CI, prior Sol design, original R3 method, candidate IDs, P2, A-line. No new dependencies or framework installation without new Controller grant.
5. Read 34 exact oracle cases and 17 invariant text from pinned Sol matrix **BEFORE coding**; establish a coverage ledger keyed T01–T34 with initial status NOT_RUN and expected independent values. Implement under R1.2 semantics when older Sol T26 pre-freeze branches conflict (current frozen AM01: no same-hour new seed). If any case contradiction to stronger accepted immutable authority arises, record `ALT_ENGINE_CONTRACT_CONFLICT_STOP` instead of inventing resolution.

## 1. Write a minimal typed architecture before logic

New Python package modules: `__init__.py`, `model.py`, `journal.py`, `money.py`, `reducer.py`, `clock.py`, `execution.py`, `signals.py`, `frozen_primitives.py`, `replay.py`. Keep per-module responsibilities from Sol matrix:
- **model:** immutable Event/Posting/OwnerLedger/RetestState/Projection/EngineState/ReplayConfig/ReplayReport; validate exact decimals, IDs and event clock.
- **journal:** stable `event_id` namespaces, canonical payload digest excluding only event ID itself for reuse conflict, cause graph, source/symbol/close Mark collision, deterministic append hash and balanced double-entry postings. Exact duplicate accepted once; payload conflict raises before any mutation; journal event order deterministic.
- **money:** owner-scoped ledgers by (`book_id`, `position_id`, `settlement_id`), cash/receivables/payables/fee/funding expense and memo encumbrances. Aggregate sums DERIVED from owners, never separately mutable scalar authorities; implement `assert_invariants` after each reduction.
- **reducer:** `reduce(old_immutable_state,event,config) -> (new_state, journal_postings, scheduled_events)`; atomically apply or fail unchanged, no hidden global singletons. Reports do not schedule new decisions.
- **clock:** separate economic/knowledge/ack events; `advance_to(aligned_open_ms)`, eligible queue sorted by available/cause/typed tie; reject S−5000ms advance. Never consume future bar close/mark. Preserve ordered book isolation and input order invariance.
- **execution:** pure B04 standing exit/SL-first/gap/capped favorable forced/time/kill/reduction, 4h/12h exact hold and cooldown max, timestamp ending at O+59999 for intrabar barrier, entry spread+slippage/fee once.
- **signals:** pure exact frozen 8 formula predicates and chronological per family/symbol/direction retest cursor across all completed bars. AM01 no new breakout in same bar as terminal cancellation/confirmation/expiry, first valid confirmation consumed once per variant even WAIT.
- **frozen_primitives:** copy or rewrite *pure*, separately version-hashed R3 Bar/Mark, aggregation, EMA/ATR/ER, cost/rounding and original `CandidateRegistry` IDs from pinned A reference; NOT `VirtualBook`, old `ledger.py`, mutable `signals.py` state or old `ReplayEngine` framework wrapper. Bind exactly 8 variants and BASE/STRESS separate books.
- **replay:** true minimal `ReplayEngine.run_simulation(SyntheticDataset, ReplayConfig)->ReplayReport` using in-memory 1m/mark bars, no loaders/connectors. Report source/clocks, event sequence hash, 8-policy × cost scenario outcomes, book-level cash/trades/WAIT/ineligible/end liabilities.

Types can be locally smaller if exact 8 records or immutable equivalents and event invariants remain auditable. Do not grow a general automated trading runtime.

## 2. Freeze precise clocks and state semantics in implementation

For minute open O, the `[O,O+60000)` complete 1m OHLC/Mark only enters decision/risk at `O+120000` (completed close plus frozen reconstructed 60s lag). Hour signal close H available H+60000, first fill H+120000; no feature from fill minute. A synthetic economic fill at open F may have modeled ACK delay F+60000 but **actual decision visibility waits until max(F+60000, admissible fill-source proof, extra delay)**; failed old architecture prematurely treated live/unacknowledged state as paid and then lost the pending liability.
Funding ownership `[S−15000,S+15000]` has conditional reserve at S; final owner's amount cannot depend on the unseen future +15s portion before the **full intersecting minute's source proof** (normally S+120000). `FundingAck` after full proof and rate proof/declaration; the owner stays tracked through EXIT ACK and Funding ACK. Use only adverse deterministic 4/8bp proxy in synthetic.
At each aligned open, event ID/payload validation → available ack and source batch → risk-visible pending losses + funding encumbrance → 1h cursor and valid scheduling → due exits → due entries → intraminute protection on *economic plane* → funding windows → ex-post report. Economic simulation may reference completed bar data to adjudicate a past interval, but **may not allow that information to influence previous as-of decisions**. Annotate economic-vs-visible labels in receipt. Every state transition must leave account identities and risk projections consistent.
For RETEST, complete every skipped hour chronologically, freeze boundary/ATR at prior signal breakout, only next 3 completed hours confirm; cancel on wrong close, first confirmation exactly once. No same-hour terminal old breakout/new seed; next distinct hour can seed if truly qualifying, no retroactive trades.

## 3. Implement double-entry money and the conservative risk projection

In the 1000 USDT isolated candidate/cost book, postings per owner use at least `CASH`, `TRADE_RECEIVABLE`, `TRADE_PAYABLE`, `FEE_PAYABLE`, `FUNDING_PAYABLE`, `REALIZED_GAIN`, `REALIZED_LOSS`, `FEE_EXPENSE`, `FUNDING_EXPENSE`, `OPENING_EQUITY` plus balanced memo cost/funding/shortfall encumbrances. No trade notional debit from cash for 1x perpetual; quantity × effective fill prices governs gross and unrealized PnL; fee/slip/tick applied exactly once.

- `E_c = CASH + acknowledged_live_MTM + sum(min(0, unacked_live_MTM)) − visible_unpaid_exit_losses − visible_unpaid_fee_payables`, all slices disjoint. If a slice exits economically, remove its prior unrealized component from the risk plane before counting the visible realized pending loss. Positive pending gains do not offset any negative pending exit slice, and do not increase `E_c`.
- `P_f = sum(final_unpaid_owner_funding_payables)`, `E_r=E_c−P_f` for risk kill (100 USDT peak-to-trough or E_r<=0). Kill latch cannot reset after ACK or fold. Economic gap insolvency may occur before causal detection; do not backdate kill.
- `C_o` includes owner remaining cost/notional commitments. `R_f` includes future/conditional owner cover and final payable's dedicated cover; `L_f` is its unreserved difference, indexed by owner/S. `A=max(0,.95*E_c−C_o−R_f−L_f)`, or 0 on kill/insolvency. The payable `P_f` is **not subtracted a SECOND time from A** where `R_f+L_f` already represents that exposure. Matching fee cover is atomically converted when its fee becomes a visible payable (do not double deduct), and unsettled cash/fee settlement later converts liability to cash once.
- **BTC Funding test:** cash1000, C_o7, ETH Rfuture2, BTC Rcover.40, BTC P1 and L.60: `R_f=2.40`, `A=940`; after Funding ACK cash999, BTC cover/payable/shortfall0, ETH reserve2, `A=940.05`. No transfer from ETH, no 941 preACK phantom capital.
- **Pending-loss test:** standardized economic exit gross/net liability169.336545 before ACK, at first **lawful proof** cut `E_c=E_r=830.663455`, killed=true, A=0; before proof no future loss. Exact use of normalized journal fixture, don't invent A's historical per-fill costs.
- **Fee cover conversion:** cash1000, entry notional cover100, fee cover2, exit cover1, `C_o=103`; fee notice2 gives E_c998, C_o101, A847.1; then ACK cash998, outstanding payable0, C_o1, G100, A947.1. No negative clipping of cash/losses, only available A max0.
- **Owner phase/tombstone:** RESERVED→UNACKED_OPEN→ACKED_OPEN→EXIT_PENDING→CLOSED_UNSETTLED→COOLDOWN→FLAT; physical inventory can disappear but financial owner and its pending liabilities cannot until all final ACK and cover release. Late prior owner ACK cannot affect new owner's cooldown or spendability.
- `Decimal` local context prec50 HALF_EVEN, USDT journal postings quantize12dp, no binary float intermediary; preserve source decimal strings, timestamp int. Every actual posting balanced, every memo posting balanced, no collision by partial string `POS_1 in POS_10`.

## 4. Independent-acceptance-oriented test construction, exact T01–T34

Use the **published Sol JSON matrix as canonical literal oracle inputs/expected outputs**. All T01–T34 must be actual executed scenario functions, each asserting independently expected behavior, not 34 report labels. To reduce Gemini implementation mistakes, use these groups as a compulsory ordered build/test sequence:

- **T01–T05: Mark/PIT:** same close 50000/52000 reversed ⇒ conflict both; late same-close 48000 ⇒ conflict; delayed close=50000 vs newer51000 ⇒ eligible only by clock, monotonic watermark; future ex-post mark must not affect E_c/order; Mark close age120s valid, age180s stale/veto.
- **T06–T09: ACK:** same ID identical payload 2×/3× fees2 debited once cash998; changed payload fee2→3 or quantity1→2 ⇒ fail closed; older P1 exit ACK cannot rewind newer P2 cooldown 1700017140000 to 1700010000000; wrong owner/cause forbids auto-ack/commitment release.
- **T10–T15: Funding and event clocks:** owner BTC payable1/cover.4/L.6 versus ETH reserve2 ⇒ A940 then 940.05 postACK; delayed funding ACK never makes liability vanish; economic exit S−10000, first aligned ExitAck=S+60000, funding final>=S+120000; non-minute `advance_to(S−5000)` invalid without mutation; POS_1 vs POS_10 exact no substring; at S conditional reserve only and final quantity uses max(pre,post) not sum.
- **T16–T19: risk:** visible standardized pending −169.336545 ⇒ E_r830.663455, kill/free0; before proof invisible; pending +50 cannot inflate capital, after ACK cash1050; pending loss20 reduces free from950 to931 even though kill not latched; kill permanent across winning ACK/fold and no new order.
- **T20–T23: B04 and clock:** same SL/TP bar ⇒ stop=49000 first; gap open48000 ⇒ worse fill48000; LONG favorable target open52000 capped51000 and SHORT favorable open48000 capped49000 including TIME/KILL/REDUCTION, friction once; 4h/12h expiry exact first due open; SL at expiry open wins.
- **T24–T27: Retest/candidate economy:** skipped intermediate hour H26 close46000 low45500 cancels prior boundary47400 despite later H27 recovery; 3h low extrema `49700−250=49450` frozen stop; AM01 same-hour cancel/expiry cannot seed new even if rebreakout condition holds; original eight remain untouched, BASE/STRESS22/44bp, under hourly proxy 4h hurdle76bp/d>=152 and 12h STRESS140bp/d>=280>250 ⇒ `STRESS_COST_GEOMETRY_INELIGIBLE` as non-trade diagnostic, not loss.
- **T28–T31: PRODUCTION replay, not unit-only:** actual `ReplayEngine.run_simulation` 240h synthetic warmup then 4h BASE/STRESS both winning AND losing independent paths (>=4 full replays), fees+funding+rounding, terminal owner zeros; separate 12h BASE valid known frozen 8h settlement schedule and 12h STRESS default hourly infeasible retained as 0 fills, no retroactive cheaper schedule switch; partial exit q1→.6→0 keeps max exposure qty1 not1.6; deterministic contexts Python3.12/3.13 and independent input permutations; missing/stale/unlicensed trade/mark/cost/filter/fold tail fail `SOURCE_BLOCKED/COST_BLOCKED/WAIT`, never pull another month or real data.
- **T32–T34: corner capital safety:** same owner negative pending slice100 and positive receivable100 cannot net to zero, E_c900/kill; A_raw=-5 and negative E_c valid free0 but cash/loss not clipped; exact fee notice & reserved fee conversion C_o103→101→1 and A847.1→947.1 without duplicate fee.
- All 17 **I01–I17** invariants recorded per relevant transition, with executed count/status; each case may skip an inapplicable invariant only with structured reason, NOT skip mandatory case execution. A risk-only toy injected book may violate 1x admission intentionally; label as synthetic normalization *not* supported strategy entry (e.g. T04). Positive test count is evidence of developer correctness only, not independent validation.

### Important no-shortcut instructions

Do not simplify T28/T29 by manually appending `CompletedTrade`, reusing old A fixture names as a list, or skipping signal/indicator/clock stages; actual nonempty production `run_simulation` must generate signals, order reserves, fills, ACK, settle Funding, exits and completed trades. Do not weaken 30–250bp stop, 4h/12h horizons, 100USDT kill, cost scenarios, 1.10 cover or GAP. If synthetic fixture triggers kill/WAIT, report the reason and construct **prospectively declared** different synthetic fixture inputs consistent with frozen rules, never fit to historical outcomes. A fixed synthetic known 8h Funding grid in T29 is a **distinct predeclared synthetic test scenario**, not permission to substitute cheaper cadence for historical campaign.

## 5. Runtime QA, evidence artifacts and one-shot STOP

First implement core journal, money and clock + T01–T19. Then B04/Retest and T20–T27. Finally fully integrated replay T28–T34. Run focused pytest after each stage and final `pytest -q tests/test_r3_alt_events_money.py tests/test_r3_alt_clock_execution.py tests/test_r3_alt_retest_replay.py`, `ruff check` on edited paths, `mypy` where production-covered, `compileall`, JSON parse, `git diff --check`. Run Python3.12 and3.13 when both available; if one environment absent, label `UNVERIFIED`, don't invent. Full CI status must be fetched/reported after PUSH, not presumed; known H40 sporadic inherited golden failure MUST NOT be suppressed. Avoid repeated 15-minute global CI runs that don't increase decision information.

Mandatory deliverables (all in allowlisted new locations):
1. New `r3_alt_engine` Python package (9 functional modules + init), real deterministic journal/reducer and ReplayEngine.
2. Three real positive/negative synthetic test modules with 34 named cases (the 34-case count must be derived from actual test IDs or machine case mapping, no aliases pretending distinct tests) and 17 invariant checks.
3. `scripts/strategy_research/r3_alt_engine/run_synthetic.py`: Hermetic input, no data loaders; CLI optional, cannot access network.
4. `docs/strategy_research/g2_r3/p1_alt_engine_impl_r1/ALT_ENGINE_IMPLEMENTATION_AND_HANDOFF.md`: source/candidate/spec SHA, type/event interfaces, money derivation, R1.1→R1.2 diff, test coverage, fail-closed limitations, eventual independent audit needs.
5. `evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/ALT_ENGINE_IMPLEMENTATION_SYNTHETIC_RECEIPT.json`: exact controller dispatch, Sol target, AM01/AM02 freeze SHA, branch/code baseline, actual 34 runtime case statuses/commands, actual tested code source SHA, per-transition I01–I17 counters, true economic/availability proof clocks, T10/T16/T34 money witnesses, nonzero T28/T29 trade IDs/cash/net/fees/funding, zero scope counters, real CI state.
6. `evidence/v0.6/b_line/g2_r3_p1_alt_engine_impl_r1/T01_T34_EXECUTED_TEST_MATRIX.json`: every ID/Txx, test_node, synthetic input provenance, independently calculated expected, observed, PASS/FAIL, invariant applicable/checked, never an unexecuted synthetic claim.

**No repeated repair cycle:** this is one coherent implementation submission. While building, self-correct normal coding bugs; after non-force push and independent audit, any material failure => STOP alternative-engine route, not automatic R2/R3/repatch.

Terminal verdict EXACTLY ONE:
- `ALT_ENGINE_IMPLEMENTED_SYNTHETIC_READY_FOR_INDEPENDENT_AUDIT` (all 34 actual runtime checks demonstrated, reconciled, focused QA; still no science/engine acceptance);
- `ALT_ENGINE_IMPLEMENTATION_INCOMPLETE` (some mandatory cases not proven, report exact missing + stop);
- `ALT_ENGINE_CONTRACT_CONFLICT_STOP` (accepted method contradiction cannot be resolved without Controller);
- `BLOCKED_IDENTITY_OR_SCOPE`; `BLOCKED_NOT_PUSHED`.

**Push on completion without asking:** `git status`, `git diff --check`, exact changed-path allowlist; commit and **non-force push to same dedicated implementation branch**, verify `git ls-remote` remote exact final HEAD, parent==`e0ff8c...` if one commit, actual CI jobs/mode. Report in handoff: `TASK_ID, CONTROLLER_DISPATCH_SHA, PINNED_PROMPT_SHA, CODE_START_SHA, AM01_AM02_FREEZE_SHA, SOL_DESIGN_SHA, FINAL_REMOTE_SHA, PARENT, REMOTE_PUSH_VERIFIED, REAL_TEST_COUNTS, T01_T34, I01_I17, SYNTHETIC_FULL_REPLAY, CI, TERMINAL_VERDICT`. Do not try to write an impossible same-commit own SHA into a precommit receipt; terminal stdout/hand-off contains actual final SHA.

**Unchanged outer fences:** P1 independent acceptance `NONE`; P2 source admitted `NO`; scientific Sol restricted `SCIENCE_READY` for proxy-only finite diagnostic; P3 effective first-pushed prereg `NONE`; P4 historical body `NONE`; TESTNET and real funds write `NONE`.
