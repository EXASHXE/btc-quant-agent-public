# P1C R4 five-citation precision repair — Stage A

Controller: ChatGPT-0, quant v0.6 B-line. Task only: P1C-R4 five erroneous line citations and one evidence-scope qualifier; immutable authority is the Git commit containing this prompt. No other work or implied release grants.

Frozen Stage A R4 manuscript: 3a5c071c1e25a11d8047105657f8df6755dc3aba
  path: reviews/v0.6/b_line/V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md
  blob: 9d3857de60a622abf0a277271d249e9828940f04
Frozen failed independent Stage B R4 audit: b1f211b16be78bd1a73f004f5134f9e27f1a85a2
  path: reviews/v0.6/b_line/V06_P1C_R4_INDEPENDENT_TERMINAL_AUDIT_R1.md
  blob: e3e937378ca6317f2dd74f428a3aaf9987c2da81
Frozen R3 independent review: 7750b69a87dcfb392bdfc8d20e7b7f174276452e
  path: reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md
  blob: d2f2b366dd5af114981cac98604f09d60c5e4981
Frozen R3 machine crosswalk: c7d68cfd3f97c27723a48fb4722dd39ddc4a1290
  path: reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json
  blob: 3d9e4a0c1f7116eb03edd793b5f670b5002ca167

Exactly five line anchors:
1. Stage A R4 line 85: incorrect R3 audit L120-L125 -> correct R3 audit L109-L115 (particularly line 111).
2. Stage A R4 line 106: incorrect R3 audit L126-L131 -> correct R3 audit L109-L115 (particularly line 113).
3. Stage A R4 line 127: incorrect R3 audit L133-L137 -> correct R3 audit L117-L123 (particularly line 119).
4. Stage A R4 line 134: incorrect R3 audit L138-L141 -> correct R3 audit L117-L123 (particularly line 121).
5. Stage A R4 line 129: incorrect R3 crosswalk JSON L697 -> correct exact field line L737, with cell #26 spanning L726-L744, value "correct_display_rounded_2dec": -0.26.

Only allowed qualifier: Stage A R4 line 72's "only legitimate independent review of R3" must be restated as "the only attributable independent R3 review established in the scoped evidence." This cannot assert that no other review exists. No other prose rewrite.

## Execution boundaries
Role: Gemini NORMAL or another author who is **not** the later independent auditor. Verify all pinned file/blob identities. Start a clean isolated docs branch `docs/v06-p1c-r4-five-citations-repair-r1` from the exact Controller AUTHORIZATION COMMIT containing this file (the invoking Controller provides this SHA). No force-push, no mutations in old R4 branch.

**Write allowlist: EXACT ONE NEW MARKDOWN FILE ONLY**
`reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_REPAIR_R1.md`

The sidecar is a narrow erratum. Include a table of precisely the FIVE source-line corrections above with full immutable commit SHA, exact path, old R4 line/anchor, new R3 source-line/anchor, and the quoted small source snippet demonstrating the correct citation. Add exactly ONE narrow scope clarification: replace original R4 line 72's "the only legitimate independent review of R3" with "the only attributable independent R3 review established in the scoped evidence"; note alternative reviews outside scope remain UNKNOWN.

Confirm the original R4 semantic corrections remain accepted as a **subscope** of `b1f211b...`, while the terminal R4 review `REVIEW_FAIL` remains in force until independently repaired and Controller-adjudicated. The original R3 42-cell numeric crosswalk passes in its limited source scope but is **not** being recomputed. Do not claim R4 PASS, reopen science/causal narratives, adjust bp/%/pp, or add new scientific conclusions.

## Strict stop conditions and receipt
If any literal source SHA/path/line does not match, STOP with `CITATION_SOURCE_CONFLICT` and do not fabricate a new line. Verify all five citations with source line content; record one scope qualifier. Diff must show exactly one added allowed Markdown file and no other paths. Report exact parent SHA, new branch SHA, new blob SHA and actual checks performed. Terminal author verdict `FIVE_CITATION_SIDECAR_READY_FOR_INDEPENDENT_REVIEW` or `SCOPE_BLOCKED`, never independently `REVIEW_PASS`. No CI green claims when CI has not run. No historical PnL runner/market data/trading or protected accesses.
