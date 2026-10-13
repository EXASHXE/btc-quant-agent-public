# Controller Next-Stage Dispatch Matrix — P1C/P1D/CI/P2

Date: 2026-10-13. Owner: ChatGPT-0 B-line Controller. This file records four distinct exact-SHA prompts delivered in the same commit; it authorizes only their specified scopes, not integration or live trading.

## Observed status

- P1C-R3 correction SHA c7d68cfd3f97c27723a48fb4722dd39ddc4a1290: 42 JSON cells, 18 MATCH, 24 DIFFER, STRESS44=44bp reference, no historical reruns. R3 Markdown `REVIEW_PENDING` conflicts with its JSON `REVIEW_PASS`; a second independent artifact with verifiable author/reviewer trail has not been established.
- P1D code latest SHA 81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079: GitHub full CI 38390261764 concluded FAILURE 3357 passed/3 failed/2 skipped; three catalog directory assertions. Independent causal reviewer result needs authenticated exact-SHA receipt.
- P1A synthetic code/report SHA 0540e2c902ef9565cd3719e60174ac01b1c22adf; actual executable run 38382220675 FAILURE 2975 passed/4 failed/2 skipped, three catalog failures plus protected H40 digest mismatch. Later green docs-only run 38384411928 skipped executable tests. Twenty-four bounded synthetic tests previously passed but do not constitute full CI or actual cost calibration.
- Existing .github/workflows/ci.yml supports workflow_dispatch profile=full; no CI workflow modification is necessary for a manual full execution on a frozen repair branch.
- P1B F1-F3 statistical inference remains METHOD_BLOCKED; G2 zero Alpha, G4 TESTNET/LIVE not authorized.

## Concurrent, non-overlapping tasks

1. P1C independent reviewer closes independent provenance, all 42 cells and manifest inconsistency. Write only a new independently authored attestation on docs.
2. P1D independent reviewer investigates receiver-known-at versus economic event downstream, settlement, restart dedup and signed cash. Write only independent docs review.
3. Code/docs migration moves two report blobs unchanged onto a standalone docs archive BEFORE individually deleting source report paths from the two code branches; rerun workflow_dispatch full on each exact repaired code SHA; H40 mismatch explicitly separate owner governance.
4. P2 BTC outcome-blind source/cost/portfolio frequency design only, not a new measured Alpha trial, protected data opening or account trade.

All executor reports must truthfully distinguish PASS under their own bounded scope from overall gate PASS. No force push or auto-merge, no tweaking H40, no verification bypass. Data collection, historical economic scoring, G1/G3 external integration and G4 are separately gated.
