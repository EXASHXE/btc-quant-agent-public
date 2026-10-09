# Sol High — v0.6 G2 R3 Scientific Strategy Review R1 (incremental economic mechanism + ex-ante power)

**Executor:** GPT-6 Sol High reasoning (Codex/agent selected externally if available). **No execution model setting is implied by GitHub publication.**
**TASK_ID:** `V06_G2_R3_SCIENTIFIC_STRATEGY_REVIEW_SOL_HIGH_R1`.
**CONTROLLER_DISPATCH_SHA:** `7da2b9e65848c3c547d940ded60a57f71314c64f` — first verify real [Controller dispatch object](https://github.com/EXASHXE/btc-quant-agent-public/blob/7da2b9e65848c3c547d940ded60a57f71314c64f/reviews/v0.6/b_line/V06_G2_R3_SCIENTIFIC_STRATEGY_REVIEW_CONTROLLER_DISPATCH_R1.md).
**REPO:** `EXASHXE/btc-quant-agent-public`.
**NEW ISOLATED BRANCH:** `feature/v06-bline-g2-r3-scientific-strategy-review-sol61-r1`.
**BRANCH START SHA:** `7da2b9e65848c3c547d940ded60a57f71314c64f` (Controller created remote branch at dispatch object; remote must match at first use).
**PREVIOUS DOCS SHA:** `35575f11772dba871b079b0b7f6a8c7ac32e2f30`.
**ORIGINAL EIGHT-CANDIDATE DESIGN SHA:** `e5b2006a89441f7eb2ec900e508aff451106b87a`.
**METHOD PROPOSAL SHA:** `35d2b8488fd6fbdab0d3d7ff8cf2b84ee5b60b6f`.
**METHOD PUBLICATION SHA:** `cf2d5cc33774cdcff7d709636305bba830e977ef`.
**PRIOR SOL SCIENCE GATE SHA:** `fc89f05014b61c51a55141cb419948f4eee9d8f3`.
**P1 A ENGINE IMMUTABLE CURRENT:** `2c60b0653d3619eedf457753511a9ecc84c1cd5b` (for isolation only; do not re-audit).
**B ENGINE R2 INDEPENDENT RESULT SHA:** `068a4005f68b5ee4a970063cb1f3bc524a08784a` (isolation only).
**SCIENCE ACCESS:** outcome-blind, design-only, aggregate previously accepted findings only.
**EXECUTION:** 1 finite pass. No Astra in this task.

## 1. Startup and permission fences

- Independently verify the NEW branch `git ls-remote` SHA equals exact `CONTROLLER_DISPATCH_SHA`. Use an **independent sibling worktree** e.g. `/root/workspace/project/quant-v0.6/g2-r3-science-sol-r1` ONLY if unoccupied; if exists, inspect owner and branch first; never touch `g2-overnight-discovery-a`, `g2-overnight-verifier-b`, `Quant-agent-sanitized` or P2 worktree. If branch/worktree dirty or already advanced by another worker, halt `BLOCKED_SCOPE_OR_GIT`, no force/reset/clean/stash.
- Source truth is the pinned public Git refs listed, not a moving local checkout or LLM summary; verify same prompt and Controller identities. This Prompt resides on a later docs commit than branch start, so fetch/read by **pinned prompt SHA from invoking link** rather than assuming its file exists on the branch at branch creation.
- Before any discovery, classify accessible material as (i) accepted method/authority, (ii) previously published aggregate development result, (iii) proposed draft, or (iv) PROTECTED/UNKNOWN. Do not open source-code or market files outside the explicit read-only scientific paths needed to understand accepted methods.
- Absolutely forbid: new raw price/Mark/funding/orderbook/OI/trade-row bodies; private A-line outcomes and H41 WF1 validation; historic 2026 BTC protected final holdout; any new Binance/bybit/OKX empirical endpoint access; trade calls; R3 backtest or parameter sweep; changes to A/B engine/tests; authoring a first-effective prereg.
- Allowed new writes ONLY:
  `docs/strategy_research/g2_r3/scientific_strategy_review_r1/**`,
  `evidence/v0.6/b_line/g2_r3_scientific_strategy_review_r1/**`,
  `reviews/v0.6/b_line/scientific_strategy_review_r1/**`.
  No CI, code, eight-candidate registry, root docs or other files.

## 2. Mandatory read-first references: reuse, don't duplicate

1. [R2 Controller accepted negative aggregate diagnostic](https://github.com/EXASHXE/btc-quant-agent-public/blob/35575f11772dba871b079b0b7f6a8c7ac32e2f30/reviews/v0.6/b_line/V06_G2_R2_CONTROLLER_L2_DIAGNOSTIC_REVIEW.md): previous 8 alternatives, all base/stress net R negative, 22/44bp proxy transactions, low support, no positive survivor. No R2 subgroup rescue or re-scoring exposed returns.
2. [R3 Controller design L2](https://github.com/EXASHXE/btc-quant-agent-public/blob/35575f11772dba871b079b0b7f6a8c7ac32e2f30/reviews/v0.6/b_line/V06_G2_R3_DESIGN_CONTROLLER_L2_SCIENTIFIC_REVIEW.md); frozen eight exact formulas from `e5b200...` and [accepted method addendum limited L2](https://github.com/EXASHXE/btc-quant-agent-public/blob/35575f11772dba871b079b0b7f6a8c7ac32e2f30/reviews/v0.6/b_line/V06_G2_R3_METHOD_R1_1_CONTROLLER_L2_ACCEPTANCE.md). Separate accepted engineering/method semantics from non-effective design proposals.
3. [Prior Sol science/economics/power analysis](https://github.com/EXASHXE/btc-quant-agent-public/blob/fc89f05014b61c51a55141cb419948f4eee9d8f3/docs/strategy_research/g2_r3/science_gate/SCIENCE_ECONOMICS_AND_POWER_GATES.md), [prior R3 prereg DRAFT](https://github.com/EXASHXE/btc-quant-agent-public/blob/fc89f05014b61c51a55141cb419948f4eee9d8f3/docs/strategy_research/g2_r3/science_gate/R3_EIGHT_CANDIDATE_PREREG_DRAFT.md) and [science gate matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/fc89f05014b61c51a55141cb419948f4eee9d8f3/evidence/v0.6/b_line/g2_r3_science_gate/SCIENCE_GATE_MATRIX.json). These already cover overlap, P2 data root, underpowered variants, bootstrap and source/license. **New report MUST have a paragraph "DELTA_VS_PRIOR_SOL_R1" listing actual novel decisions; do NOT restate its full inventory**.
4. [H41 accepted terminal exploratory NO_GO](https://github.com/EXASHXE/btc-quant-agent-public/blob/35575f11772dba871b079b0b7f6a8c7ac32e2f30/reviews/v0.5/V0.5.1_H41_EXPLORATORY_NO_GO_CONTROLLER_ADJUDICATION_R1.md); [H41 successor Controller design acceptance](https://github.com/EXASHXE/btc-quant-agent-public/blob/35575f11772dba871b079b0b7f6a8c7ac32e2f30/reviews/v0.5/V0.5.1_H41_SUCCESSOR_SCIENTIFIC_CAMPAIGN_V1_DESIGN_R1_CONTROLLER_ACCEPTANCE.md); [H41 Astra public design audit](https://github.com/EXASHXE/btc-quant-agent-public/blob/35575f11772dba871b079b0b7f6a8c7ac32e2f30/reviews/v0.5/astra-h41-successor-design/V0.5.1_H41_SUCCESSOR_SCIENTIFIC_CAMPAIGN_V1_ASTRA_DESIGN_AUDIT_R1.md); [H42 public feasibility remit](https://github.com/EXASHXE/btc-quant-agent-public/blob/35575f11772dba871b079b0b7f6a8c7ac32e2f30/prompts/v0.5/research/v0.5.5_H42_STRATEGY_DISCOVERY_HYBRID_CAPABLE_FEASIBILITY_R1.md). Reuse **accepted** PIT, provenance, joint cluster inference, candidate-budget/exposure and HOLDOUT separation. Do NOT import A-line sealed outcomes, H42 findings not yet accepted, H41 fixed alpha thresholds, or claim its 120h bootstrap plug-and-play covers R3.
5. P1 has its own architecture repair to fix B01/B03/B05/B06/B07; P2 has its own dataset admission. This science task may list scientific *gates* contingent on P1/P2, not redo their line-by-line engineering or file access.

## 3. Required analytical study: economic mechanisms, not parameter optimization

For EACH of the eight original IDs create one row of `MECHANISM_LEDGER` with:
- Exact formula/family/direction/hold as originally frozen; causal signal availability and actual entry delay. Are LONG/SHORT mirror definitions economically symmetric? Discuss funding/crowding/asymmetric liquidation as hypotheses **not observed facts**.
- **Plausible economic source:** who transfers expected PnL to strategy? Momentum persistence from slow portfolio adjustment, continuation after liquidity absorption, retest filtering late-chase adverse selection, post-sweep liquidity recovery, or none. Label mechanism `PHYSICAL_MICROSTRUCTURE_JUSTIFICATION`, `TESTABLE_UNVERIFIED_ASSUMPTION`, or `WEAK_NARRATIVE`, never "known alpha".
- Failure regimes/exclusions definable **before** observing R3 PnL: trend vs chop, volume/volatility conditions, gap risk, funding cost windows, macro-driven volatility, false retest. WAIT/no-trade is a distinct policy choice that may improve expected net but reduces events and statistical power. No subgroup chosen by R2's most negative/least negative row.
- **Dependence:** 4h vs 12h sharing entry trigger, LONG/SHORT being direction mirrors, STRUCTURAL vs RETEST sharing 4h EMA directional filter, same asset common-time return shock, correlated BTC/ETH/SOL. Distinct names/filters do NOT prove eight independent tests; assess effective hypotheses and keep multiplicity protection until prospectively accepted alias reduction.
- For each horizon, list feasibility under frozen 30–250bp stop and stress coverage, without changing risk stop, 4h/12h period or minimum confirmation features.

## 4. Required arithmetic: break-even and genuine economic feasibility

Use symbolic, not historical, price returns. Distinguish:
- Entry notional basis bp versus risk-R and account equity.
- Transaction cost = base `6+2+3 bp per leg` ×2 = 22bp; stress `12+4+6 bp per leg` ×2 = 44bp, *before* uncertain funding/tick effects. Current fees/spread/impact are **scenario proxies**, not verified executed Binance history.
- Adverse funding proxy `4bp/event` base, `8bp/event` stress, **event count and actual settlement schedule unresolved**; unknown hourly stress 12h example `12*8+44=140 bp`. Original geometric hurdle `stop >= 2*stress_total_cost` (140→280bp) conflicts with stop<=250bp; mark `STRESS_COST_GEOMETRY_INELIGIBLE` only, not observed losing 12h and not universal exchange statement.
- For idealized outcomes with stop distance `d bp`, fixed profit target `2d bp`, and total cost `c bp`, break-even win fraction `p_BE=(d+c)/(3d)`. Derive visibly; include illustration `d=100bp`, `c=22bp` → 40.67%, `c=44bp` → 48%, but label as illustrative without gap/timeout/holding-state ambiguity. Actual empirical hurdle is higher/changed when stop slippage, gap, time exit, censoring, funding variation, isolated losses or no-fill occur. Do not substitute hit-rate alone for mean netbp/expected R.
- Distinguish *trade frequency* (events), *eligible fill fraction* (geometry/WAIT/gap), *economic expected net*, *probability of noisy apparent profit*, *effective independent block count*, and cost sensitivity. No optimization, profit projection or current-trading advice.
- Identify the minimum piece of **source evidence** that would allow moving from `PROXY_DIAGNOSTIC_ONLY` to economically credible support, and what can remain proxy with explicit limited claim. Funding schedule, scenario cap, fill/mark PIT, tick/lot, fee tier, spread/impact uncertainty must each receive a status.

## 5. Sample size/power/candidate overlap: ex-ante quantitative design

- Compare original >=100 unique filled trades per candidate **per fold**, >=12 joint occupied weekly clusters and >=4/fold proposed science-draft detail, +5bp economically meaningful after-cost effect, 8×2 FWER correction with 10,000 fixed-seed common-time clusters, within-fold resampling and 14-day sensitivity. Separate accepted versus still DRAFT amendments — **none become authority merely by this report**.
- Use hypothetical per-eligible-day rates `0.5,1,2,4` and one-month 29-day equivalent to show approx 14.5/29/58/116 events per fold. Solve what it would take to attain 100/fold and 30/fold diagnostic floor; label theoretical, no invented R3 counts.
- Illustrate common-time-block power with the existing prospective draft equation `n_week >= ceil(12.7877 * (sigma_block/5)^2)` and hypothetical sigma_block 5/10/20bp → 13/52/205 occupied weekly blocks. This is a toy *block* calculation, NOT actual method power. Three ~monthly folds have ~12–13 weeks total and may not support 5bp detection; multiple assets/strategies are NOT more independent calendar blocks. Include pseudo-power under overlap and sensitivity reasoning, not hallucinated realized volatility or weekly SD.
- Eight strategies with shared assets/entries/horizons: describe an **outcome-blind alias matrix** based only on formula/signal definitions, not measured correlated returns. Critically classify what would justify reducing the formal multiplicity budget *only via NEW preregistration before any R3 bodies*, versus merely reporting correlated tests while retaining 8×2 conservatism.
- Report under what hypothetical event rate + cost confidence the current 3-fold design is worth even finite P4 diagnostic. When low support is likely, choose `INSUFFICIENT_EVIDENCE` rather than pretend negative underpowered == profitable or universally losing.

## 6. Three choices required (no hidden candidate/threshold adjustment)

Compare in one decision table, at minimum:

**A — CURRENT_8_UNCHANGED, bounded first DEVELOPMENT_DIAGNOSTIC.** Preserves 8 IDs/formulas, existing eligible three older BTC windows if P2 admits them, SOURCE/COST grade and risk geometry. Requires Controller selection of one data universe, independent accepted P1 engine, P2 metadata/source/license, accepted statistics/proxy descriptors, NEW exact first-pushed prereg + separate market-body reading capability. Prospectively do a single small fixed-budget replay and fully report WAIT/ineligible variants and 0-survivor. May NOT claim economically validated Alpha from proxy-only costs, or falsify 12h stress geometry.

**B — LIMITED_PROSPECTIVE_DESIGN_CHANGE.** Keep old eight as immutable historical roster; propose at most a small, explicit set of new regime/WAIT, event de-aliasing or economic execution refinements **as a separate new roster/semantic root**, requiring separate design approval, multiplicity / support / cost contract, fresh first-pushed prereg and body admission. NO applying B tweak secretly to current 8 or rescue of an exposed R2 regime slice. Rate extra latency against mechanism strength/power, not automatic “improvement”.

**C — NEW_MECHANISM_FAMILY.** H42-style cross-sectional/multi-asset conditional mechanisms, funding/basis/OI×price only if independent source/PIT coverage can later be verified, potentially venue/asset holdouts. Separate scientific root/strategy IDs, source and holdout authorities, event/economic model and new prereg. Do not consume protected H41/H42 or run probes. Show engineering/source cost and how genuine independent replication differs from BTC/ETH/SOL within one venue.

For each A/B/C: `expected_information_value (qualitative)`, `market_body_permissions_required`, `reused_or_new_authority`, `P3_date/risk (qualitative)`, `hypothesis_diversity`, `statistical_power_caveat`, `real_cost_identifiability`, `fallback_trigger`.

Make **ONE explicit recommendation and one STOP condition**. Default to fast scientific learning, not an endless audit.

## 7. Pre-P3 delta and Astra threshold (Controller reserves decisions)

Provide **P3_MINIMUM_DELTA_MATRIX** with each necessary item:
- already accepted/frozen/not to alter;
- needs Controller P3 freeze before future price access;
- depends on P1 engine acceptance;
- depends on P2 source/permissions/licence; or
- can be stated as prospective `DIAGNOSTIC_ONLY` caveat.
Answer: can current eight rationally undergo a single diagnostic replay before a new mechanism family is designed? Is a registered minimal 3-era option worth that? Could even negative or all WAIT outcomes be decision-useful, under what prereg risk/stop? No result-informed month extension.

**Astra gate matrix** (one row each): (1) true power/support clearly inadequate; (2) high hidden multiplicity/design selection; (3) cost/funding/partial fills unable to identify economic claim; (4) proposed method amendment conflicts with accepted H41/H42 or R3 methods. Each `MATERIAL_ASTRA_REQUIRED`, `SOL_RESOLVED_CONTROLLER_CAN_FREEZE`, or `NOT_MATERIAL_NOW`, with specific unresolved decision and *what Astra could actually change*. Do not request Astra to rerun routine engineering tests, re-review P1 or duplicate prior H41 Astra. Only Controller may authorize **one** material Astra audit after Sol is pushed and reviewed.

**Verdict:** ONE of `SCIENCE_READY`, `METHOD_REPAIR_REQUIRED`, `ECONOMIC_NO_GO`, `INSUFFICIENT_EVIDENCE`; add `claim_scope` and `source_grade`. If zero fresh outcome access, `ECONOMIC_NO_GO` is allowed ONLY for analytically proven design/geometry impossibility under frozen assumptions; NEVER as empirical no-edge claim. `SCIENCE_READY` means P3 science design sufficient *conditional on P1/P2* and specified minimal prereg edits, **not** empirical Alpha evidence. If ambiguities prevent defensible P3 freeze, `METHOD_REPAIR_REQUIRED`.

## 8. Exact deliverables, safety counters and automatic push

Three required docs-only artifacts:
- `docs/strategy_research/g2_r3/scientific_strategy_review_r1/ECONOMIC_MECHANISM_COST_POWER_REPORT.md` — cite each exact source ref; include 8-row mechanism ledger, cost algebra/hit-rate derivation, sparsity / dependence toy grid, A/B/C table, diff vs prior Sol R1.
- `evidence/v0.6/b_line/g2_r3_scientific_strategy_review_r1/SCIENCE_REVIEW_MATRIX.json` — canonical deterministic key structure with `task_id, controller_dispatch_sha, branch_start_sha, original_eight_sha, method_sha, prior_sol_science_sha, restricted_sources_read, candidate_rows[8], break_even_scenarios, effective_blocks_power_toy, three_route_comparison, p3_required_delta, astra_disputes, terminal_verdict, zero_access_counters`.
- `reviews/v0.6/b_line/scientific_strategy_review_r1/P3_MINIMUM_DELTA_AND_ASTRA_GATE.md` — concise decision-grade P1/P2/Science→P3→P4 path, stop/fallback rules for engine failure and inadequate net economics, explicit independent Astra necessity/no-necessity.

**Evidence discipline:** Never claim absolute network-access zero from an unverified global environment; report work-scope `new_empirical_price_reads=0, protected_reads=0, exchange_private_calls=0, live_writes=0` only if genuinely observed. No Python or business outcome tests needed for analytic docs; exact symbolic calculations may be checked with hermetic arithmetic only, no market data. CI `mode=none` gives **0 tests** and is not proof of scientific adequacy.

**Commit/push:** One cohesive commit on the new science branch only, plus at most a machine-receipt-only follow-up if SHA cannot be included without self-reference. Verify changed-path allowlist, `git diff --check`, JSON parser, all 8 rows, source-link existence, commit parent == pinned branch start (if single commit), remote `ls-remote --heads` equals final SHA, and CI if available. **Proactively non-force push**, verify remote SHA, and return `REMOTE_PUSH_VERIFIED=true`, exact `EXECUTION_BRANCH`, `FINAL_SHA`, `PARENT`, artifacts, test/sanity checks, unambiguous verdict. If push fails `BLOCKED_NOT_PUSHED`. Do NOT wait for the user to say “push”.

**Unchanged safety:** `P1=IN_PROGRESS`, `P2=LOCAL_ROOT_UNKNOWN`, `P3_PREREG_EFFECTIVE=NONE`, `P4_EMPIRICAL_BODY_AUTHORITY=NONE`, `G4_TESTNET=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `AUTONOMOUS_LIVE=FORBIDDEN`.
