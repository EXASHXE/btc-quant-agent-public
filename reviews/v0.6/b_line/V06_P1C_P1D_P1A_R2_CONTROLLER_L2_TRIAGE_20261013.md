# Controller L2 Triage: P1C / P1D / P1A-R2
Date: 2026-10-13; authority: ChatGPT-0 B-line Controller; scope: GitHub public source/report receipts only.

## Exact remote branches and bounded findings

| Task | Remote SHA | Scoped result | L2 terminal |
| --- | --- | --- | --- |
| P1C H18 narrative erratum | b4f24c763895c97a0c304dc422db76a73761251d | Two allowed doc/JSON paths, no original evidence edits | DELIVERED_AUDIT_AND_CORRECTION_REQUIRED |
| P1D Consumer C funding PIT | 81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079 | Five allowed code/test/review paths; local 155 pass; prior CI 3 catalog failures; latest HEAD full CI running when inspected | SYNTHETIC_CONTRACT_SCOPE_ACCEPTED_PENDING_LATEST_CI_AND_INDEPENDENT_REVIEW |
| P1A-R2 per-fill synthetic costs | 0540e2c902ef9565cd3719e60174ac01b1c22adf | Four allowed paths; 24 new targeted tests pass; full CI 2975 pass / 4 fail / 2 skipped | SYNTHETIC_CASES_PASS__FULL_GATE_BLOCKED |

All three were branched from their respective Controller-authorized exact engineering/docs base, without changing frozen strategy results. P1C doc-branch parent is efa2df62...; it cites the separately published Controller dispatch 68def8... and was intentionally NOT based on that docs-branch tip.

## P1C needs correction and truly independent verification

Narrative report: https://github.com/EXASHXE/btc-quant-agent-public/blob/b4f24c763895c97a0c304dc422db76a73761251d/reviews/v0.6/b_line/V06_P1C_H18_YEARLY_TABLE4_IMMUTABLE_ERRATUM_R2.md

- Its own header says REVIEW_PENDING, despite REPORT_ERRATUM_READY. No independent completed reviewer decision is present.
- Section 4 states STRESS44 means "taker 4.4 bp / round-trip 8.8 bp". This is incorrect. STRESS44 is the legacy 44 bp round-trip cost proxy (12+4+6 per leg, multiplied by two). Correct the sidecar explanation; do not rewrite frozen source ledgers.
- Its section 4 W1 2023 H1-E0 narrative +56.89 vs canonical +56.8831195 bp and W2 2023 narrative +27.38 vs canonical +27.386912 bp are MARKED MATCH_ROUNDED in Markdown, while its companion machine crosswalk marks both MISMATCH. At two decimal digits the canonical rounded values are +56.88 and +27.39 respectively. Do not claim all 2023 entries match.
- The claim that exactly four 2022 events were shifted into 2021 is not established merely by N(14,17) versus N(10,21). It requires exact event-to-year evidence including narrative cohort identities not provided. The purported human manual copy cause of +23.95 also cannot be independently proven by similarity to another value alone; treat causal provenance as unconfirmed unless supported.
- The claim of 100% exact matching across "all timestamps" is stronger than the displayed aggregate crosswalk. Difference in float last digits is not exact identity. Separate verified numeric agreement from unjustified event-level totality.
- "Statistically indistinguishable from a 50/50 coin-flip" needs an actual defined test/CI; 26/56 adverse is descriptive, not a validated hypothesis test. This is not a basis to automatically abandon an exit hypothesis or approve one.
- The existing 4-W1/3-W2 right-tail attribution is retrospective; no ex-ante classifier or strategy Alpha PASS is established.

**Disposition:** do not accept P1C as independently completed until an independent read-only exact-source verification and non-destructive correction sidecar closes these issues. Do not edit the original H18 narrative/machine ledger.

## P1D

Source: https://github.com/EXASHXE/btc-quant-agent-public/commit/81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079

Old equal-time funding acceptance was corrected to allow late REST receipt with economic settlement-at held distinct from receiver-known-at. Latest code improves conflict checking and duplicate transport clock bookkeeping. Local 155 tests pass as reported; actual remote earlier full run 38383966460: 3357 passed/3 failed/2 skipped. All three failure assertions require reviews/ to be absent on the code branch, while the Controller explicitly required the report under reviews/. Latest SHA run https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38390261764 was IN_PROGRESS during inspection. A docs-scoped CI success at earlier receipt-only SHA bd868d9... skipped executable suite and does not resolve this. Report header names an independent review route, but no distinct signed independent review receipt was found in the delivered allowlist; require direct reviewer evidence and code/consumer known-at semantics check. Synthetic port accepts delayed receipt, but G1 integration and financial settlement completeness remain separately unproven.

## P1A-R2

Source: https://github.com/EXASHXE/btc-quant-agent-public/commit/0540e2c902ef9565cd3719e60174ac01b1c22adf

Independent local reviewer and all 24 synthetic tests reportedly passed. GitHub execution CI 38382220675 at tested implementation a535fde2... ran FULL and FAILED: 2975 passed, 4 failed, 2 skipped. Three failures: test_v050_r01_surface_reduction asserts absence of reviews/ (Controller-dispatched report path conflicts with intentional code/docs surface split). Fourth: protected H40 synthetic scientific graph digest mismatch d5a962... expected vs ee185f... actual. Cause has NOT been isolated; never call it pre-existing or harmless without a base-comparison controlled diagnostic authorized by H40's governing owner. Do not read/alter H40 protected evidence, original golden, protected source or old validation outcomes.

P1A-R2 cost arithmetic is **synthetic contract research**, NOT measured NORMAL/ADVERSE fee spread/slippage/funding, nor venue fill model or historic G2 repricing.

## Next gates

1. Independent P1C forensic review + bounded correction sidecar.
2. Independent P1D financial/PIT review against latest exact code SHA and final current CI receipt.
3. Separate CI compatibility diagnosis for the reviews/ placement. Prefer restoring code/docs segregation by a separately authorized relocation and preserving tests, rather than broad weakening of catalog policy.
4. H40 scientific golden case stays under its own Controller; no implicit fix, no suppressed tests. Any cross-line request must use approved separate owner authority.
5. Later prospective public quote evidence and cost model integration require separate quantified grants. F1-F3 METHOD_BLOCKED, G2 Alpha NO_GO, TESTNET/LIVE NO_GO.

No new code execution, historical result scoring or protected data read was authorized by this triage receipt.
