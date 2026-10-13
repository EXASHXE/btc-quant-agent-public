# P1C-R4 — Five-Source-Citation Precision Repair Sidecar

**Task ID:** `V06_P1C_R4_FIVE_CITATIONS_REPAIR`  
**Controller Authority:** `AUTHORIZE_R4_FIVE_CITATION_REPAIR_ONLY`, authorized in Controller dispatch commit `a2b81f8b02d76cdb7f10edb393403a5b7472a9c4`, file `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_CONTROLLER_AUTHORIZATION_R1.md` (Git blob `22a827dd69afaf6af7ec96dc81763767818410ec`)  
**Base Commit:** `a2b81f8b02d76cdb7f10edb393403a5b7472a9c4`  
**Isolated Branch:** `docs/v06-p1c-r4-five-citations-repair-r1`  
**Author / Executor:** Gemini NORMAL (bounded docs-only corrective author; **not** the independent reviewer)  
**Author Role & Separation of Duties:** Authoring narrow citation-repair sidecar only; strictly prohibited from self-certifying or issuing independent audit verdicts  
**Reviewer Gate Status:** `R4_REPAIR_INDEPENDENT_REVIEW_PENDING` (independent review by Codex Sol High or ChatGPT-1 pending)  
**Controller Gate Status:** `CONTROLLER_L2_PENDING` (final Controller L2 adjudication pending independent verification)  
**Terminal Author Verdict:** `FIVE_CITATION_SIDECAR_READY_FOR_INDEPENDENT_REVIEW`  
**Global Strategic Invariant:** `G2_ALPHA_NO_GO`, `G4_TESTNET_NOT_AUTHORIZED`, `LIVE_NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_NONE`  

---

## 1. Executive Summary & Purpose of Repair Sidecar

This document serves as the bounded, surgical Stage A precision repair sidecar for the P1C-R4 documentary erratum series.

In the preceding Stage B independent terminal audit (`b1f211b16be78bd1a73f004f5134f9e27f1a85a2`, `reviews/v0.6/b_line/V06_P1C_R4_INDEPENDENT_TERMINAL_AUDIT_R1.md`), the independent auditor issued the following evaluation:
1. **Substantive Semantic Sub-Verdict:** **`PASS_WITHIN_BOUNDED_DOCUMENTARY_SCOPE`** (confirming that the causal impossibility prose replacement, cohort partition rationale clarification, signed prose typo correction, event count agreement qualification, and numerical coincidence distinction were valid and accurate in substance).
2. **Terminal Overall Verdict:** **`REVIEW_FAIL`**, strictly due to remaining exact-line provenance issues:
   - Four source line citations to the frozen R3 independent review (`7750b69...`) pointed to incorrect line spans (Finding B01).
   - One line citation to the frozen R3 crosswalk JSON (`c7d68cf...`) cited line 697 rather than line 737 for cell #26 (Finding B02).
   - A wording concern regarding reviewer exclusivity on R4 line 72 (Finding N01).

Under Controller authorization `AUTHORIZE_R4_FIVE_CITATION_REPAIR_ONLY`, this sidecar provides the exact line-level corrections for precisely the five source citations and records the single allowed evidence-scope qualification, without mutating frozen historical source files, altering code/tests, or unlocking downstream execution gates.

---

## 2. Immutable Source & Historical Audit Identities

All source documents, historical errata, and audit reports are preserved byte-immutable under exact Git object hashes:

| Role / Artifact | Git Commit SHA | File Path | Git Blob SHA | Status in this Repair |
|---|---|---|---|---|
| **Controller Authorization** | `a2b81f8b02d76cdb7f10edb393403a5b7472a9c4` | `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_CONTROLLER_AUTHORIZATION_R1.md` | `22a827dd69afaf6af7ec96dc81763767818410ec` | Immutable Authority |
| **Stage A Repair Prompt** | `a2b81f8b02d76cdb7f10edb393403a5b7472a9c4` | `prompts/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_REPAIR_EXECUTION_R1.md` | `8226c21d09abb38a3ee25c213148bfd7b0f9758c` | Immutable Prompt |
| **Stage B Review Prompt** | `a2b81f8b02d76cdb7f10edb393403a5b7472a9c4` | `prompts/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_INDEPENDENT_REVIEW_R1.md` | `73043f202e5ebd327c30379fed4234b45d667e16` | Immutable Prompt |
| **Stage A R4 Manuscript** | `3a5c071c1e25a11d8047105657f8df6755dc3aba` | `reviews/v0.6/b_line/V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md` | `9d3857de60a622abf0a277271d249e9828940f04` | Immutable (Clarified by this Repair) |
| **Failed Stage B R4 Audit** | `b1f211b16be78bd1a73f004f5134f9e27f1a85a2` | `reviews/v0.6/b_line/V06_P1C_R4_INDEPENDENT_TERMINAL_AUDIT_R1.md` | `e3e937378ca6317f2dd74f428a3aaf9987c2da81` | Immutable Historical Audit (`REVIEW_FAIL`) |
| **R3 Independent Review** | `7750b69a87dcfb392bdfc8d20e7b7f174276452e` | `reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md` | `d2f2b366dd5af114981cac98604f09d60c5e4981` | Immutable Source Audit |
| **R3 Crosswalk JSON** | `c7d68cfd3f97c27723a48fb4722dd39ddc4a1290` | `reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json` | `3d9e4a0c1f7116eb03edd793b5f670b5002ca167` | Immutable Machine Crosswalk |
| **P1C-R3 Markdown Erratum** | `c7d68cfd3f97c27723a48fb4722dd39ddc4a1290` | `reviews/v0.6/b_line/V06_P1C_H18_TABLE4_CORRECTED_ERRATUM_R3.md` | `f7f1be23defc6a3d13b8f4576d9952ffdcd19cb9` | Immutable R3 Erratum |
| **Historical Failed R2 Erratum** | `b4f24c763895c97a0c304dc422db76a73761251d` | `reviews/v0.6/b_line/V06_P1C_H18_YEARLY_TABLE4_IMMUTABLE_ERRATUM_R2.md` | `78da392fc16ff12abd0284bd91e77b7b9e2c9590` | Immutable Historical Fail |

> [!IMPORTANT]
> **Declaration of Narrow Supersession Scope:**  
> This repair sidecar supersedes **only** the five identified source line citations in the Stage A R4 manuscript (`3a5c071...`) and applies the single allowed scope qualification to R4 line 72. All earlier documents remain byte-for-byte immutable.

---

## 3. Surgical Correction Table: The Five Verified Source-Line Citations

The table below provides the precise line-level mapping correcting all five citation defects:

| Item # | Stage A R4 Location (`3a5c071...`) | Erroneous Anchor in R4 | Target Source Document & Exact Commit SHA | Verified Correct Source Anchor | Quoted Source Snippet Demonstrating Correct Citation |
|---|---|---|---|---|---|
| **1** | `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L85` | `7750b69...#L120-L125` | `7750b69a87dcfb392bdfc8d20e7b7f174276452e`<br>`reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md` | **`#L109-L115`**<br>(specifically **`#L111`**) | `"In R3 Markdown line 166, despite correctly labelling right-tail concentration as ex-post, the text asserts: “No causal entry-time feature distinguishes these 7 winners from the remaining 49 trades without lookahead bias.” The available retrospective concentration table does not establish the nonexistence of an ex-ante predictor. The valid weaker claim is that no such feature has been established by this analysis."` |
| **2** | `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L106` | `7750b69...#L126-L131` | `7750b69a87dcfb392bdfc8d20e7b7f174276452e`<br>`reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md` | **`#L109-L115`**<br>(specifically **`#L113`**) | `"R3 per-cell notes at lines 121–133, including W2 2021/2022 mean and account-return cells, repeatedly assert “Calculated over non-canonical cohort.” The original N partitions differ, but no manuscript construction log or underlying narrative cohort identity is available to prove that these exact numbers were calculated from a specific alternate cohort. R3 section 6 (line 153) itself correctly says drafting/partition cause UNKNOWN. The source evidence establishes mismatch, not production mechanism. This does not invalidate the corrected numeric source values but materially overstates scientific and forensic certainty."` |
| **3** | `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L127` | `7750b69...#L133-L137` | `7750b69a87dcfb392bdfc8d20e7b7f174276452e`<br>`reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md` | **`#L117-L123`**<br>(specifically **`#L119`**) | `"R3 Markdown line 124, 42-cell table row #26 (W2_C05/2021 H1–E0) describes the correct negative figure as +-0.26 bp. The actual row's canonical column and JSON have −0.26 bp, so the table numeric correction remains correct, but the explanatory text is malformed."` |
| **4** | `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L134` | `7750b69...#L138-L141` | `7750b69a87dcfb392bdfc8d20e7b7f174276452e`<br>`reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md` | **`#L117-L123`**<br>(specifically **`#L121`**) | `"R3 Markdown line 156 under “Exact / Rounded Matches (18 cells)” says “All 6 event counts match Exit R1”. This is correct only for corrected machine-backed counts, not the original Table 4 (two W2 original annual counts differ). Explicitly qualify which layer is matching to avoid contradicting the 18/24 count."` |
| **5** | `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L129` | `c7d68cf...#L697` | `c7d68cfd3f97c27723a48fb4722dd39ddc4a1290`<br>`reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json` | **`#L737`**<br>(cell #26 span **`#L726-L744`**) | `"correct_display_rounded_2dec": -0.26,` |

---

## 4. Forensic Detail for the Five Source Citations

### 4.1 Citation 1: Causal Finding in R3 Independent Review
- **Stage A R4 Target:** `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L85`.
- **Erroneous Anchor:** `7750b69...#L120-L125`. (Lines 120–125 of the frozen R3 review discuss Finding 3 and disposition; they do not contain Finding 2 on causal claims).
- **Correct Verified Anchor:** `7750b69a87dcfb392bdfc8d20e7b7f174276452e:reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md#L109-L115`.
- **Target Assertion Line:** Line 111 contains the exact analysis addressing R3 Markdown line 166:
  ```markdown
  109: ### Finding 2 — HIGH / OBSERVED: R3 prose overstates causal impossibility and assumes a manuscript calculation mechanism
  110: 
  111: In R3 Markdown line 166, despite correctly labelling right-tail concentration as ex-post, the text asserts: “No causal entry-time feature distinguishes these 7 winners from the remaining 49 trades without lookahead bias.” The available retrospective concentration table does not establish the nonexistence of an ex-ante predictor. The valid weaker claim is that no such feature has been established by this analysis.
  ```

### 4.2 Citation 2: Cohort Finding in R3 Independent Review
- **Stage A R4 Target:** `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L106`.
- **Erroneous Anchor:** `7750b69...#L126-L131`. (Lines 126–131 of the frozen R3 review discuss Section E terminal decisions; they do not contain the cohort finding).
- **Correct Verified Anchor:** `7750b69a87dcfb392bdfc8d20e7b7f174276452e:reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md#L109-L115`.
- **Target Assertion Line:** Line 113 contains the exact analysis addressing R3 cell notes:
  ```markdown
  113: R3 per-cell notes at lines 121–133, including W2 2021/2022 mean and account-return cells, repeatedly assert “Calculated over non-canonical cohort.” The original N partitions differ, but no manuscript construction log or underlying narrative cohort identity is available to prove that these exact numbers were calculated from a specific alternate cohort. R3 section 6 (line 153) itself correctly says drafting/partition cause UNKNOWN. The source evidence establishes mismatch, not production mechanism. This does not invalidate the corrected numeric source values but materially overstates scientific and forensic certainty.
  ```

### 4.3 Citation 3: Signed Prose Typo in R3 Independent Review
- **Stage A R4 Target:** `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L127`.
- **Erroneous Anchor:** `7750b69...#L133-L137`. (The file ends at line 135; lines 136–137 do not exist).
- **Correct Verified Anchor:** `7750b69a87dcfb392bdfc8d20e7b7f174276452e:reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md#L117-L123`.
- **Target Assertion Line:** Line 119 contains the exact analysis addressing `+-0.26 bp`:
  ```markdown
  117: ### Finding 3 — CONCERN / OBSERVED: misleading signed display and ambiguous match-language
  118: 
  119: R3 Markdown line 124, 42-cell table row #26 (W2_C05/2021 H1–E0) describes the correct negative figure as +-0.26 bp. The actual row's canonical column and JSON have −0.26 bp, so the table numeric correction remains correct, but the explanatory text is malformed.
  ```

### 4.4 Citation 4: Ambiguous Match-Language in R3 Independent Review
- **Stage A R4 Target:** `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L134`.
- **Erroneous Anchor:** `7750b69...#L138-L141`. (The file ends at line 135; lines 138–141 do not exist).
- **Correct Verified Anchor:** `7750b69a87dcfb392bdfc8d20e7b7f174276452e:reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md#L117-L123`.
- **Target Assertion Line:** Line 121 contains the exact analysis addressing event count match scope:
  ```markdown
  121: R3 Markdown line 156 under “Exact / Rounded Matches (18 cells)” says “All 6 event counts match Exit R1”. This is correct only for corrected machine-backed counts, not the original Table 4 (two W2 original annual counts differ). Explicitly qualify which layer is matching to avoid contradicting the 18/24 count.
  ```

### 4.5 Citation 5: Cell #26 Field Line in R3 Crosswalk JSON
- **Stage A R4 Target:** `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L129`.
- **Erroneous Anchor:** `c7d68cf...:V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json#L697`.  
  (Line 697 is `"h18_machine_field_path": null` belonging to cell #24, `W2_C05_2021_H1_mean_net_bps`).
- **Correct Verified Anchor:** `c7d68cfd3f97c27723a48fb4722dd39ddc4a1290:reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json#L737`.
- **Target Field & Context:** Cell #26 (`W2_C05_2021_delta_H1_E0_net_bps`) spans lines 726–744:
  ```json
  726:     {
  727:       "cell_index": 26,
  728:       "cell_id": "W2_C05_2021_delta_H1_E0_net_bps",
  ...
  736:       "original_unrounded_canonical_value": -0.2576475900573598,
  737:       "correct_display_rounded_2dec": -0.26,
  738:       "deviation": 25.27,
  ...
  744:     }
  ```
  The numerical value `-0.26` is confirmed at line 737; the previous citation of line 697 was an address offset error.

---

## 5. Exactly Allowed Scope Qualification (R4 Line 72)

### 5.1 Pre-Repair Statement in Stage A R4 Manuscript
In `V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md#L72`:
> *"The only legitimate independent review of R3 was performed at commit 7750b69a87dcfb392bdfc8d20e7b7f174276452e by an independent review role/session."*

### 5.2 Precisely Qualified Repair Statement
Under the strict authorization of prompt `V06_P1C_R4_FIVE_CITATIONS_REPAIR_EXECUTION_R1.md`, line 72 is qualified as:
> **"the only attributable independent R3 review established in the scoped evidence"**

### 5.3 Evidentiary Limitation & Boundary
- Review commit `7750b69a87dcfb392bdfc8d20e7b7f174276452e` is the sole attributable independent review established within the scoped repository artifacts and verifiable Git commits.
- This statement does **not** assert universal exclusivity or claim that no other review exists outside the inspected repository scope.
- Any hypothetical or alternative reviews outside the scoped evidence remain strictly **`UNKNOWN`**.
- The historical anonymous `REVIEW_PASS` in the frozen R3 JSON metadata remains formally **`UNVERIFIED`**.

---

## 6. Retention of Substantive Decisions & Strict Negative Scope

1. **Substantive Corrections Retained:**  
   The substantive clarifications delivered in Stage A R4 manuscript (`3a5c071...`) remain fully valid and accepted as a subscope (`R4_SEMANTIC_CORRECTIONS_ACCEPTED_SUBSCOPE` per `b1f211b...` Section 4):
   - Replacement of causal impossibility assertion with *"No such ex-ante discriminator is validated by this analysis; whether one exists is UNKNOWN"*.
   - Replacement of cohort calculation notes with *"Original narrative and canonical annual summary values differ; the original manuscript calculation methodology and any cohort transfer are UNKNOWN"*.
   - Correction of signed prose typo to `−0.26 bp`.
   - Explicit qualification that event count agreement refers to canonical machine counts ($N=8, 10, 16, 10, 21, 24$).
   - Coincidence vs. copying origin distinction for W1 2021 Delta (+23.95 bp).
2. **Terminal Status Preservation:**  
   The terminal Stage B R4 review verdict **`REVIEW_FAIL`** (at `b1f211b16be78bd1a73f004f5134f9e27f1a85a2`) remains in force until this repair sidecar is independently verified and adjudicated by the Controller. This sidecar does **not** self-issue an independent `REVIEW_PASS`.
3. **Numeric Integrity:**  
   The original R3 42-cell numeric crosswalk (18 matches, 24 differences, 12 shared machine summary agreements) passed within its limited source scope under independent BigInt fixed-point verification and is **not** being recomputed.
4. **Strict Negative Scope:**  
   - Zero modifications to frozen R2, R3, H18, Exit R1, Stage A R4 manuscript (`3a5c071...`), or Stage B audit (`b1f211b...`).
   - No sixth citation correction.
   - No historical strategy simulation or re-scoring.
   - No access to protected H39/H40/H41/Forward/Holdout datasets, private accounts, or market endpoints.
   - No code, test, or CI workflow changes.
   - Global gates unchanged: `G2_ALPHA_NO_GO`, `G4_TESTNET_NOT_AUTHORIZED`, `LIVE_NOT_AUTHORIZED`.

---

## 7. Execution Governance, Allowlist Affirmation & Receipt

### 7.1 Write Allowlist Compliance
Under the strict allowlist of prompt `V06_P1C_R4_FIVE_CITATIONS_REPAIR_EXECUTION_R1.md`:
- **EXACTLY ONE NEW FILE** is created on branch `docs/v06-p1c-r4-five-citations-repair-r1`:  
  `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_REPAIR_R1.md`
- Zero other files added, modified, or deleted.

### 7.2 CI Pipeline Status
- Documentation paths under `reviews/**` and `prompts/**` are ignored by GitHub Actions CI (`paths-ignore` in `.github/workflows/ci.yml`).
- **Actual CI Status:** **`NOT_RUN`** (docs-only deliverable).

### 7.3 Gate Dispositions & Terminal Verdict
- **Author Verdict:** **`FIVE_CITATION_SIDECAR_READY_FOR_INDEPENDENT_REVIEW`**
- **Independent Attestation Status:** **`R4_REPAIR_INDEPENDENT_REVIEW_PENDING`**
- **Controller Gate Status:** **`CONTROLLER_L2_PENDING`**
- **Next Stage:** Stage B Independent Micro-Audit (under prompt `prompts/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_INDEPENDENT_REVIEW_R1.md`).
