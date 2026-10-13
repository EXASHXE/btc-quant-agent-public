# P1C-R4 — Bounded Clarification and Attestation-Response Sidecar (Stage A)

**Task ID:** \`V06_P1C_R4_DOCUMENTARY_CLARIFICATION\`.
**Controller authority:** \`L2_AUTHORIZE_P1C_R4_BOUNDED_DOCS_ONLY\`, contained in the immutable commit together with this prompt. The invoking Controller supplies the exact dispatch commit SHA; verify that SHA and both prompt blobs before acting.
**Executor:** Gemini NORMAL (corrective author); **not** the reviewer who will subsequently attest R4.
**Base:** checkout the immutable Controller authorization commit into a clean isolated docs worktree; create \`docs/v06-p1c-r4-clarification-response-r1\`. If the exact branch exists with a different HEAD or write scope conflicts, STOP; never force-push.

## Approved source identities

- P1C-R3 original submission at \`c7d68cfd3f97c27723a48fb4722dd39ddc4a1290\`, its two frozen docs:
  \`reviews/v0.6/b_line/V06_P1C_H18_TABLE4_CORRECTED_ERRATUM_R3.md\`;
  \`reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json\`.
- Independent R3 42-cell review at \`7750b69a87dcfb392bdfc8d20e7b7f174276452e\`, \`reviews/v0.6/b_line/V06_P1C_R3_INDEPENDENT_REVIEW_ATTESTATION_R1.md\`; independent verdict \`REVIEW_FAIL\`, numerical-only sub-verdict \`PASS_42_CELL_NUMERIC_CROSSWALK_ONLY\`.
- Frozen H18 \`397a62c1a0fbd6ad14a569a5be0058b1f684f08e\`, Exit R1 \`55ac4c631c69f6edbd275462ad23e4486b9782ed\`, failed R2 \`b4f24c763895c97a0c304dc422db76a73761251d\`.
- Controller authorization file colocated with this prompt.

**Read limitation:** only exact public summary/docs/42-cell JSONs and public Git object identities. Do not read market/event-level arrays, underlying trading source/trade logs, historical source runner, protected H39/H40/H41/Forward/Holdout, owner data roots, private repositories, accounts, credentials, actual market endpoints or executable adapter environments.

## Write allowlist — EXACTLY ONE NEW FILE

\`reviews/v0.6/b_line/V06_P1C_H18_R4_CLARIFICATION_AND_ATTESTATION_RESPONSE.md\`

No other file may change: do NOT edit R3 Markdown or JSON, R3 independent review, R2, original H18/Exit, code/tests/CI, or other roles' documents. A new 42-cell JSON is NOT authorized. No modification of original R3 reviewer_status is permitted; instead provide a versioned R4 precedence/correction statement.

## Required corrections, each with original exact SHA/path/line reference

1. Explicit status hierarchy: original R3 Markdown \`REVIEW_PENDING\`; R3 JSON anonymous \`REVIEW_PASS\` **UNVERIFIED**; actual R3 independent reviewer at \`7750b69...\` \`REVIEW_FAIL\` overall, \`PASS_42_CELL_NUMERIC_CROSSWALK_ONLY\`. State this does NOT retroactively validate the claimed anonymous PASS, nor invalidate its already separately checked numeric entries.
2. Replace "No causal entry-time feature distinguishes 7 winners from the remaining 49 trades without lookahead" with "No such ex-ante discriminator is validated by this analysis; whether one exists is UNKNOWN." Avoid categorical absence of predictive power.
3. Replace R3 cell notes "Calculated over non-canonical cohort" (W2 2021/2022) with "Original narrative and canonical annual summary values differ; the original manuscript calculation methodology and any cohort transfer are UNKNOWN." Similar numbers of events across two years do not reveal specific transferred identities.
4. Correct signed prose typo \`+-0.26 bp\` → \`−0.26 bp\`. State numerical R3 table/JSON already contains the correct negative value; new text fixes prose only. Qualify "All 6 event counts match Exit R1" as referring to **corrected canonical numbers** (not 2 W2 narrative counts).
5. Retain source-limited factual bounds: STRESS44=44bp round-trip assumed sensitivity (24bp fee+8bp spread+12bp slippage), not measured; 42-cell correction =18 original match,24 differ; 12 shared counts/deltas only; W1 2023=+56.88bp, W2 2023=+27.39bp; account-return differences in pp; 26/56 adverse DESCRIPTIVE_ONLY; right-tail 4/3 ex post only. Do not re-run or rescore strategy outcomes.
6. Distinguish the W1 +23.95 & E2 SHORT ≈23.950589 numerical coincidence from an unsupported copying-origin claim. No author's thought process or manuscripts are in evidence; drafting cause UNKNOWN.
7. For each independent R3 review finding, provide traceable pre-R4 statement, precisely corrected R4 statement, reason/evidentiary limit and unresolved UNKNOWN. Include a clear "R4 sidecar supersedes only the identified R3 interpretation/attestation claims; R3 machine crosswalk and old evidence remain immutable" declaration.
8. Do NOT insert an independent audit \`REVIEW_PASS\` into this authored sidecar. Mark \`R4_REVIEW_PENDING\` and \`CONTROLLER_L2_PENDING\` until an independent reviewer actually evaluates this new SHA. Do not impersonate a reviewer.

## Publish/stop

Write solely the one allowed Markdown file on the isolated docs branch. Check diff against the exact base. Publish its exact full Git commit SHA and blob SHA, reviewer requirement, line-count/terminology checks and actual CI status (if absent, NOT_RUN). No independent re-review may occur at an unpinned branch HEAD. Terminal \`R4_RESPONSE_READY_FOR_INDEPENDENT_AUDIT\` or \`R4_RESPONSE_BLOCKED\` with concrete cause.

This grant does not include a new historical trial, funding/PIT integration, data admission, Alpha, TESTNET or LIVE.
