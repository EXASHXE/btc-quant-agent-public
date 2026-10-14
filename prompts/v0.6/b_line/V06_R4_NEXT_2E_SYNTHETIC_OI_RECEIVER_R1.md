# ChatGPT-2-E — Pure invented-input OI receiver / PIT witness negative suite R1

**Owner:** ChatGPT-0 B-line Controller, five sessions 0/1/2-R/2-C/2-E. Authority is the exact immutable Git commit and file blob which publishes this prompt. Check exact Git SHA before acting. Start an isolated branch from the specified base; verify parent, diff, real test evidence, pushed HEAD. No self-independent audit, force-push, merge or branch-policy switch.

**Forbidden:** protected H39/H40/H41/Forward/Final Holdout content, reserved outcomes, owner private data roots, historical strategy-return replays, new market REST/WS source collection, production/testnet orders, credentials, funds, and changing historical frozen results or safety/CI goldens. SOURCE_NOT_ADMITTED / G2_ALPHA_NO_GO / TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE.

**Base code SHA:** 13e3a710b137efeec2e21e3002f748834ec0cc22. **Branch:** feature/v06-r4-2e-oi-synthetic-witness-r1. Research source 2-R R3 35c269aecf0f1b756575af2ac5e355f2cf53757c, reviewer 2-C a1e9632a30f330041bcffb22c2ba3d3d656963bc; consequential ChatGPT-1 R3 review may still be pending. This is a standalone synthetic prototype, not source authority.

**Exactly TWO ADD files; NO other modifications:**
1. scripts/strategy_research/g2_oi_pit_synthetic_receiver_witness_r1.py
2. tests/test_v06_g2_oi_pit_synthetic_receiver_witness_r1.py

Implement deterministic pure functions consuming entirely invented attempt/clock/payload/durability envelopes, never real HTTP, WebSocket, market prices, provider/clock system calls, filesystem persistent recorder, dataset reads or authenticated source flags. Distinguish provider period-end, complete body reception monotonic clock, conservative upper UTC bound, safe durability acknowledged time, decision known-at, source version and raw fake bytes digest. Preserve append-only revision/duplicate identity in the invented state transitions, no backdating later version to earlier decision. If external clock/source/rights attestation is not independently authenticated, fail closed PIT_UNKNOWN and SOURCE_NOT_ADMITTED; a synthetic signed=true, 64-hex hash or fabricated 40ms estimate must never self-admit.

Prove invented negative cases: 15m period end before received; header-only/incomplete body; clock epoch/step/rollback/offset uncertainty; missing chrony-style witness; body complete but durability absent/lost; crash before/after append ACK; byte duplicate versus same-version changed numerical OI; payload corrected after the prior decision; missing earlier 15m bucket; unit/contract-version conflict; no rights receipt; quote/X/oi source gaps; decoder mismatch. Use Decimal for mock OI quantities; label SYNTHETIC every output. Metamorphic deterministic replay/permutation must not create earlier first-known-at. Include no-network import/AST assertions. No empirical source/latency rate, statistical event outcomes, fee or Alpha.

Run actual focused pytest and lint/compile on new files. Only claim RED evidence if truly executed before repair. Report focused results, honest full CI if run, exact SHA/parent/blobs, two ADD only and source-unadmitted terminal. No connection to Episode production code, G1, P1D, CI planner, existing test fixtures or protected data.

**Terminal:** SYNTHETIC_RECEIVER_WITNESS_READY_FOR_INDEPENDENT_AUDIT / SCOPE_BLOCKED / FAIL. Handoff frozen exact SHA to ChatGPT-1; current R3 design audit may require separate future corrective contract, never silently treat this prototype as accepted source.
