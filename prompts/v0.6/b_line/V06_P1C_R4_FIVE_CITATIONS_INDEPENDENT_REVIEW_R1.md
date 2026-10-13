# P1C R4 five-citation micro-audit — Stage B

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

## Prerequisite and independent role
Reviewer: independently acting ChatGPT-1 or Codex Sol; never the Stage A author. FIRST obtain the exact remote Stage A repair branch commit SHA AND blob SHA for `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_REPAIR_R1.md`; verify the commit has one added allowlisted file relative to this Controller authorization commit. Do not accept a moving-branch-only target. Missing or mismatched target => `INCOMPLETE_TARGET_UNFROZEN`, no PASS.

Read only the source files identified above, actual Stage A sidecar and this authorization. Independently check the five citations *against the exact original source lines*, not merely the author's table. Confirm each old R4 false anchor and its immutable new correct range, including #L737 representing cell 26 `-0.26` and #L697 representing unrelated data. Verify that the single permitted line-72 qualifier neither erases R3 REVIEW_FAIL nor invents reviewer exclusivity. There must be NO sixth citation correction, no new metrics, no 42-cell rerun, no H18/Exit rewrite and no original R4 modification.

## Write authorization (separate audit branch)
Create `docs/v06-p1c-r4-five-citations-independent-review-r1` from exactly this Controller AUTHORIZATION COMMIT, without merging Stage A; fetch its sidecar read-only by exact SHA.
Write only NEW `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_INDEPENDENT_REVIEW_R1.md`.

Report independently observed source snippets and line intervals, exact Stage A commit/blob identity, five mapping PASS/FAIL results, single qualifier check, two-branch diff/permissions, reviewer role and actual executed operations. Terminal **`REVIEW_PASS` / `REVIEW_FAIL` / `INCOMPLETE`** applies ONLY to the narrow R4 five-citation supersession. The original Stage B fail and R3 history remain immutable, and the Controller alone can adjudicate documentary closure. Never claim Alpha/PIT/cost/release acceptance.

No market data, history runner, source/evidence write, protected H39/H40/H41/Forward/holdout, accounts, code/CI edits, merge, testnet, live or real funds permissions.
