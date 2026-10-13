# Controller L2 authorization — P1C R4 FIVE-source-citation repair (single bounded grant)

**Controller action:** `AUTHORIZE_R4_FIVE_CITATION_REPAIR_ONLY`. Date: 2026-10-14. Authority commit: immutable commit containing this authorization and the two dispatches. Original docs parent: `7568678a983c4b16c71908c8b0f9bcd3570e4a19`.

R4 Stage A published SHA `3a5c071c1e25a11d8047105657f8df6755dc3aba`; independent R4 Stage B audit `b1f211b16be78bd1a73f004f5134f9e27f1a85a2` gives `REVIEW_FAIL` solely for five line-anchor defects and an evidence-scope wording concern; semantic sub-verdict is `PASS_WITHIN_BOUNDED_DOCUMENTARY_SCOPE`. Independent prior R3 audit `7750b69a87dcfb392bdfc8d20e7b7f174276452e` established 42/42 numeric crosswalk but R3 overall failed. Preserve those historical decisions.

## Five verified source corrections (all from immutable Git files)

| R4 Stage A line | False anchor | Verified correct anchor |
| --- | --- | --- |
| 85 | R3 independent review #L120-L125 | R3 independent review #L109-L115; relevant assertion #L111 |
| 106 | R3 independent review #L126-L131 | R3 independent review #L109-L115; relevant assertion #L113 |
| 127 | R3 independent review #L133-L137 | R3 independent review #L117-L123; sign typo #L119 |
| 134 | R3 independent review #L138-L141 | R3 independent review #L117-L123; count wording #L121 |
| 129 | R3 JSON #L697 | R3 JSON #L737; cell #26 #L726-L744 (`-0.26 bp`) |

Permitted wording limitation ONLY: replace R4 line 72's "only legitimate independent review" claim with **"the only attributable independent R3 review established in the scoped evidence"**. No sweeping claim about all external reviews. Do not introduce another numerical, causal or evidence conclusion.

## Two-stage execution, separation of duties

1. **Stage A — single citation-repair sidecar**, author Gemini NORMAL or equivalent independently of the reviewer; new branch `docs/v06-p1c-r4-five-citations-repair-r1` based on THIS immutable Controller grant commit. Exactly ONE NEW FILE: `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_REPAIR_R1.md`. The original R4 Stage A and R4 independent FAIL audit remain byte-for-byte untouched. The sidecar is only a supersession of these five erroneous reference pointers and one scope qualifier. No PASS self-certification.
2. **Stage B — genuinely independent micro-audit**, distinct author/reviewer, starts only once Stage A exact remote commit and blob are frozen. New branch `docs/v06-p1c-r4-five-citations-independent-review-r1` from THIS grant commit, exactly ONE NEW FILE: `reviews/v0.6/b_line/V06_P1C_R4_FIVE_CITATIONS_INDEPENDENT_REVIEW_R1.md`. Review the five anchors and scope qualifier, exact one-file diff and frozen identities; record independent `REVIEW_PASS` / `REVIEW_FAIL` / `INCOMPLETE`. Stage B result does not self-issue Controller L2 closure.

**Hard stop / nonauthorization:** no editing old files, no source/evidence JSON modifications, no new machine table, no broad R4 prose rewriting, no 42-cell rework, no historical strategy simulation, markets/raw events, protected H39/H40/H41/Forward/holdout or owner/private data access, no code/CI changes, no cross-branch merge, no testnet or trading. Documentation only; G2_ALPHA_NO_GO / TESTNET_NO_GO / LIVE_NO_GO.

Current terminal: `R4_FIVE_CITATION_REPAIR_AUTHORIZED`, `R4_L2_CLOSURE_PENDING_NEW_INDEPENDENT_REVIEW`.
