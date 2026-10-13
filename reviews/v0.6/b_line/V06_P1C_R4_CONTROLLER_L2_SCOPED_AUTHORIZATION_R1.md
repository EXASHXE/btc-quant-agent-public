# B-line Controller L2 — Exact-SHA Authorization for P1C-R4 Documentary Clarification and Independent Audit

**Date:** 2026-10-14
**Controller:** ChatGPT-0, B-line Primary Controller
**Decision:** \`L2_AUTHORIZE_P1C_R4_BOUNDED_DOCS_ONLY\`
**Authority:** The immutable commit containing this authorization and the two Stage A/B dispatch prompts. No inference of authority from a moving branch.
**Parent docs SHA:** \`efe0dce0773e2ac76771dda7847a4dffbe867ceb\`.
**Global:** \`G2_ALPHA_NO_GO\`, \`G4_TESTNET_NOT_AUTHORIZED\`, \`LIVE_NOT_AUTHORIZED\`, \`REAL_FUNDS_WRITE_NONE\`.

## Verified basis and bounded Controller adjudication

- Frozen P1C R3 author submission \`c7d68cfd3f97c27723a48fb4722dd39ddc4a1290\`: corrected Markdown + 42-cell source crosswalk JSON. Corrected 18 MATCH, 24 DIFFER, and 12 shared annual summary matches. It remains immutable.
- Independent ChatGPT-1 R3 audit \`7750b69a87dcfb392bdfc8d20e7b7f174276452e\`, review file \`reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md\`, blob \`d2f2b366dd5af114981cac98604f09d60c5e4981\`: terminal **\`REVIEW_FAIL\`**, numerical sub-verdict **\`PASS_42_CELL_NUMERIC_CROSSWALK_ONLY\`**. Its independence is explicitly attributed to the review role/session, not independently authenticated human identity.
- R3 original Markdown says reviewer \`REVIEW_PENDING\`, whereas R3 JSON claims anonymous \`REVIEW_PASS\`. The independent R3 auditor could not recover a real prior attestation backing that R3 JSON claim. It remains **UNVERIFIED**, not automatically upgraded by later independent computation.
- Independent reviewer verified 42 source-field entries and identified three bounded residual classes: (1) reviewer provenance contradiction; (2) categorical causal/forensic claims unsupported by summary evidence, including the asserted absence of an ex-ante feature and presumed alternate annual cohort construction; (3) \`+-0.26\` explanatory typo and ambiguous "All 6 event counts match" layer.
- H18 source commit \`397a62c1a0fbd6ad14a569a5be0058b1f684f08e\`; Exit R1 summary \`55ac4c631c69f6edbd275462ad23e4486b9782ed\`; earlier R2 failed erratum \`b4f24c763895c97a0c304dc422db76a73761251d\`.
- R4 is not a new research result, new alpha, new trial, code fix, or correction to raw source ledgers. There was **no existing remote P1C-R4 branch** during this authorization's preliminary verification.

## Separation of duties and grant

**Stage A: R4 correction/attestation-response SIDE-CAR only** (Gemini NORMAL or other author who is not the subsequent reviewer). The Stage A prompt in this authorization commit grants precisely ONE new Markdown doc on an isolated new docs branch. Existing R3/R2 and all frozen machine sources are read-only. Stage A result is \`R4_RESPONSE_READY_FOR_INDEPENDENT_AUDIT\`, not a PASS.

**Stage B: genuinely independent R4 semantic/provenance audit** (Codex Sol or ChatGPT-1 in a distinct role/session, not the Stage A author). Stage B starts **only after** Stage A's final remote commit SHA, blob SHA and exact one-file diff have been supplied. The Stage B prompt grants one separate NEW independent review document in a separate docs branch; no editing Stage A. Outcome \`REVIEW_PASS\` / \`REVIEW_FAIL\` / \`INCOMPLETE\` is the reviewer's own explicit verdict, not the Controller's final signoff.

**No cross-branch merge**, protected/owner data access, protected H39/H40/H41/Forward/Final Holdout inspection, historical result re-scoring, market ingestion, credential use, account/exchange action, testnet or live authority. Never rename or erase the failed R2/R3 audit history. A green docs-only CI action is not evidence of an executable release gate.

## Controller acceptance checklist for R4

1. R4 source and role provenance distinguished: original R3 JSON anonymous \`REVIEW_PASS\` is not valid prior independent signoff; R3 independent \`7750b69...\` gives \`REVIEW_FAIL\` on published R3 + 42-cell numeric sub-PASS.
2. Categorical \`No causal entry-time feature distinguishes...\` corrected to \`No ex-ante discriminator was validated by these source summaries\`, without claiming impossibility or measured predictive power.
3. W2 narrative-vs-canonical cohort discrepancy is established, while the assertion that published figures were *calculated over a particular noncanonical cohort* remains **UNKNOWN**, absent author worksheets/event identities.
4. Mathematical 2021 W1 E2 SHORT \`23.950589...\` similarity is not proof of manuscript copying; 26/56 adverse is descriptive only; target shares ~98.064%/~74.636% remain ex post only.
5. Remove malformed \`+-0.26bp\` in the **new correction explanation**, and state unequivocally that six counts matching Exit/H18 refer to canonical summary counts, NOT the original narrative (which has W2 annual count errors).
6. All cited 42 figures, bp/%/pp units and STRESS44=44bp research proxy are retained by exact SHA **without new scoring**. The R4 sidecar is an explanatory supersession of R3 prose and reviewer status *only*, not an unauthorized mutation of frozen results.
7. Distinct auditor inspects exact Stage A SHA, reports independent findings and signs its actual role/process; absent review must be \`INCOMPLETE\`, not fabricated PASS.
8. Any residual source provenance unknown is preserved as UNKNOWN. Controller L2 may accept R4 documentary closure only after independent review, and grants no economic, Alpha or external integration gate.

**Disposition:** AUTHORIZED_TO_EXECUTE_DOCS_ONLY, R4 final independent audit and L2 acceptance remain PENDING.
