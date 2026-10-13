# P1D Consumer C R3 — Independent Financial/PIT Audit

Reviewer: Codex Sol / ChatGPT-1 independent of Gemini BOOST P1D implementer.
DISPATCH_BASE_DOCS_SHA: 68def8fed3fd290ffbddf00a8f86e4184a8b036f. Freeze current source at 81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079.
Scope: READ-ONLY code/tests/reports/receipt and existing GitHub CI. No merge, source edit, market fetch, result scoring or account/order writes.

Audit Consumer C `market_pit_port.py` `_translate_funding`, `ingest_envelope`, duplicate/re-key conflict, receiver-known-at, delayed settlement at vs published event at, later decisions, crash/restart state and journal persistence, G1 consumer-facing schema, Mark and actual exposure at settlement, sign/zero coverage, ambiguity +/-15s and replayed conflicting event IDs. Confirm that provenance journal and consumer downstream semantics are not mistakenly treated as evidence of real settlement cash. Distinguish demonstrated unit-scoped behavior from untested integration, including the fact `g1_event.at` retains old settlement time while receiver availability is a different clock.

Verify independent 155 local test report against named actual tests, inspect remote CI 38390261764 FINAL status (not earlier docs-only green). Explicitly segregate the known reviews/ catalog failure from new code failures; preserve all other defects. Require an independently authored report of substantive review, not merely the executor's asserted auditor name.

No privileged/reserved dataset, private account, exchange orders, H39/H40/H41/Forward/Final Holdout, provenance rewriting or CI test policy changes. Return PASS_SYNTHETIC_C_ONLY / FAIL_CAUSAL_PIT / REVIEW_INCOMPLETE with exact code SHA and evidence; never promote to integrated G1/G3 or G2 Alpha.
