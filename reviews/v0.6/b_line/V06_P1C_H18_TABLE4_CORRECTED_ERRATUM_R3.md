# Corrected Narrative Erratum R3 — P1C H18 Annual Table 4 Forensics

**Task ID:** `V06_P1C_R3_CORRECTED_H18_ERRATUM`  
**Dispatch SHA:** `feaf55386dfa20c125236533d28514a587bfcf0a`  
**Dispatch Authority:** Controller dispatch `prompts/v0.6/b_line/V06_P1C_R3_CORRECTED_ERRATUM_DISPATCH.md`  
**Adjudication Source:** Controller adjudication `reviews/v0.6/b_line/V06_P1C_H18_INDEPENDENT_REVIEW_FAIL_CONTROLLER_ADJUDICATION_R1.md`  
**Execution Base SHA:** `feaf55386dfa20c125236533d28514a587bfcf0a`  
**Isolated Branch:** `docs/v06-p1c-h18-erratum-r3-correction`  
**Executor:** Gemini NORMAL (bounded, docs-only forensics)  
**Reviewer Route:** Independent second reviewer: Codex Sol / ChatGPT-1 separate from original executor  
**Reviewer Gate Status:** `REVIEW_PENDING` (awaiting independent second audit; zero self-certification)  
**Terminal Decision:** `R3_ERRATUM_REVIEW_READY`  
**Strategic Release Verdict:** `RETAIN_ALPHA_NO_GO` / `TESTNET_LIVE_STRICTLY_PROHIBITED`  
**Historical Replay:** Strictly prohibited and not executed  

---

## 1. Executive Summary & Controller Adjudication Context

This document establishes the corrected **R3** forensic erratum for published **Table 4** ("Annual and Structural Breakdown (STRESS44)") of the Goal B H18 mechanism report (`docs/strategy_research/g2_goal_h18_mechanism_r1/H18_MECHANISM_EMPIRICAL_REPORT.md`, SHA `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`).

### Formal Controller Adjudication Record
On 2026-10-13, the B-line Controller issued formal adjudication `reviews/v0.6/b_line/V06_P1C_H18_INDEPENDENT_REVIEW_FAIL_CONTROLLER_ADJUDICATION_R1.md` accepting the independent reviewer finding of **REVIEW_FAIL** against the previous erratum deliverable (R2, commit `b4f24c763895c97a0c304dc422db76a73761251d`). The R2 artifact remains an immutable, failed historical submission (`REVIEW_FAIL_ACCEPTED / P1C_R2_NOT_ACCEPTED / CORRECTION_R3_REQUIRED`).

### Disposition of the Eight Controller / Reviewer Objections in R3

1. **STRESS44 Cost Model Definition & Units (HIGH):** Corrected from R2's erroneous "4.4bp taker / 8.8bp round-trip" to the authoritatively published definition in H18: 44 bp round-trip assumed research proxy (24 bp assumed fees + 8 bp spread + 12 bp slippage, or 22 bp per one-way leg). Discrepancies between account returns are strictly labelled in **percentage points (pp)**, not percent (%). These figures represent assumed research parameters, not measured exchange fills or personal fees.
2. **Markdown vs. JSON Status Alignment on 2023 Deltas (HIGH):** In R2, Markdown erroneously marked W1 2023 (+56.89 narrative vs +56.88 canonical) and W2 2023 (+27.38 narrative vs +27.39 canonical) as `MATCH_ROUNDED` despite the JSON marking both `MISMATCH`. In this R3 deliverable, both Markdown and JSON strictly align: both 2023 narrative deltas are explicitly flagged **incorrect in the original narrative** and classified as `DIFFER` (`ROUNDING_DISCREPANCY_NARRATIVE_INCORRECT`).
3. **Cross-Source Evidence Limitation (HIGH):** Cross-source machine agreement between H18 diagnostic machine results and Exit R1 canonical machine results is strictly limited to **six annual event counts + six paired annual deltas** within declared numeric tolerance ($\le 1\times 10^{-10}$). The remaining 30 H18 machine cells are explicitly `null` (unpopulated in H18). R3 strictly disclaims whole-ledger integrity, all-timestamp identities, zero historical defect, or independent end-to-end replay.
4. **W2 2021/2022 Cohort Partition Mismatch (HIGH):** The narrative published $N=(14, 17)$ for 2021 and 2022 whereas canonical machine results partition UTC calendar years as $N=(10, 21)$ (both sum to 31 events; 2021-2023 total is 55 events). R3 explicitly classifies the causal origin of this mismatch as **UNKNOWN**. Count differences cannot identify shifted events; Exit accepted-ID date spans cannot be attributed to H18 accepted IDs or receiver clock.
5. **Timestamp Source Limitation (MEDIUM):** Exit R1, not H18, contains accepted event identifiers encoding 2021 ten events (between 2021-04-26T01:45:00Z and 2021-12-23T20:45:00Z) and 2022 twenty-one events (between 2022-01-13T18:45:00Z and 2022-12-11T21:00:00Z). These are source transaction timestamps, not receiver-known-at evidence.
6. **W1 2021 Delta & H1 Means Causality (HIGH):** Factual numeric differences are recorded: W1 2021 Delta (+23.95 narrative vs +2.94 canonical) and H1 mean (+128.53 narrative vs +107.52 canonical). R3 confirms that observed arithmetic coincidences ($104.58 + 23.95 = 128.53$ and Exit E2 SHORT scalar $23.950589$ bp) support an explanatory hypothesis, but do NOT prove that the author copied a value. The manuscript drafting provenance is classified as **UNKNOWN**.
7. **Continuation & Tail Evidence Boundary (HIGH):** The adverse 12–18h continuation rate of $26/56 = 46.43\%$ is classified strictly as **DESCRIPTIVE_ONLY**; no inference regarding 50/50 probability, lack of statistical edge, or hypothesis test significance is asserted. Similarly, the 4 W1 ($98.064\%$) and 3 W2 ($74.636\%$) right-tail target winners represent **ex-post retrospective attribution only**, and do NOT constitute an actionable ex-ante trade signal.
8. **Account Return Units (MEDIUM):** Account returns are percentages (%); differences between two account returns are strictly labelled as **percentage points (pp)**.

---

## 2. Immutable Source Artifact Identities

All analyses and data points in this deliverable are pinned to the following immutable source artifacts:

| Source Role | Frozen Git Commit SHA | Git Blob SHA | Exact Repository File Path | Status / Scope |
|---|---|---|---|---|
| **Task Dispatch** | `feaf55386dfa20c125236533d28514a587bfcf0a` | `09106e22b5efc2913ad80c4d142a092bff168fd9` | `prompts/v0.6/b_line/V06_P1C_R3_CORRECTED_ERRATUM_DISPATCH.md` | Controller Dispatch Authority |
| **Controller Adjudication** | `feaf55386dfa20c125236533d28514a587bfcf0a` | `5c4aa09beacedf7706710a091cc7f5a93647dd0f` | `reviews/v0.6/b_line/V06_P1C_H18_INDEPENDENT_REVIEW_FAIL_CONTROLLER_ADJUDICATION_R1.md` | REVIEW_FAIL Adjudication Authority |
| **R2 Erratum Markdown** | `b4f24c763895c97a0c304dc422db76a73761251d` | `78da392fc16ff12abd0284bd91e77b7b9e2c9590` | `reviews/v0.6/b_line/V06_P1C_H18_YEARLY_TABLE4_IMMUTABLE_ERRATUM_R2.md` | REVIEW_FAIL (Immutable Historical) |
| **R2 Crosswalk JSON** | `b4f24c763895c97a0c304dc422db76a73761251d` | `0cfb9fb00c64d4352e3f9005f25a257b3006a39d` | `reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CROSSWALK_R2.json` | REVIEW_FAIL (Immutable Historical) |
| **H18 Research Report** | `397a62c1a0fbd6ad14a569a5be0058b1f684f08e` | `4d0601f29e8bdf3846107e079d6a82322a00adf6` | `docs/strategy_research/g2_goal_h18_mechanism_r1/H18_MECHANISM_EMPIRICAL_REPORT.md` | Frozen Published Report |
| **H18 Diagnostic Machine** | `397a62c1a0fbd6ad14a569a5be0058b1f684f08e` | `ebd28897737728872390451ff5162e6cc43ae204` | `evidence/v0.6/b_line/g2_goal_h18_mechanism_r1/H18_MECHANISM_DIAGNOSTIC_RESULTS.json` | Frozen Machine Summary (12 slots) |
| **Exit R1 Research Report** | `55ac4c631c69f6edbd275462ad23e4486b9782ed` | `772b4cb5e6eeb19778849305dc3398b1e1de5ecb` | `docs/strategy_research/g2_exit_horizon_r1/EXIT_R1_EMPIRICAL_REPORT.md` | Frozen Canonical Report |
| **Exit R1 Machine Results** | `55ac4c631c69f6edbd275462ad23e4486b9782ed` | `c264831f44ae3e93df498eae8ea55f4b9cb631ff` | `evidence/v0.6/b_line/g2_exit_horizon_r1/EXIT_R1_RESULTS.json` | Frozen Canonical Machine (42 slots) |

> [!IMPORTANT]
> No raw market feeds, historical order logs, private keys, trading runners, or protected data suites (H39/H40/H41/Forward/Final Holdout) were loaded, read, or executed.

---

## 3. Published Narrative Table 4 (Original as Published in H18 Report)

Reproduced verbatim from `H18_MECHANISM_EMPIRICAL_REPORT.md` (SHA `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`):

| Candidate | Year | $N$ | E0 Mean (bp) | H1 Mean (bp) | H2 Mean (bp) | $\Delta$ H1-E0 (bp) | Account E0 Ret | Account H1 Ret |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **W1_C04** | 2021 | 8 | +104.58 | +128.53 | +91.56 | +23.95 | +4.95% | +5.72% |
| **W1_C04** | 2022 | 10 | -11.92 | +20.25 | +48.83 | +32.17 | +1.37% | +3.85% |
| **W1_C04** | 2023 | 16 | -21.03 | **+35.86** | +17.36 | **+56.89** | -2.93% | **+4.75%** |
| **W2_C05** | 2021 | 14 | +92.42 | +117.43 | +104.53 | +25.01 | +8.23% | +10.15% |
| **W2_C05** | 2022 | 17 | +35.84 | +56.59 | +44.52 | +20.75 | +10.98% | +14.37% |
| **W2_C05** | 2023 | 24 | -45.49 | **-18.11** | -24.98 | **+27.38** | -8.40% | **-3.23%** |

---

## 4. Corrected Table 4 (Verbatim from Controller Adjudication)

Reproduced verbatim from Controller adjudication `reviews/v0.6/b_line/V06_P1C_H18_INDEPENDENT_REVIEW_FAIL_CONTROLLER_ADJUDICATION_R1.md` under **STRESS44** friction (44 bp round-trip assumed research proxy; units in headings):

| Candidate | Year | N | E0 bp | H1 bp | H2 bp | H1−E0 bp | Account E0 % | Account H1 % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W1_C04 | 2021 | 8 | 104.58 | 107.52 | 91.56 | 2.94 | 7.50 | 7.72 |
| W1_C04 | 2022 | 10 | -11.92 | 21.68 | 48.83 | 33.61 | -1.05 | 1.83 |
| W1_C04 | 2023 | 16 | -21.03 | 35.86 | 17.36 | 56.88 | -2.93 | 4.75 |
| W2_C05 | 2021 | 10 | 131.22 | 130.96 | 182.14 | -0.26 | 12.18 | 12.14 |
| W2_C05 | 2022 | 21 | 39.31 | 66.89 | 28.30 | 27.58 | 6.74 | 11.44 |
| W2_C05 | 2023 | 24 | -45.49 | -18.11 | -24.98 | 27.39 | -8.40 | -3.23 |

> [!NOTE]
> **Computational Rule:** Each displayed `H1−E0` value is computed directly from unrounded source means before rounding once to 2 decimals at the end (e.g. W1 2022: $21.681892 - (-11.923554) = 33.605446 \to 33.61$ bp; W1 2023: $35.857119 - (-21.026000) = 56.883120 \to 56.88$ bp; W2 2023: $-18.106408 - (-45.493320) = 27.386912 \to 27.39$ bp).
> Both W1 2023 (+56.88 bp vs narrative +56.89 bp) and W2 2023 (+27.39 bp vs narrative +27.38 bp) are explicitly flagged **incorrect in the original narrative**.

---

## 5. Exhaustive 42-Cell Comparative Crosswalk

The 42 candidate $\times$ year $\times$ metric cells are evaluated below. Exactly **24 cells differ** from the original narrative and **18 cells match**.
Every status, deviation, and classification strictly mirrors `reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json`.

| # | Cand | Year | Metric | Unit | Original Narrative | Canonical Unrounded | Correct Display Rounded | Deviation | Dev Unit | Status | Classification | H18 Machine Value | Notes & Analysis |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|---|---|
| 1 | W1_C04 | 2021 | N | events | 8 | 8 | 8 | 0 | events | `MATCH` | `MATCH_EXACT` | 8 | Exact match (8 events). Reconciled across Exit R1 and H18 machine ledgers. |
| 2 | W1_C04 | 2021 | E0 | bp | +104.58 | 104.576321 | +104.58 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (104.576321) rounded to 2 decimals (104.58). |
| 3 | W1_C04 | 2021 | H1 | bp | +128.53 | 107.520594 | +107.52 | +21.01 | bp | `DIFFER` | `NUMERIC_MISMATCH_MANUSCRIPT_CAUSE_UNKNOWN` | — | Narrative published +128.53 bp vs canonical +107.52 bp (raw 107.520594 bp). Factual numeric difference. 104.58 + 23.95 = 128.53 bp is an observed arithmetic possibility, but manuscript cause is UNKNOWN. |
| 4 | W1_C04 | 2021 | H2 | bp | +91.56 | 91.557676 | +91.56 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (91.557676) rounded to 2 decimals (91.56). |
| 5 | W1_C04 | 2021 | H1-E0 | bp | +23.95 | 2.944273 | +2.94 | +21.01 | bp | `DIFFER` | `NUMERIC_MISMATCH_MANUSCRIPT_CAUSE_UNKNOWN` | 2.944273 | Narrative published +23.95 bp vs canonical/machine +2.94 bp (raw 2.944273 bp). Unrounded delta matches H18 machine (2.944273 bp) within 1e-10. Similarity to Exit E2 SHORT scalar (23.950589 bp) is an explanatory hypothesis only; manuscript cause is UNKNOWN. |
| 6 | W1_C04 | 2021 | Account_E0 | % | +4.95 | 7.497365 | +7.5 | -2.55 | pp | `DIFFER` | `ACCOUNT_RETURN_MISMATCH_CAUSE_UNKNOWN` | — | Narrative published 4.95% vs canonical cash return 7.50% (raw 7.497365%). Reporting basis ungrounded in machine artifact; manuscript cause UNKNOWN. |
| 7 | W1_C04 | 2021 | Account_H1 | % | +5.72 | 7.718307 | +7.72 | -2.00 | pp | `DIFFER` | `ACCOUNT_RETURN_MISMATCH_CAUSE_UNKNOWN` | — | Narrative published 5.72% vs canonical cash return 7.72% (raw 7.718307%). Reporting basis ungrounded in machine artifact; manuscript cause UNKNOWN. |
| 8 | W1_C04 | 2022 | N | events | 10 | 10 | 10 | 0 | events | `MATCH` | `MATCH_EXACT` | 10 | Exact match (10 events). Reconciled across Exit R1 and H18 machine ledgers. |
| 9 | W1_C04 | 2022 | E0 | bp | -11.92 | -11.923554 | -11.92 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-11.923554) rounded to 2 decimals (-11.92). |
| 10 | W1_C04 | 2022 | H1 | bp | +20.25 | 21.681892 | +21.68 | -1.43 | bp | `DIFFER` | `NUMERIC_MISMATCH_MANUSCRIPT_CAUSE_UNKNOWN` | — | Narrative published +20.25 bp vs canonical +21.68 bp (raw 21.681892 bp). Factual numeric difference; manuscript cause UNKNOWN. |
| 11 | W1_C04 | 2022 | H2 | bp | +48.83 | 48.832740 | +48.83 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (48.832740) rounded to 2 decimals (48.83). |
| 12 | W1_C04 | 2022 | H1-E0 | bp | +32.17 | 33.605446 | +33.61 | -1.44 | bp | `DIFFER` | `NUMERIC_MISMATCH_MANUSCRIPT_CAUSE_UNKNOWN` | 33.605446 | Narrative published +32.17 bp vs canonical/machine +33.61 bp (raw 33.605446 bp). Matches H18 machine exactly. Factual numeric difference; manuscript cause UNKNOWN. |
| 13 | W1_C04 | 2022 | Account_E0 | % | +1.37 | -1.045077 | -1.05 | +2.42 | pp | `DIFFER` | `ACCOUNT_RETURN_MISMATCH_CAUSE_UNKNOWN` | — | Narrative published 1.37% vs canonical cash return -1.05% (raw -1.045077%). Manuscript cause UNKNOWN. |
| 14 | W1_C04 | 2022 | Account_H1 | % | +3.85 | 1.830864 | +1.83 | +2.02 | pp | `DIFFER` | `ACCOUNT_RETURN_MISMATCH_CAUSE_UNKNOWN` | — | Narrative published 3.85% vs canonical cash return 1.83% (raw 1.830864%). Manuscript cause UNKNOWN. |
| 15 | W1_C04 | 2023 | N | events | 16 | 16 | 16 | 0 | events | `MATCH` | `MATCH_EXACT` | 16 | Exact match (16 events). Reconciled across Exit R1 and H18 machine ledgers. |
| 16 | W1_C04 | 2023 | E0 | bp | -21.03 | -21.026000 | -21.03 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-21.026000) rounded to 2 decimals (-21.03). |
| 17 | W1_C04 | 2023 | H1 | bp | +35.86 | 35.857119 | +35.86 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (35.857119) rounded to 2 decimals (35.86). |
| 18 | W1_C04 | 2023 | H2 | bp | +17.36 | 17.358785 | +17.36 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (17.358785) rounded to 2 decimals (17.36). |
| 19 | W1_C04 | 2023 | H1-E0 | bp | +56.89 | 56.883120 | +56.88 | +0.01 | bp | `DIFFER` | `ROUNDING_DISCREPANCY_NARRATIVE_INCORRECT` | 56.883120 | Narrative published +56.89 bp vs correct display-rounded +56.88 bp (unrounded 56.883120 bp). Unrounded delta matches H18 machine (56.883120 bp) within 1e-10. Original narrative rounding was incorrect. |
| 20 | W1_C04 | 2023 | Account_E0 | % | -2.93 | -2.934050 | -2.93 | +0.00 | pp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-2.934050) rounded to 2 decimals (-2.93). |
| 21 | W1_C04 | 2023 | Account_H1 | % | +4.75 | 4.754757 | +4.75 | +0.00 | pp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (4.754757) rounded to 2 decimals (4.75). |
| 22 | W2_C05 | 2021 | N | events | 14 | 10 | 10 | 4 | events | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | 10 | Narrative published N=14 vs canonical N=10. Sum of 2021+2022 events equals 31 in both (14+17 vs 10+21). Causal origin of partition mismatch is UNKNOWN. Event difference cannot identify shifted events; Exit accepted IDs date spans cannot be attributed to H18 accepted IDs or receiver clock. |
| 23 | W2_C05 | 2021 | E0 | bp | +92.42 | 131.216814 | +131.22 | -38.80 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 92.42 vs canonical 131.22 (raw 131.216814). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 24 | W2_C05 | 2021 | H1 | bp | +117.43 | 130.959167 | +130.96 | -13.53 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 117.43 vs canonical 130.96 (raw 130.959167). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 25 | W2_C05 | 2021 | H2 | bp | +104.53 | 182.144299 | +182.14 | -77.61 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 104.53 vs canonical 182.14 (raw 182.144299). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 26 | W2_C05 | 2021 | H1-E0 | bp | +25.01 | -0.257648 | -0.26 | +25.27 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | -0.257648 | Narrative published +25.01 bp vs canonical +-0.26 bp (raw -0.257648 bp). Calculated over non-canonical cohort. Canonical paired delta matches H18 machine (-0.257648 bp) within 1e-10. Manuscript origin UNKNOWN. |
| 27 | W2_C05 | 2021 | Account_E0 | % | +8.23 | 12.176616 | +12.18 | -3.95 | pp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 8.23 vs canonical 12.18 (raw 12.176616). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 28 | W2_C05 | 2021 | Account_H1 | % | +10.15 | 12.135737 | +12.14 | -1.99 | pp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 10.15 vs canonical 12.14 (raw 12.135737). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 29 | W2_C05 | 2022 | N | events | 17 | 21 | 21 | -4 | events | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | 21 | Narrative published N=17 vs canonical N=21. Sum of 2021+2022 events equals 31 in both (14+17 vs 10+21). Causal origin of partition mismatch is UNKNOWN. Event difference cannot identify shifted events; Exit accepted IDs date spans cannot be attributed to H18 accepted IDs or receiver clock. |
| 30 | W2_C05 | 2022 | E0 | bp | +35.84 | 39.305493 | +39.31 | -3.47 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 35.84 vs canonical 39.31 (raw 39.305493). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 31 | W2_C05 | 2022 | H1 | bp | +56.59 | 66.885160 | +66.89 | -10.30 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 56.59 vs canonical 66.89 (raw 66.885160). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 32 | W2_C05 | 2022 | H2 | bp | +44.52 | 28.302973 | +28.3 | +16.22 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 44.52 vs canonical 28.30 (raw 28.302973). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 33 | W2_C05 | 2022 | H1-E0 | bp | +20.75 | 27.579667 | +27.58 | -6.83 | bp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | 27.579667 | Narrative published +20.75 bp vs canonical +27.58 bp (raw 27.579667 bp). Calculated over non-canonical cohort. Canonical paired delta matches H18 machine (27.579667 bp) within 1e-10. Manuscript origin UNKNOWN. |
| 34 | W2_C05 | 2022 | Account_E0 | % | +10.98 | 6.744435 | +6.74 | +4.24 | pp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 10.98 vs canonical 6.74 (raw 6.744435). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 35 | W2_C05 | 2022 | Account_H1 | % | +14.37 | 11.438788 | +11.44 | +2.93 | pp | `DIFFER` | `COHORT_PARTITION_MISMATCH_ORIGIN_UNKNOWN` | — | Narrative published 14.37 vs canonical 11.44 (raw 11.438788). Calculated over non-canonical cohort. Manuscript origin UNKNOWN. |
| 36 | W2_C05 | 2023 | N | events | 24 | 24 | 24 | 0 | events | `MATCH` | `MATCH_EXACT` | 24 | Exact match (24 events). Reconciled across Exit R1 and H18 machine ledgers. |
| 37 | W2_C05 | 2023 | E0 | bp | -45.49 | -45.493320 | -45.49 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-45.493320) rounded to 2 decimals (-45.49). |
| 38 | W2_C05 | 2023 | H1 | bp | -18.11 | -18.106408 | -18.11 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-18.106408) rounded to 2 decimals (-18.11). |
| 39 | W2_C05 | 2023 | H2 | bp | -24.98 | -24.984239 | -24.98 | +0.00 | bp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-24.984239) rounded to 2 decimals (-24.98). |
| 40 | W2_C05 | 2023 | H1-E0 | bp | +27.38 | 27.386912 | +27.39 | -0.01 | bp | `DIFFER` | `ROUNDING_DISCREPANCY_NARRATIVE_INCORRECT` | 27.386912 | Narrative published +27.38 bp vs correct display-rounded +27.39 bp (unrounded 27.386912 bp). Unrounded delta matches H18 machine (27.386912 bp) within 1e-10. Original narrative rounding was incorrect. |
| 41 | W2_C05 | 2023 | Account_E0 | % | -8.4 | -8.400670 | -8.4 | +0.00 | pp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-8.400670) rounded to 2 decimals (-8.40). |
| 42 | W2_C05 | 2023 | Account_H1 | % | -3.23 | -3.230744 | -3.23 | +0.00 | pp | `MATCH` | `MATCH_ROUNDED` | — | Narrative value matches unrounded canonical value (-3.230744) rounded to 2 decimals (-3.23). |

---

## 6. Discrepancy Reconciliation Summary

Across the 42 cells evaluated:

- **Total Cells Differing:** **24**
- **Total Cells Matching:** **18**

### Breakdown by Discrepancy Category
1. **Rounding Errors in Narrative (2 cells):** W1 2023 Delta (+56.89 narrative vs +56.88 canonical display; deviation +0.01 bp) and W2 2023 Delta (+27.38 narrative vs +27.39 canonical display; deviation -0.01 bp). Both are flagged as narrative errors; machine unrounded values match across both sources.
2. **Cohort Partition Mismatches (14 cells):** All 7 metrics for W2 in 2021 and all 7 metrics for W2 in 2022. Narrative drafted with $N=(14, 17)$ vs canonical $N=(10, 21)$ (sum = 31). Cause is **UNKNOWN**. Date spans in Exit R1 cannot identify shifted events or clock discrepancies.
3. **Numeric Discrepancies (4 cells):** W1 2021 Delta (+23.95 vs +2.94 bp), W1 2021 H1 (+128.53 vs +107.52 bp), W1 2022 Delta (+32.17 vs +33.61 bp), W1 2022 H1 (+20.25 vs +21.68 bp). Cause is **UNKNOWN**.
4. **Account Return Discrepancies (4 cells):** W1 2021 E0 (+4.95% vs +7.50%), W1 2021 H1 (+5.72% vs +7.72%), W1 2022 E0 (+1.37% vs -1.05%), W1 2022 H1 (+3.85% vs +1.83%). Deviation units are **pp**. Cause is **UNKNOWN**.
5. **Exact / Rounded Matches (18 cells):** All 6 event counts match Exit R1 ($N=8, 10, 16, 10, 21, 24$). E0, H1, H2, and Account returns match in 2023 for both candidates, and E0/H2 match in 2021 and 2022 for W1.

---

## 7. Mechanistic Findings & Evidence Boundary

### 1. Right-Tail Target Winner Concentration
- **W1_C04:** 4 target winners account for **98.064%** of net delta (+1,245.16 bp of +1,269.74 bp).
- **W2_C05:** 3 target winners account for **74.636%** of net delta (+920.92 bp of +1,233.88 bp).
> [!IMPORTANT]
> **Evidence Boundary:** This concentration is strictly an **ex-post retrospective attribution**, NOT an ex-ante trade signal or classifier. No causal entry-time feature distinguishes these 7 winners from the remaining 49 trades without lookahead bias.

### 2. Adverse Continuation Rate
- Across the 56 baseline positions reaching the 12h horizon: **26 out of 56 positions (46.43%)** experienced adverse continuation between 12h and 18h (W1: 11/20 = 55.0%; W2: 15/36 = 41.67%).
> [!IMPORTANT]
> **Statistical Claim Boundary:** The 26/56 (46.43%) continuation proportion is **DESCRIPTIVE_ONLY**. No assertion of a 50/50 probability, lack of edge, or hypothesis testing significance is made.

### 3. Strategic Release Verdict
- **`G2_ALPHA_NO_GO` / `TESTNET_LIVE_STRICTLY_PROHIBITED`:** Neither candidate is approved for Alpha promotion or execution staging.
- **No Trial Unlock:** This erratum is strictly documentary. No historical re-scoring, parameter search, or new market trials are unlocked.

---

## 8. Governance, Reviewer Route & Delivery Receipts

### Reviewer Route & Second Independent Audit
- **Executor:** Gemini NORMAL (bounded docs-only forensics).
- **Independent Second Reviewer Requirement:** Codex Sol / ChatGPT-1 separate from executor.
- **Reviewer Gate Status:** `REVIEW_PENDING` (no self-certification; awaiting separate independent audit).
- **Terminal Decision:** `R3_ERRATUM_REVIEW_READY`

### Write Allowlist Compliance Affirmation
Only the two authorized paths are created on branch `docs/v06-p1c-h18-erratum-r3-correction`:
1. `reviews/v0.6/b_line/V06_P1C_H18_TABLE4_CORRECTED_ERRATUM_R3.md`
2. `reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json`

### CI Receipts & Inherited H41 Ruff Notice
- GitHub Actions CI (`.github/workflows/ci.yml`) explicitly ignores documentation paths under `reviews/**` (`paths-ignore`), properly skipping CI runs on doc-only deliverables.
- Legacy Ruff lint debt in `evidence/v0.5/h41/...` (6 errors in protected historical artifacts) remains untouched and unbypassed, preserving strict evidence integrity.
