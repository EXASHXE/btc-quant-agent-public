# Controller Dispatch — P1D-R3 Independent Consumer C Funding/PIT and Ledger Semantics Review

Owner: ChatGPT-0 B-line Controller.
Independent executor: Codex Sol High or ChatGPT-1 Auditor (not the Gemini BOOST author of P1D).
Freeze implementation exactly at 81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079.
Read-only comparison baseline: 91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b.
Review dispatch SHA is the immutable commit containing this prompt; verify first.
Original P1D evidence in its five-path scoped branch, remote CI full run 38390261764: 3357 passed, 3 failed, 2 skipped. All three failures are reviews/ surface-reduction assertions. Docs-only run 38386975908 did NOT run executable pytest; do not conflate it with full CI.

## Evidence-first procedure

If another independent auditor already completed this exact task, locate and authenticate its retained full report, exact reviewed SHA, reviewer identity and real executed tests. If no attributable artifact exists, perform independent code review; do not accept a Gemini-authored claim "Independent auditor: Sol" as independent execution evidence. Do not duplicate broad CI unless necessary; the existing run is authoritative for its SHA.

Review scripts/g1g3_offline_ports_r1/market_pit_port.py, the two changed P1D synthetic suites, and the immediate PUBLIC G1 consumer interfaces and recovery journals at the frozen implementation SHA. No code/test/source modifications. Synthetic local test execution is allowed only for bounded falsifying witnesses, no historical market data, protected A-line sources, credentials, accounts, Feishu external send, exchange order or funding API.

## Audit-specific hard questions

1. Economic settlement_at, provider event time and receiver available_at/known-at must be separate. Port accepts a late settlement REST report without backdating feature visibility. Test both after-receipt and prior decision snapshots.
2. g1_event.at is explicitly the OLD economic timestamp. Does the downstream G1 event queue, event sort, WAL or ledger mistake it for receiver-known-at? The translated Funding payload exposes settlement_at/rate; prove how receiver-known-at is retained downstream, or mark INTEGRATION_BLOCKED. Do not infer causal correctness from the port's max_feature_known_at alone.
3. Duplicate funding replay on same and different transport keys, divergent event_id/Mark/rate, restart persistence of seen_funding_settlements, journal state reconstruction and exactly-once cash posting. Validate no double charge or accepted conflicting settlement after crash.
4. Test signed short exposure and side/quantity consistency including negative signed quantities, zero-quantity flat positions, before/after economic partial exits, Mark-based funding, ±15s settlement-time uncertainty if relevant, stale/clock regression and completeness witness. Missing Mark, absent rate or uncertain coverage must not become zero realized cash.
5. The unit helper calculation is not proof that source Mark, executed position, venue charge, queue ACK or wallet post exist. Synthetic-only CONTRACT grade.
6. Check invariant that one settlement is not replayed as market strategy features at the economic timestamp after receiver ingestion; identify any unverified downstream replay hazard as BLOCKER.

Return attributable defects with severity, exact source file/line/commit, minimal falsifying example, evidence and lowest-scope remediation. Distinguish port-only assurance, code-path integration, financial source completeness and release gate.

## Publication

New docs sidecar branch from docs SHA 2c99c8f64368a02dfeca05ac1886ed2280faf3ba:
docs/v06-p1d-independent-causal-review-r1
Exact single new path:
reviews/v0.6/b_line/V06_P1D_FINAL_SHA_INDEPENDENT_CAUSAL_REVIEW_R1.md

Do not edit P1D source/tests, prior receipt, CI, H40 evidence or another branch. If independent reviewer cannot substantiate a result, mark REVIEW_INCOMPLETE and do not claim PASS.
Verdict is one of PASS_SYNTHETIC_PORT_ONLY, FAIL_CAUSAL_PIT, INTEGRATION_BLOCKED, REVIEW_INCOMPLETE. PASS_SYNTHETIC_PORT_ONLY is NOT production/economic settlement-source certification, G1/G3 merged release or G2 Alpha.
Include reviewed SHA, actual local test commands if run, immutable CI URL/results, exact new docs commit and no protected writes.
