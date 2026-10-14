# RESET R2 — Independent Synthetic Sparse-Inference Method Audit

**INDEPENDENT REVIEWER:** ChatGPT-3 Quantitative Challenger, independently instructed, not the Codex Sol High implementer or the Controller. **Review date:** 2026-10-14 (Asia/Shanghai). **Scope:** immutable source/method, public CI *summary only*, and independent invented Gaussian arithmetic/Monte Carlo. **No historical F1–F3 scoring, market collection, protected H40 contents, code modification, or self-approval by the implementer.**

**TERMINAL: `SYNTHETIC_METHOD_AUDIT_PASS_WITH_LIMITS` — `SYNTHETIC_KNOWN_DGP_ONLY`; `REAL_DATA_INFERENCE_NOT_ADMITTED`; `FULL_CI_FAILED`.** The new method provides a logically valid simultaneous CI **only when an externally justified, finite, ex-ante population-variance envelope is correct and the prespecified analysis units are independent**. The synthetic experiment tests examples satisfying those assumptions; it does not estimate or validate them for real BTC weeks. Old F1–F3 remains `SIMULTANEOUS_INFERENCE_UNCALIBRATED`, and its observed positive/negative proxy summaries cannot be repriced or rescored here.

## 1. Exact immutable identity and remote publication boundary

| Object | Exact immutable identity | Independent verification |
|---|---|---|
| Authoritative R2 audit dispatch | `70fde472d83c3ed9ba24d130ba8d7ec36c4e1fa5`; `prompts/v0.6/b_line/V06_RESET_R2_SPARSE_INFERENCE_INDEPENDENT_AUDIT.md`; blob `97356062d3072c22adb6b07991092b2e9a7e5163` | GitHub file content and git blob retrieved at requested exact SHA |
| Original P1 synthetic dispatch | `ceb851765b84e8e83b78caa6ceecbc665e57c02f`; `prompts/v0.6/b_line/V06_RESET_R1_SPARSE_INFERENCE_SYNTHETIC.md`; blob `dc0c73f07fbfeba3ebc54160a1bac647607a5a6d` | Explicitly assigns Codex Sol High as implementer and ChatGPT-3 as independent reviewer |
| Audited frozen implementation | `c7c8d98520b21f3d36352e1ba0df408327e011fe`, baseline `13e3a710b137efeec2e21e3002f748834ec0cc22` | Git compare: **one commit ahead**, precisely two added files, no replacement |
| New method module | `scripts/strategy_research/g2_sparse_inference_synthetic_calibration_r1.py` | Blob `5208f25268ec7e4efe854b7f5e13c55deb8e0d04`; 378 source lines plus terminal newline |
| New test module | `tests/test_v06_g2_sparse_inference_synthetic_calibration_r1.py` | Blob `50eca94c86f73837a3842d6202b1b3eb9600ce0e`; 187 source lines plus terminal newline |
| Immutable old *method only* | `f25954b45577cebb7624fae86cd91df9071a87ab`; `scripts/strategy_research/g2_flow_funding_entries_r1/statistics.py` | Blob `f86ee6c20c8bc08f0e42dcb4d586b4d908290018`; old historical runner and input arrays neither accessed nor run |

**Reviewer publication:** this file is the **only** allowed new path on isolated branch `docs/v06-reset-r1-inference-independent-method-audit`, created from `70fde472d83c3ed9ba24d130ba8d7ec36c4e1fa5`. Record publication commit/blobs externally after GitHub accepts the write; never claim a commit preimage contains its own immutable SHA. Independence here means separately executed review and independently derived challenge, **not** a cryptographically distinct GitHub identity. Implementation remains untouched.

## 2. Old clipped-SE defect: reproduced analytically, not using F1–F3 market records

The pinned original `compute_block_bootstrap_max_t` computes calendar-block sums, resamples common block indices, studentizes each bootstrap mean difference, and explicitly clamps the **resampled** SE to `max(b_se, 1e-6)`. If one arm's bootstrap sample is constant zero despite a positive original block mean, the numerator remains nonzero but the denominator becomes `1e-6`; the max-|T| family quantile can be dominated by this numerical artifact. It is **not** a reliable corrected significance test.

**Invented one-arm witness:** 32 calendar-week totals, exactly one `+10 bp` and 31 zeros. Observed mean `10/32 = 0.3125 bp/week`; an iid bootstrap omits the nonzero week with probability `(31/32)^32 = 0.362055289...`. Then the resampled SE is zero and the clipped studentized absolute deviation is `0.3125 / 1e-6 = 312,500`. This magnitude describes the broken statistic's *computed critical value*, **not** a risk estimate, plausible BTC cost, or validated historical signal. Frozen synthetic test checks this same construction, including exact-reference function comparison on invented timestamps/weekly returns. It does not justify reusing the original F3 intervals.

**Finding S01: `OLD_METHOD_INVALID_FOR_INFERENCE` (confirmed).** Not fixed by changing epsilon, suppressing empty blocks, deleting sparse weeks or adjusting the H32/F3 trial budget.

## 3. New candidate's precise theorem — accept conditional proof, reject general calibration inference

For `n` **independent** analysis units indexed `i` and `A` jointly tested arms `a`, let `X_{ia}` be an additive **calendar-week / supercluster total in bp**, not a per-trade return. Before observing any outcome, assume each arm/unit has a genuine population bound `Var(X_{ia}) <= v_{ia}`, with finite `v_{ia} >= 0`. Within-unit correlations across arms are unrestricted. The parameter `mu_a` is the equal-unit average of possibly heterogeneous `E[X_{ia}]`. Then

`Var(Xbar_a) <= V_a = sum_i(v_{ia}) / n^2`.

With `h = sqrt((sum_a V_a) / alpha)`, Chebyshev plus the union bound gives

`P(any_a abs(Xbar_a - mu_a) > h) <= sum_a(V_a / h^2) <= alpha`.

Therefore all `[Xbar_a-h, Xbar_a+h]` intervals simultaneously cover their stated means at least `1-alpha`. This remains true when arms correlate or when some units have no events; `n` must count actual **independent** units and omitted zero-event units must remain included. It is an **equal-calendar-unit estimand**: a large-event week does not receive larger weight. This differs from the mean bp **per executed trade** used in earlier F1–F3 strategy reports, so this candidate is **not** a plug-in replacement even if later source data were authorized.

**S02 CONDITIONAL PASS:** The formula in `candidate_intervals` faithfully implements that theorem: it validates finite shapes and nonnegative `v`, computes `h` from all arms, and does not divide by bootstrap SE or infer variance from a degenerate sample. An `all_zero` population DGP with *provably zero variance* correctly yields zero-width intervals; observing 32 zeros in a nondegenerate population does **not** justify `v=0`.

**S03 BLOCKER FOR REAL-DATA ADOPTION:** The function accepts a caller-supplied `independent_units=True` flag and caller-supplied numeric `variance_upper_bps2`. Neither the software, the public prices nor the synthetic tests **prove** these claims for real BTC. Mislabeling a parameter fitted from realized events as an a-priori population upper bound voids the theorem. If finite defensible bounds or independence cannot be established externally and frozen outcome-blind, **fail closed** with `VARIANCE_BOUND_UNKNOWN / CLUSTER_INDEPENDENCE_UNPROVEN`; do **not** output a purported calibrated 95% CI. This is a non-admission limitation, not a coding bug under the declared contract.

No distribution-free finite-sample CI with this same guarantee is derived for an unbounded, unknown-variance or arbitrarily dependent data-generating process. Heavy-tailed t3 in the fixture grid has finite, **known** variance 3, unlike generic infinite-variance or adversarial financial tails.

## 4. Fixed synthetic nulls, FWER, coverage and Monte Carlo error

Frozen settings verified directly from the exact module:
- **6 arms**, two-sided family `alpha=0.05`.
- Seeds `20261014`, `20261015`; **512 invented independent simulation trials per seed/DGP**; old comparison **199** shared-index resamples each; failure exhibit **2,000** resamples.
- Ten finite null DGP names: `all_zero`, `sparse_97pct_empty`, `constant_shift_null`, `unequal_event_counts`, `clustered_four_weeks`, `degenerate_arm`, `heavy_tail_t3`, `sign_flipped_skew`, `multi_arm_gaussian`, `rare_asymmetric_null`.
- The **32-unit** null grid assigns *population-known* `v`: 0 for exactly-zero population; 2.5 for 2.5%-active ±10 bp; 4 for **one** independent common-shift unit; unequal-count heteroskedastic Gaussian variance `1,2,5,9` per week; `1+0.01/4=1.0025` per four-week-averaged independent cluster; 0 for the deterministic degenerate arm and 1 for others; t3 variance 3; shared-sign exponential skew variance 1; normal variance 1; rare asymmetric centered `100*(Bernoulli(0.001)-0.001)` variance **9.99**. None is estimated from realized F3 data.
- `constant_shift_null` correctly contracts 32 perfectly dependent identical weeks into **one** independent unit. `clustered_four_weeks` contracts 128 correlated raw weeks into 32 independent four-week mean units; it is **not** a general long-memory guarantee.
- Each null trial counts `any` among six false exclusions of true mean zero: this is a six-arm **FWER** event. Under a zero-mean null, simultaneous coverage `=1-FWER` exactly in each trial, so the two reported metrics are complements, **not independent evidence channels**.

The Wilson uncertainty calculation uses `MC_FAMILY_ERROR=0.01`, **224** prespecified MC interval slots (10 DGP × 2 methods × 2 metrics × 2 seeds, plus 36 planted-grid cells × 2 seeds × 2 power methods), and `z=4.082036...`. For **zero failures out of 512**, the resulting multiplicity-adjusted Wilson **upper** error bound is approximately **0.031519**, not zero; complementary coverage lower bound is approximately **0.968481**. The gate expressly requires `FWER upper <= .05` and `coverage lower >= .95` in all 20 candidate null cells. This is a conservative Monte Carlo *testing gate* and does not independently establish the required physical variance bounds.

**S04 SYNTHETIC NULL GATE:** The two frozen-seed calibration and replay tests were included in the targeted test file and the full CI; their pass status follows from the absence of a target-file failure and the full-suite summary, not from an auditor-initiated fresh reproduction of all 512×10×2 samples. We separately recomputed the theorem, Wilson zero-count bound and two adversarial synthetic counterexamples below. We **do not** claim an independent full-suite rerun or claim exact runtime stdout/JSON statistics we have not fetched.

**S05 FWER family caveat:** Six candidate arms represent only the *invented fixture family*. The old F1–F3 endpoints, H32–H34, Goal-A/B, R3 cells, future thresholds/horizons, prior exposed selection, opportunity matching and reporting filters **must** remain in the eventual preregistered scientific family. The six-arm Chebyshev radius cannot be applied to a larger cherry-picked family without re-freezing its dimensions and controlling the resulting multiplicity. Coverage also depends on how units with unequal exposure and missing/unobserved weeks are handled; invalid source coverage is not a legitimate observed zero.

## 5. Independent adversarial invented-DGP checks: guarantee collapses outside its assumptions

These are **new, invented Gaussian thought experiments plus a standalone independent numerical check**, not imports of the implementation or historic F1–F3. We used a fixed local RNG seed `20261014`, 50,000 invented Monte Carlo replicates, `n=32` apparent weeks, `A=6` arms, `alpha=.05`, and a **misrepresented** caller-declared `v_{ia}=1`. The candidate's hypothetical half-width is `sqrt(6/(32*.05)) = 1.9364916731 bp`.

| Invented diagnostic | Actual DGP | Analytic / independently measured violation | Status |
|---|---|---|---|
| **D1: long-memory/perfect common shock** | For each arm `a`, draw one `Z_a ~ N(0,1)` and repeat it identically for all 32 alleged weeks; each week's marginal variance **is 1**, but units are **NOT independent** | Under false `independent_units=True`, analytic FWER `1 - [1-2*(1-Phi(1.9364917))]^6 = 0.2778466`; standalone 50,000-trial FWER **0.27528**, simultaneous coverage **0.72472** | **FAIL OUTSIDE CONTRACT**; passing an unsupported independence flag gives false assurance |
| **D2: externally understated variance** | 32 truly independent `N(0,40)` weeks per arm, yet declared `v=1` | Standalone 50,000-trial FWER **0.40770**, coverage **0.59230** | **FAIL OUTSIDE CONTRACT**; a sample-dependent, guessed or wrong upper bound invalidates the nominal claim |

Reproducibility for the **standalone adversarial check only**: independent Python NumPy draws `rng=np.random.default_rng(20261014)`; generate `latent=rng.normal(0,1,(50000,6))`, score `any(abs(latent)>sqrt(3.75),axis=1)`; then `means=rng.normal(0,sqrt(40/32),(50000,6))` from the same RNG, score the same event. No BTC, source file, trade result, historical price or repository runtime was involved. The difference between the exact Gaussian FWER and simulated rate is ordinary MC noise. The implementation explicitly rejects `independent_units=False`, so this finding **does not refute the stated theorem**; it demonstrates that external caller attestation is a serious science gate. Different weaker serial dependence or infinite-variance tails are **not** covered by these two illustrations, and are not admitted by the frozen contract.

## 6. Future synthetic power: mathematically consistent but not a market power estimate

The future grid is fixed to `n ∈ {26,52,104,208}` **independent weeks**, `p ∈ {.05,.25,1}` active probability per week and invented conditional cost-noise SD `c ∈ {1,5,15}` bp, **36** tuples × **2** seeds, 512 replicates each. Only arm 0 has planted **+5 bp per active event**; its true mean is `mu = p*5 bp/week`, explicitly **not +5 bp per trade over the calendar weeks**. The declared population variance envelope is `v=p*(4+c²)+p*(1-p)*25`; the `6v` family-width term conservatively covers arms with or without the planted mean.

For the one-sided positive-exclusion event `Xbar_0 > h`, the code's guaranteed power lower bound `max(0,1-v/[n*(mu-h)^2])` when `mu>h` follows from Chebyshev on arm-0 misses. Its inversion,
`n_min=ceil((sqrt(6v/.05)+sqrt(v/.20))²/mu²)`, is algebraically consistent for **this invented alternative and true known variance envelope**. Independent algebra over the frozen 36-cell grid finds **4/36** feasible at the predeclared ≥80%-power lower-bound criterion with the given maximum 208 weeks; this is **not** empirical BTC feasibility.

Illustrative independently calculated minimum effective weeks for 80% conservative guaranteed power:

| Invented event probability p | Cost-noise SD c=1 bp | c=5 bp | c=15 bp |
|---|---:|---:|---:|
| .05/week | 4,002 | 7,343 | 35,181 |
| .25/week | 662 | 1,330 | 6,897 |
| 1.0/week | 35 | 202 | 1,594 |

These are worst-case **guaranteed-power bounds** for the assumed model, not estimated requirements from trading data; they illustrate severe conservatism and the cost of scarce independent information. **S06:** Prior BTC horizon 4–24h, ~one qualified *candidate opportunity* per 48 hours, cannot be equated to the invented Bernoulli `p` without source-qualified canonical event counting, independent week support and fill/cost evidence.

## 7. Actual exact-source CI and runtime receipt — FULL GATE NOT GREEN

| Workflow | Observed GitHub state | Material outcome |
|---|---|---|
| [Push run 38513033356](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38513033356) | `head_sha=c7c8d98520b21f3d36352e1ba0df408327e011fe`; checkout planner logs `code_sha=c7c8d985...`; concluded **failure** | **3,006 passed / 1 failed / 2 skipped**, 9 warnings; pytest **799.75 s**; risk planner `full` |
| [PR run 38513054890](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38513054890) | Workflow associated with `head_sha=c7c8d985...`, but the risk-planner log records PR **merge checkout** `code_sha=b03de8a9b02d8ab8ed0b2c7da2e90bf78d1f0826`; concluded **failure** | **3,006 passed / 1 failed / 2 skipped**, 9 warnings; pytest **1026.42 s**; planner `full` |

**Single reported failure:** `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`, a protected H40 synthetic graph digest mismatch visible in the **public CI summary only**. We **did not inspect its protected source/artifacts or weaken it**. The sparse-calibration test path is absent from failures, and 3006 successful tests support its frozen suite passing inside both full runs. Ruff, mypy, compile and changed-JSON steps report success in both jobs. Two targeted synthetic power reproducibility test calls were among the slowest: **52.81/52.78 s** push and **65.45/65.09 s** PR; overall test execution costs are materially nontrivial.

**Attribution limit:** Two-source-file diff does not implicate H40, but this review cannot independently prove the H40 failure was preexisting, nor designate it safe to waive. Also, the PR **merge checkout** SHA is not the bare target source commit despite the run head reference; do not misstate both as byte-identical execution trees. Controller/CI owners retain authority to resolve that failure in an independently scoped track. **`FULL_CI_PASS = FALSE`**; method-science review cannot override CI.

## 8. Threat model, residual unknowns, acceptance and explicit prohibitions

**Accepted within the frozen synthetic-only scope:** correct defect diagnosis of the original SE-floor; independent exact blob identity and narrow two-add-path provenance; mathematically sound ex-ante variance Chebyshev–union simultaneous intervals; deliberate equal-week estimand and proper collapse of constructed four-week dependence; null grid with all-zero/rare/skew/t3 and declared population variance; familywise Wilson MC-error gate; separate planted-effect power calculation and reproducible finite seeds. Positive synthetic control is not evidence of market edge.

**Unresolved / blocked for real inference:** any defensible ex-ante upper bound on **real** BTC per-independent-unit weekly total variance; whether serial volatility regimes or return/cost shocks admit genuinely independent superclusters; presence of nonstationary or infinite-variance/heavier-than-t3 tails; silent missing observation epochs and zero-trade-vs-data-outage separation; whether the real target is equal-calendar mean or per-executed-trade expectancy; full historical multiplicity, selective admissions/portfolio occupancy and canonical episode identity; actual trade fee roles and execution cost, maker nonfill/queue/latency/gap, signed Funding+Mark PIT; true week event frequency, useful effect scale, calibrated effective sample size; both CI runs' H40 failure resolution. None is set to zero by lack of data.

**Final independent verdict:** `SYNTHETIC_METHOD_AUDIT_PASS_WITH_LIMITS` solely for the **known-DGP, correctly upper-bounded, independent-unit theorem and synthetic fixtures**. Record `SYNTHETIC_KNOWN_DGP_ONLY`, `OLD_F1_F3_SIMULTANEOUS_INFERENCE_UNCALIBRATED`, `VARIANCE_BOUND_UNKNOWN_FOR_REAL_BTC`, `CLUSTER_INDEPENDENCE_UNPROVEN`, `FULL_CI_FAILED`. Do **not** adopt this statistic for historical F1–F3 or prospective BTC evaluation without a new Controller exact-SHA authorization, independently source-justified variance/cluster specification, source/PIT/cost evidence, precommitted complete research family and appropriately reviewed sample-power plan. Do not interpret this scientific PASS-with-limits as Alpha, funding/basis validation, source admission, green CI, TESTNET, LIVE or real-funds authority.

**Execution and data-access audit:** GitHub public code/prompts/commit/compare/CI jobs and **public failure summary only**; independent locally generated Gaussian values and arithmetic **only**. Protected/reserved H39/H40/H41/Forward/Final Holdout contents **NONE**; historical BTC F1–F3 trades, performance labels, outcome arrays and market replay **NONE**; exchange market endpoints/network price capture **NONE**; owner/private folders/accounts/secrets **NONE**; historical reruns/parameter optimization **NONE**; target source/tests/goldens modifications **NONE**. This file is an independently authored review, not a claim that the synthetic implementation audited itself.
