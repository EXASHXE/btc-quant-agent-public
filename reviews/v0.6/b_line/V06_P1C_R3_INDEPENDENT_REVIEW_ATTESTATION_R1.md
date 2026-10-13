# Independent P1C-R3 Second-Review Attestation and Provenance Closure R1

**Independent reviewer:** ChatGPT-1 — Independent Supervisory Auditor, distinct from the Gemini NORMAL author of R3, the R2 author, and ChatGPT-0 Controller. This is an attributable **new** independent review performed against immutable public GitHub artifacts, not a retroactively invented Codex Sol attestation.  
**Date:** 2026-10-14, Asia/Singapore.  
**Terminal verdict on the R3 artifact as published: `REVIEW_FAIL`.**  
**Numeric sub-verdict:** `PASS_42_CELL_NUMERIC_CROSSWALK_ONLY` (42 independently cross-checked values; 18 original matches, 24 original differences; 12 scoped H18/Exit cross-source agreements).  
**Release/science:** `G2_ALPHA_NO_GO`; TESTNET, LIVE and real-funds authority **NONE**. This is report forensics, not historical performance certification.

## A. Immutable review authority and identities

- Controller task dispatch: `efe0dce0773e2ac76771dda7847a4dffbe867ceb`, `prompts/v0.6/b_line/V06_NEXT_P1C_R3_SECOND_REVIEW_PROVENANCE_CLOSURE_R1.md` (dispatch blob `63a9ade550a47eacf969093fdc10b6dd2da581d5`). The remote canonical `v0.6-docs` HEAD observed at review start was this same dispatch SHA.
- Authorized new branch: `docs/v06-p1c-r3-independent-attestation-r1`; exactly the parent `2c99c8f64368a02dfeca05ac1886ed2280faf3ba`. Only this document may be added, without editing or merging any frozen source. The resulting new commit is recorded separately after publication.
- Frozen reviewed R3 docs SHA `c7d68cfd3f97c27723a48fb4722dd39ddc4a1290` (one commit above parent `feaf55386dfa20c125236533d28514a587bfcf0a`, exactly **two added R3 documents**, no earlier artifact edits):
  - `reviews/v0.6/b_line/V06_P1C_H18_TABLE4_CORRECTED_ERRATUM_R3.md`; Git blob `f7f1be23defc6a3d13b8f4576d9952ffdcd19cb9`.
  - `reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json`; Git blob `3d9e4a0c1f7116eb03edd793b5f670b5002ca167`.
- R2 failed and immutable at `b4f24c763895c97a0c304dc422db76a73761251d`: Markdown blob `78da392fc16ff12abd0284bd91e77b7b9e2c9590`; crosswalk JSON blob `0cfb9fb00c64d4352e3f9005f25a257b3006a39d`. R2 `REVIEW_FAIL` was accepted by the Controller at `feaf55386dfa20c125236533d28514a587bfcf0a`, adjudication blob `5c4aa09beacedf7706710a091cc7f5a93647dd0f`.
- Original H18 empirical narrative at `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`: `docs/strategy_research/g2_goal_h18_mechanism_r1/H18_MECHANISM_EMPIRICAL_REPORT.md`, blob `4d0601f29e8bdf3846107e079d6a82322a00adf6`; H18 machine summary `evidence/v0.6/b_line/g2_goal_h18_mechanism_r1/H18_MECHANISM_DIAGNOSTIC_RESULTS.json`, blob `ebd28897737728872390451ff5162e6cc43ae204`.
- Canonical Exit R1 at `55ac4c631c69f6edbd275462ad23e4486b9782ed`: `docs/strategy_research/g2_exit_horizon_r1/EXIT_R1_EMPIRICAL_REPORT.md`, blob `772b4cb5e6eeb19778849305dc3398b1e1de5ecb`; machine summary `evidence/v0.6/b_line/g2_exit_horizon_r1/EXIT_R1_RESULTS.json`, blob `c264831f44ae3e93df498eae8ea55f4b9cb631ff`.

**Prior reviewer recovery:** repository branch/ref search for the expected independent attestation branch returned no ref; repository search for the exact attestation path returned no matching file. Only the Gemini-authored R3 JSON's anonymous `independent_reviewer_audit` declaration and R3 Markdown's `REVIEW_PENDING` could be found. The former lacks a separately attributable review log/commit/identity and cannot count as a prior independent check. This review therefore independently performs the evidence check now; it does not claim earlier Sol execution, historical sign-off, or an independent test run that did not occur.

## B. Independent scope, method and reproducibility

**OBSERVED and independently COMPUTED** via connected GitHub on exact frozen source blobs. No old code, datasets, raw trading transactions or source runners were opened. The reviewer fetched only the enumerated allowed narrative/report/summary documents. No local test or historical PnL run occurred.

For each of the 42 combinations (two candidates × three annual cohorts × seven metrics), the review:
1. Parsed the original published six Table 4 rows from the immutable H18 narrative, stripping display signs/percent decorations without changing values. In each row metric order is `N, E0, H1, H2, H1-E0, Account_E0, Account_H1`.
2. Traversed **each** R3 JSON `canonical_source_field_path` in the original Exit R1 frozen machine object and independently recomputed its underlying value rather than treating the R3 value as authoritative.
3. For `H1-E0`, subtracted the two **unrounded machine yearly means** before rounding once. Compared the raw result with R3's original-unrounded canonical field at **1e-10 bp**, then used **integer decimal/BIGINT fixed-point half-up 2-decimal rendering**. For count `N`, used exact integer equality. Account returns are percentages (%); deviations between account returns must be reported in **percentage points (pp)**, and mean/delta units are basis points (bp).
4. Compared each original narrative value, correctly rounded canonical display, `MATCH/DIFFER` classification, and corresponding 42-cell Markdown/JSON row. All 42 rows' MD-vs-JSON status/classification/unit/deviation values and displayed source numbers (six decimal places) were cross-checked.
5. Looked up the six annual `event_count` and six annual `mean_delta_net_bps` fields at each declared H18 source path. All 12 agree with the Exit R1 values at ≤1e-10 bp (integer exact for counts). **The remaining 30 H18 machine comparison slots are null / absent and not independently cross-source corroborated.** This is not full ledger reproduction or an all-timestamp proof.

**Results:** `42/42` source paths resolve; `42/42` numeric/status/units/MD crosswalk checks match; `24 DIFFER` / `18 MATCH` relative to original H18 narrative; `12/12` limited H18 machine matches; no numeric contradictions discovered in the frozen R3 42-cell crosswalk. Assertions were evaluated with exact integer-scaled decimal representations from the original JSON numeric lexemes, not binary floating-point rounding for the canonical value derivation.

**Path-generation cross-check:** candidate keys are `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` and `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H`. The exact full source path for each row is retained in the frozen R3 JSON:
- `N`: `candidates.<candidate>.STRESS.paired.E0.yearly_breakdown.<year>.n_trades`.
- `E0/H1/H2`: `candidates.<candidate>.STRESS.paired.<scheme>.yearly_breakdown.<year>.mean_net_bps`.
- `H1-E0`: subtract `paired.H1` and `paired.E0` raw `mean_net_bps`.
- `Account_E0/Account_H1`: `candidates.<candidate>.STRESS.account.<scheme>.metrics.yearly_breakdown.<year>.cash_return_pct`.
- H18 matching 12 keys only: `regime_stratification.<candidate>.STRESS.year.<year>.event_count` or `mean_delta_net_bps`.

**Numeric anchors verified independently:** W1 2023 H1–E0 = `56.883119527965495...` bp → **+56.88 bp**, not published +56.89; W2 2023 = `27.386911967605211...` bp → **+27.39 bp**, not published +27.38. W2 2021 H1–E0 = `-0.25764759005736...` bp → **−0.26 bp** (not `+-0.26`). All differences are derived from unrounded Exit R1 machine means.

### Complete 42-row independent result ledger

Every row below was retrieved and compared to its exact frozen source path. **N** values are events, **Account_*** values are %, all other values are bp. For account-return deviation use pp, not percent.

| # | Candidate | Year | Metric | Original | Recomputed canonical display | Comparison |
|---:|---|---:|---|---:|---:|---|
| 1 | W1_C04 | 2021 | N | 8 | 8 | MATCH |
| 2 | W1_C04 | 2021 | E0 | 104.58 | 104.58 | MATCH |
| 3 | W1_C04 | 2021 | H1 | 128.53 | 107.52 | DIFFER |
| 4 | W1_C04 | 2021 | H2 | 91.56 | 91.56 | MATCH |
| 5 | W1_C04 | 2021 | H1-E0 | 23.95 | 2.94 | DIFFER |
| 6 | W1_C04 | 2021 | Account_E0 | 4.95 | 7.50 | DIFFER |
| 7 | W1_C04 | 2021 | Account_H1 | 5.72 | 7.72 | DIFFER |
| 8 | W1_C04 | 2022 | N | 10 | 10 | MATCH |
| 9 | W1_C04 | 2022 | E0 | -11.92 | -11.92 | MATCH |
| 10 | W1_C04 | 2022 | H1 | 20.25 | 21.68 | DIFFER |
| 11 | W1_C04 | 2022 | H2 | 48.83 | 48.83 | MATCH |
| 12 | W1_C04 | 2022 | H1-E0 | 32.17 | 33.61 | DIFFER |
| 13 | W1_C04 | 2022 | Account_E0 | 1.37 | -1.05 | DIFFER |
| 14 | W1_C04 | 2022 | Account_H1 | 3.85 | 1.83 | DIFFER |
| 15 | W1_C04 | 2023 | N | 16 | 16 | MATCH |
| 16 | W1_C04 | 2023 | E0 | -21.03 | -21.03 | MATCH |
| 17 | W1_C04 | 2023 | H1 | 35.86 | 35.86 | MATCH |
| 18 | W1_C04 | 2023 | H2 | 17.36 | 17.36 | MATCH |
| 19 | W1_C04 | 2023 | H1-E0 | 56.89 | 56.88 | DIFFER |
| 20 | W1_C04 | 2023 | Account_E0 | -2.93 | -2.93 | MATCH |
| 21 | W1_C04 | 2023 | Account_H1 | 4.75 | 4.75 | MATCH |
| 22 | W2_C05 | 2021 | N | 14 | 10 | DIFFER |
| 23 | W2_C05 | 2021 | E0 | 92.42 | 131.22 | DIFFER |
| 24 | W2_C05 | 2021 | H1 | 117.43 | 130.96 | DIFFER |
| 25 | W2_C05 | 2021 | H2 | 104.53 | 182.14 | DIFFER |
| 26 | W2_C05 | 2021 | H1-E0 | 25.01 | -0.26 | DIFFER |
| 27 | W2_C05 | 2021 | Account_E0 | 8.23 | 12.18 | DIFFER |
| 28 | W2_C05 | 2021 | Account_H1 | 10.15 | 12.14 | DIFFER |
| 29 | W2_C05 | 2022 | N | 17 | 21 | DIFFER |
| 30 | W2_C05 | 2022 | E0 | 35.84 | 39.31 | DIFFER |
| 31 | W2_C05 | 2022 | H1 | 56.59 | 66.89 | DIFFER |
| 32 | W2_C05 | 2022 | H2 | 44.52 | 28.30 | DIFFER |
| 33 | W2_C05 | 2022 | H1-E0 | 20.75 | 27.58 | DIFFER |
| 34 | W2_C05 | 2022 | Account_E0 | 10.98 | 6.74 | DIFFER |
| 35 | W2_C05 | 2022 | Account_H1 | 14.37 | 11.44 | DIFFER |
| 36 | W2_C05 | 2023 | N | 24 | 24 | MATCH |
| 37 | W2_C05 | 2023 | E0 | -45.49 | -45.49 | MATCH |
| 38 | W2_C05 | 2023 | H1 | -18.11 | -18.11 | MATCH |
| 39 | W2_C05 | 2023 | H2 | -24.98 | -24.98 | MATCH |
| 40 | W2_C05 | 2023 | H1-E0 | 27.38 | 27.39 | DIFFER |
| 41 | W2_C05 | 2023 | Account_E0 | -8.40 | -8.40 | MATCH |
| 42 | W2_C05 | 2023 | Account_H1 | -3.23 | -3.23 | MATCH |

## C. Additional provenance and scientific controls

- **Cost units — ACCEPTED for definition only.** H18 and Exit R1 define STRESS44 as assumed **44 bp round-trip** research friction: 24 bp assumed total fees, 8 bp spread and 12 bp slippage. It is not a personally observed Binance fee, real execution or measured maker/taker queue cost.
- **Cross-source identity limited.** The H18 machine agrees with Exit R1 only on the six annual event counts and six paired yearly mean deltas. The other 30 canonical source values are extracted from the frozen Exit R1 summary and cannot be asserted to have independent H18 machine agreement. This verdict says nothing about the correctness of underlying historical market/return events, runner, source calendars, true PIT or the absence of latent defects.
- **W2 count disagreement and dates — VERIFIED AS EXIT ID METADATA ONLY.** Original H18 Table 4 shows `2021/2022 N=14/17`, while Exit/H18 machine summaries show `10/21` (both sum to 31); W2 2023 is 24. `EXIT_R1_RESULTS.json` public `candidates.W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H.STRESS.account.E0.accepted_event_ids` contains 55 identifiers. Parsed embedded UTC epoch timestamps yield 2021 n=10 from `2021-04-26T01:45:00Z` to `2021-12-23T20:45:00Z`, 2022 n=21 from `2022-01-13T18:45:00Z` to `2022-12-11T21:00:00Z`, and 2023 n=24. This verifies an **Exit R1 identifier encoding**, not original H18 event identities, receiver known-at or a four-event drafting shift. Actual manuscript-cause and individual transferred event identities are **UNKNOWN**.
- **W1 2021 copy hypothesis — INFERRED ONLY.** R2's reported `+23.95` is numerically similar to Exit R1 E2/SHORT `23.950589292003308` bp, and `104.58 + 23.95 = 128.53` is an arithmetic coincidence. It does not prove who copied what or how the original table was drafted. The cause remains **UNKNOWN**.
- **Continuation/right-tail — DESCRIPTIVE_ONLY.** The published continuation fraction is `26/56 = 46.428571...%` adverse; there is no dependence-aware 50/50 hypothesis test. W1 4 target winners contribute ~98.0642506% and W2 3 contribute ~74.6362480% of ex-post H1–E0 gains. This does not identify an ex-ante 12h or entry-time classifier; it **also cannot prove none exists**. No historical rerun or classifier design is authorized by this task.

## D. Material findings — why terminal overall review FAILS despite accurate numbers

### Finding 1 — HIGH / OBSERVED: unverifiable self-ascribed independent verdict in the frozen R3 JSON

At reviewed SHA `c7d68cf...`, Markdown **lines 9–12 and 181–185** explicitly state that Gemini NORMAL authored the correction and an independent second review is **`REVIEW_PENDING`**. The companion JSON `crosswalk_metadata.reviewer_status` instead states **`REVIEW_PASS`**, and `crosswalk_metadata.independent_reviewer_audit` claims an anonymous `Independent Second Reviewer (Codex Sol / ChatGPT-1 Auditor)`, `verdict=REVIEW_PASS`, `verified_cells_count=42`. No separate attributable reviewer artifact, real review execution record or reviewer commitment is in the R3 two-file diff. This is an incompatible source-state/provenance claim, not an independently valid certification.

**Disposition:** original R3 JSON reviewer-PASS remains **UNVERIFIED / NOT ACCEPTED**; this new independent review has its own separate review identity, date, scope and outcome and must not be backdated as the person behind that earlier anonymous field.

### Finding 2 — HIGH / OBSERVED: R3 prose overstates causal impossibility and assumes a manuscript calculation mechanism

In R3 Markdown **line 166**, despite correctly labelling right-tail concentration as ex-post, the text asserts: **“No causal entry-time feature distinguishes these 7 winners from the remaining 49 trades without lookahead bias.”** The available retrospective concentration table does not establish the nonexistence of an ex-ante predictor. The valid weaker claim is that no such feature has been *established by this analysis*.

R3 per-cell notes at **lines 121–133**, including W2 2021/2022 mean and account-return cells, repeatedly assert **“Calculated over non-canonical cohort.”** The original N partitions differ, but no manuscript construction log or underlying narrative cohort identity is available to prove that these exact numbers were calculated from a specific alternate cohort. R3 section 6 (line 153) itself correctly says drafting/partition cause **UNKNOWN**. The source evidence establishes **mismatch**, not production mechanism. This does not invalidate the corrected numeric source values but materially overstates scientific and forensic certainty.

**Disposition:** independent numerical correction accepted within defined scope; prose scientific/provenance assertions **FAIL** pending a versioned, non-destructive qualification sidecar. No empirical strategy inference or retrospective new trial follows.

### Finding 3 — CONCERN / OBSERVED: misleading signed display and ambiguous match-language

R3 Markdown **line 124**, 42-cell table row #26 (W2_C05/2021 H1–E0) describes the correct negative figure as **`+-0.26 bp`**. The actual row's canonical column and JSON have **−0.26 bp**, so the table numeric correction remains correct, but the explanatory text is malformed.

R3 Markdown **line 156** under “Exact / Rounded Matches (18 cells)” says **“All 6 event counts match Exit R1”**. This is correct only for **corrected machine-backed counts**, not the original Table 4 (two W2 original annual counts differ). Explicitly qualify which layer is matching to avoid contradicting the 18/24 count.

**Disposition:** textual corrections only; do not alter original R3 immutable artifacts under this task.

## E. Terminal decision, next bounded gate and protected boundaries

**`REVIEW_FAIL` — overall corrected R3 document as published, on provenance-science/text-governance grounds.** Not a claim that the 42 numeric corrections fail: they **passed** the independently performed source crosswalk.

**Recommended one finite Controller action:** issue a narrowly scoped **English-only P1C-R4 clarification/attestation-response sidecar** on a *separate* Controller-authorized docs branch. It should (a) distinguish historical anonymous PASS claim from this genuine independent result; (b) remove categorical claims about nonexistent causal features and unproven manuscript cohort mechanisms; (c) fix `+-0.26` and ambiguously worded event-count matches; (d) quote this independently verified 42-cell numeric crosswalk without rerunning or rewriting frozen results. Have a distinct reviewer verify the new version's claims and exact SHA before final Controller L2 acceptance. If scope cannot be granted, terminal remains `REVIEW_FAIL`; do not manufacture PASS or change old documents.

**Actual reviewer execution receipts:** connected GitHub fetch of fixed public repository files, commit/base comparison, ref/branch and code/path search, and deterministic JavaScript lexical fixed-point decimal comparisons using BigInt. **No** Python/pytest, GitHub Actions full suite, local source runner, backtest, original PnL recalculation, external exchange API, protected-data inspection, raw trade return sample, or asynchronous work. Docs-only absence of CI execution is **not** an executable `PASS`.

**Read/write boundary:** zero changes to R3/R2/H18/Exit source, code/tests, CI, golden, original machine results, or Controller canonical branch. No protected H39/H40/H41/Forward/Final Holdout, owner local data roots, private credentials/accounts, or live trading endpoints accessed. New write path is only `reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md` on the new isolated docs branch.

**Auditor strategic recommendation:** `BOUNDED_REPAIR` (prose/provenance sidecar only). This advisory verdict is **not** Controller approval for source admission, strategy trials, G2 Alpha, merges, TESTNET, LIVE or real-money actions.
