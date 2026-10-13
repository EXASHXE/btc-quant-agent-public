# P1C-R4 — Independent Terminal Semantic and Provenance Audit R1

**Terminal verdict: `REVIEW_FAIL` (exact-line provenance defects in the frozen R4 response; not a finding of numerical or strategic result failure).**  
**Semantic correction sub-verdict: `PASS_WITHIN_BOUNDED_DOCUMENTARY_SCOPE`.**  
**Reviewer:** ChatGPT-1, independent supervisory audit role/session; NOT the Gemini NORMAL Stage A corrective author. This is a new independently executed Stage B audit, not a retrospective Codex Sol signoff. Git repository account metadata alone does not cryptographically prove the model or human identity behind Stage A; role separation is supported by the Controller dispatch, Stage A's explicit author declaration, and this distinct review execution.  
**Date:** 2026-10-14 (Asia/Shanghai).  
**Strategic gates:** G2 Alpha NO_GO; TESTNET/LIVE NOT AUTHORIZED; real-money writes NONE. No Controller L2 closure is issued by this reviewer.

## 1. Exact immutable authority, frozen target, and write integrity

| Role | Exact Git commit SHA | File and Git blob |
|---|---|---|
| Controller Stage B dispatch | `7568678a983c4b16c71908c8b0f9bcd3570e4a19` | `prompts/v0.6/b_line/V06_P1C_R4_INDEPENDENT_TERMINAL_AUDIT_R1.md` / `3f5dce05a0ffb9ec76279544a42f6d1f9dd770fa` |
| Stage A grant | `7568678a983c4b16c71908c8b0f9bcd3570e4a19` | `prompts/v0.6/b_line/V06_P1C_R4_DOCUMENTARY_CLARIFICATION_EXECUTION_R1.md` / `83c94dd62499c366cd2b5c609ae8194137d63aea` |
| Controller L2 scoped authorization | `7568678a983c4b16c71908c8b0f9bcd3570e4a19` | `reviews/v0.6/b_line/V06_P1C_R4_CONTROLLER_L2_SCOPED_AUTHORIZATION_R1.md` / `828ec8b7a117a4819ccea687e698808b8ed0ec15` |
| **R4 Stage A frozen reviewed target** | **`3a5c071c1e25a11d8047105657f8df6755dc3aba`** | **`reviews/v0.6/b_line/V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md` / `9d3857de60a622abf0a277271d249e9828940f04`** |
| Original R3 Markdown | `c7d68cfd3f97c27723a48fb4722dd39ddc4a1290` | `reviews/v0.6/b_line/V06_P1C_H18_TABLE4_CORRECTED_ERRATUM_R3.md` / `f7f1be23defc6a3d13b8f4576d9952ffdcd19cb9` |
| Original R3 crosswalk | `c7d68cfd3f97c27723a48fb4722dd39ddc4a1290` | `reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json` / `3d9e4a0c1f7116eb03edd793b5f670b5002ca167` |
| Independent R3 audit | `7750b69a87dcfb392bdfc8d20e7b7f174276452e` | `reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md` / `d2f2b366dd5af114981cac98604f09d60c5e4981` |
| Frozen H18 narrative/machine | `397a62c1a0fbd6ad14a569a5be0058b1f684f08e` | Report blob `4d0601f29e8bdf3846107e079d6a82322a00adf6`; diagnostic summary blob `ebd28897737728872390451ff5162e6cc43ae204` |
| Frozen Exit R1 narrative/machine | `55ac4c631c69f6edbd275462ad23e4486b9782ed` | Report blob `772b4cb5e6eeb19778849305dc3398b1e1de5ecb`; summary blob `c264831f44ae3e93df498eae8ea55f4b9cb631ff` |
| Historical R2 failed erratum | `b4f24c763895c97a0c304dc422db76a73761251d` | Markdown blob `78da392fc16ff12abd0284bd91e77b7b9e2c9590` (read-only; earlier R2 JSON remains frozen as well) |

**Target-frozen precondition VERIFIED.** The Stage A branch `docs/v06-p1c-r4-clarification-response-r1` resolved to full immutable commit `3a5c071...`, but all subsequent review reads were pinned to that SHA. Fetching the file by both fixed commit/path and exact Git blob produced identical content, Git blob `9d3857de...`. Comparing `7568678...` to `3a5c071...` gives exactly **one commit ahead** and exactly **one newly added Markdown file** (`+228/-0`); GitHub's exact commit parent is `7568678...`, and the file does not exist at that parent. No R2/R3/H18/Exit documents, JSON, code, tests, CI, golden or protected inputs were changed by this Stage A commit.

**Publication authority for this Stage B response** is a *different* isolated branch, `docs/v06-p1c-r4-independent-terminal-audit-r1`, created from exact Controller dispatch SHA `7568678...`. The sole allowed new path is `reviews/v0.6/b_line/V06_P1C_R4_INDEPENDENT_TERMINAL_AUDIT_R1.md`. This report's resulting commit and one-file diff are available from GitHub after publication. Neither branch is merged here.

## 2. Independently checked semantic acceptance questions

| Gate | Actual check / independent adjudication | Result |
|---|---|---|
| 1 — Status provenance | At R3 MD lines 11, 184 the status is `REVIEW_PENDING`; R3 JSON lines 12 and 56–66 assert a non-attributable `REVIEW_PASS`. The actually published independent R3 reviewer `7750b69...` issued `REVIEW_FAIL` overall but `PASS_42_CELL_NUMERIC_CROSSWALK_ONLY`. R4 lines 57–75 distinguish each without retroactive validation, and leave R4 `R4_REVIEW_PENDING` / `CONTROLLER_L2_PENDING`. | **PASS, scoped** |
| 2 — Ex-ante causality | The categorical R3 MD line 166 nonexistence assertion is replaced at R4 lines 79–96 with “No such ex-ante discriminator is validated by this analysis; whether one exists is UNKNOWN.” No invented alpha, classifier, or impossibility proof. | **PASS** |
| 3 — Cohort narrative origin | R4 lines 100–118 expressly classify presumed cohort transfer and manuscript calculations as UNKNOWN, while preserving original W2 2021/22 N=(14,17) vs canonical N=(10,21). This avoids implying four identifiable events were actually moved. | **PASS** |
| 4 — Signed number and count layer | R4 lines 122–136 correctly distinguish the original prose typo `+-0.26` from canonical `-0.26`; clarify that six counts match the **corrected canonical summaries**, whereas only four original narrative counts match. | **PASS on meaning, provenance citation defect** |
| 5 — Metric/source bounds | R4 lines 169–198 preserve STRESS44 44 bp assumed round-trip (24+8+12), bp/%/pp, original 18 match / 24 differ, the six counts + six deltas only, correct W1/W2 2023 deltas, descriptive 26/56, and ex-post 4/3 right-tail attribution. No independent source-ledger proof or strategy rerun claimed. | **PASS, scoped** |
| 6 — Separation/unknowns | R4 names Gemini NORMAL as corrective author, awaits external audit, preserves unknown authoring provenance and does not insert new independent `REVIEW_PASS`. No private/protected access or new causality proof claimed. Reviewer corroboration is new and separate, not sourced from author metadata as verification. | **PASS, evidence-limited** |
| 7 — Exact-SHA/diff/CI | One file newly added at frozen Stage A SHA, exact parent/approved branch verified. API query of GitHub Actions runs filtered for Stage A head SHA returned `total_count=0`; Stage A correctly says CI `NOT_RUN`. This is neither executable verification nor a release gate. | **PASS** |
| **8 — Exact citation traceability of provenance corrections** | Four R4 references to the *old independent review* point to the wrong sections, with two entirely past EOF; an extra R3 JSON field line number identifies an unrelated field. Exact provenance citations are mandatory for documentary closure. | **FAIL** |

### Independent numeric spot checks (not a fresh 42-cell rerun)

The prior independent 42/42 Decimal/BigInt source-path verification belongs to **the earlier separately published independent R3 audit** at `7750b69...` and is **reused by exact SHA**. This Stage B audit does **not** claim to have rerun all 42 checks. Instead, I independently read frozen Exit R1 and H18 **summary** JSONs and verified four referenced annual paired differences:

| Candidate/year | Exit R1 E0 raw bp | Exit R1 H1 raw bp | Difference bp rounded once | H18 summary delta agreement |
|---|---:|---:|---:|---|
| W1 2023 | -21.02600023916617 | 35.857119288799325 | **+56.88** | yes, approx 7.1e-15 bp discrepancy |
| W2 2023 | -45.493320037239755 | -18.106408069634544 | **+27.39** | exact at displayed float precision |
| W2 2021 | 131.21681427727543 | 130.95916668721807 | **−0.26** | yes, approx 1.62e-14 bp discrepancy |
| W2 2022 | 39.30549291352028 | 66.88515991881047 | **+27.58** | yes, approx 1.07e-14 bp discrepancy |

All four were newly spot-checked with JavaScript arithmetic against source summary fields; the original R3 42-cell verdict remains attributed to the earlier review, rather than an invented new 42/42 run.

The H18 summary itself identifies TIME_CAP support `20+36=56` and adverse continuations `11+15=26`, so 26/56=46.43% is **descriptive only**. H18 summary's target fate breakdowns give W1 four targets, share 98.06425062826763%, and W2 three targets, share 74.63624800688082%, **ex-post only**. The Exit R1 E2 SHORT summary scalar `23.950589292003308` bp is numerically close to narrative `23.95`; the manuscript copying hypothesis remains **UNKNOWN**. These are summary-level cross-checks, not event replay. Assumed STRESS44 `24+8+12=44 bp` is verified from frozen report definitions; actual exchange transaction costs remain UNKNOWN.

## 3. Exact-source forensic findings and terminal rationale

| ID | Severity | Frozen R4 claim | Exact independently observed evidence | Required disposition |
|---|---|---|---|---|
| **B01 — review-finding citation mapping** | **HIGH (documentary provenance acceptance blocker)** | R4 MD **line 85** cites prior R3 reviewer `7750b69...#L120-L125` as Finding 2 on causal nonexistence; **line 106** cites `#L126-L131` for cohort Finding 2; **line 127** cites `#L133-L137` and **line 134** cites `#L138-L141` for Finding 3. | Actual *frozen* independent R3 review is **135 populated lines plus trailing newline**. **Finding 2 is lines 109–115** (specific causal claim at 111 and cohort at 113). **Finding 3 is lines 117–123** (signed typo at 119, six-count ambiguity at 121). Lines 120–125 do not contain the alleged Finding 2; lines 126–131 are terminal discussion; lines 137–141 do **not exist**. These are not verifiable source citations in an exact-line provenance closure. | A versioned author-side citation correction must replace the four wrong spans with correct immutable R3 reviewer path/SHA/line spans, without changing the R3 evidence or numerical conclusions. |
| **B02 — wrong JSON cell field line** | **MEDIUM (documentary traceability defect)** | R4 MD **line 129** says R3 crosswalk JSON **line 697** contains `"correct_display_rounded_2dec": -0.26`. | Frozen R3 JSON **line 697** is `"h18_machine_field_path": null` for a different cell (W2 2021 H1). The correct W2 2021 delta cell **#26 starts at line 726** and has `"correct_display_rounded_2dec": -0.26` at **line 737**. The numerical `−0.26` is indeed correct; it is the **source line citation** that is false. | Correct attribution to `c7d68cf...:V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json#L726-L744`, specifically `#L737`. |
| **N01 — bounded reviewer exclusivity** | **LOW / qualification, not independently a blocker** | R4 MD line 72 refers to “the only legitimate independent review of R3.” | This audit recovered and verified review commit `7750b69...` and found no attributed prior R3 pass in the scoped artifacts. It cannot rule out all external reviews or authenticate all human/model authorship. | Controller should construe this as “the only attributable independent R3 review established in the scoped evidence” and preserve historical anonymous status as UNVERIFIED. |

**Severity separation:** This R4 response repaired the scientific assertions and numeric typo *in substance*. The failures above do **not** demonstrate a faulty corrected H18 number, a trading-account defect, or a false new profitability estimate. Nevertheless, R4's purpose is **exact-SHA semantic/provenance closure** and Stage A expressly requires accurate source file/line tracing. Publishing `REVIEW_PASS` over demonstrably wrong or nonexistent source spans would silently waive that provenance requirement. Hence terminal **`REVIEW_FAIL`**, narrowly on attribution/citation integrity.

## 4. Recommended finite, non-destructive next gate

The Controller may separately authorize **one bounded R4 citation-repair sidecar** with just (i) corrected independent R3 reviewer citations in R4 lines 85, 106, 127, 134; (ii) corrected R3 JSON line anchor in R4 line 129; (iii) optional scope tightening of the “only legitimate reviewer” phrase. An independent reviewer then checks that new, *separately frozen* SHA and the one-file diff. **Do not modify** this frozen Stage A document, R3/R2, raw results, scientific code, CI, or protected source data under this Stage B authority. Do not run additional historical PnL or introduce a new strategy test to fix mere provenance citations.

**Authority retained:** `R4_SEMANTIC_CORRECTIONS_ACCEPTED_SUBSCOPE`; **`P1C_R4_TERMINAL_REVIEW_FAIL`** pending Controller's narrow new grant. Original independent R3 remains `REVIEW_FAIL`; its 42-cell numeric sub-PASS is intact. This Stage B review is not Controller L2 acceptance.

## 5. Execution truth and explicit exclusions

Read on pinned GitHub refs: Controller L2 authorization and both dispatch prompts; Stage A by exact commit SHA and exact blob SHA, plus one-file commit/diff; original R3 MD and JSON; independent R3 report; frozen H18/Exit report and **summary** JSONs; failed R2 Markdown (for identity). Inspected only summary-level statistical fields of machine JSONs; no event-level arrays or unprotected market data were evaluated for this review.

Performed: exact Git object and identity checks; line-by-line documentary comparisons; source citation-address tests; independently computed **four** annual paired-delta spot checks; checked source summary continuation/tail metrics and assumed friction arithmetic; queried Stage A Actions for existence (0 workflow runs under head SHA).

**Not performed:** complete fresh 42-cell recomputation, pytest/full-repo CI, source/historical strategy runner, underlying trade-level PnL replay, external data retrieval, holdout inspection, private data/account access, order placement, personal finance/account operation, merge, force-push or any write except this **one separately authorized new docs audit**. The absence of Stage A CI is `NOT_RUN`, not `PASS`.

**Final reviewer verdict:** `REVIEW_FAIL` strictly for remaining exact-line provenance issues. **No Alpha/TESTNET/LIVE grant.**
