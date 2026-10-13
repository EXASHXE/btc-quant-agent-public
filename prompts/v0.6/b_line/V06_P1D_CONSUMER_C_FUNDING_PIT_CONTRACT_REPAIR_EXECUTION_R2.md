# Controller Dispatch — P1D Consumer C Late-Funding PIT Contract Repair R2

**Owner:** ChatGPT-0 B-line Controller. **Executor:** Gemini BOOST. **Review:** Codex Sol High independent financial/causal review.
**DISPATCH_ID:** V06_P1D_CONSUMER_C_LATE_FUNDING_PIT_R2.
**DISPATCH_SHA:** the immutable Git commit containing THIS prompt; verify before applying. This document is scope-specific authority for isolated synthetic-only source and test changes, NOT a merge, empirical score, source collection, testnet or live authorization.
**FROZEN CODE BASE:** 91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b (Consumer C known baseline). Create feature/v06-p1d-consumer-c-late-funding-pit-r2 as an isolated worktree from this exact SHA. Do not overlay Gemini BOOST branch; BOOST architecture fdec02d5d7cf9d80ae45fc36c56af5008df003d6 is READ-ONLY semantics reference, NOT a merge parent. Fail if the starting repository/ref is not exact.

## Observed defect

scripts/g1g3_offline_ports_r1/market_pit_port.py function _translate_funding checks wall_ms >= settlement_at AND avail_ms == settlement_at, rejecting legitimate settlement REST records received after the economic charge. Envelope available_at_ms is a *receiver-known-at* bound, not the settlement clock. Do not backdate availability, overwrite earlier decision information sets or silently treat missing Funding as zero.

## Narrow write allowlist

- scripts/g1g3_offline_ports_r1/market_pit_port.py
- tests/test_v06_g1g3_offline_ports_r1_core_integration.py
- tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py
- reviews/v0.6/b_line/V06_P1D_CONSUMER_C_LATE_FUNDING_R2_IMPLEMENTATION_AND_EVIDENCE.md
- evidence/v0.6/b_line/p1d_consumer_c_late_funding_r2/SYNTHETIC_CASE_RECEIPT.json

Do not change generic G1 ledger/runtime, feed bridge A/B, source adapters, protected code/evidence, experiments, financial reporting engines or existing frozen research results. If necessary downstream behavior cannot be made safe within this list, emit CONTRACT_BLOCKED_REQUIRED_SCOPE and a minimal change proposal; do not expand scope silently.

## Causal contract

Separate immutable economic settlement_at from provider publish time (UNKNOWN if not supplied), actual receiver ingress/known-at, decision_at, transaction/posting time, and source Mark witness. Preserve observed Funding rate identity, settlement id, signed quantity exposure AT SETTLEMENT (not delayed receipt), and exactly-once ledger semantics. Future data may not alter the earlier decision state. For a late REST record, accept only if envelope chronology/provenance is coherent and the event is irrevocably settled; future-known, forged or missing-event claims fail closed. An estimated Funding event cannot pass as realized. No use of Mark as an executable trade price.

## Synthetic acceptance (before any release claim)

Write focused invented-data tests for: on-time settled funding, 3-second and multi-minute late receipt with correct receiver-known-at, unchanged earlier decision feature view, duplicate replay idempotence, same settlement ID conflicting rate/Mark hard fail, receipt-before-settlement reject, missing Mark/rate => COST_INCOMPLETE, funding credit/debit side symmetry, exposure before vs after partial fill/settlement, ambiguous fill-vs-settlement boundary, reconnect or clock-regression fail closed, zero-real-funding requiring complete witnessed coverage. Preserve a strictly causal source-event ledger with no retroactive strategy feature access. If existing payload schema cannot safely represent required witness, refuse narrow implementation rather than creating synthetic false verification.

Run only relevant focused tests initially, plus correct risk-map/full release tests when warranted by executable changes. Record selected tests and actual counts, any skipped suites, dependency versions, reviewer evidence, source/end SHAs and exactly changed paths. No automatic cross-branch merge.

**Pass:** independently audited synthetic known-at/funding contract invariants and no unknown-data-to-zero; **fail:** any retroactive decision leakage, unsupported settlement Mark, double posting, prohibited file modification or incomplete account conservation. Terminal PASS_CONSUMER_PIT_CONTRACT_PENDING_INTEGRATION or CONTRACT_BLOCKED_REQUIRED_SCOPE. G2 Alpha/TESTNET/LIVE remain NO_GO.
