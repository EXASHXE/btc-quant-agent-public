# ChatGPT-1 — Independent P1D G1/C4/WAL R3 architecture audit

**Owner:** ChatGPT-0 B-line Controller, five sessions 0/1/2-R/2-C/2-E. Authority is the exact immutable Git commit and file blob which publishes this prompt. Check exact Git SHA before acting. Start an isolated branch from the specified base; verify parent, diff, real test evidence, pushed HEAD. No self-independent audit, force-push, merge or branch-policy switch.

**Forbidden:** protected H39/H40/H41/Forward/Final Holdout content, reserved outcomes, owner private data roots, historical strategy-return replays, new market REST/WS source collection, production/testnet orders, credentials, funds, and changing historical frozen results or safety/CI goldens. SOURCE_NOT_ADMITTED / G2_ALPHA_NO_GO / TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE.

**Target:** frozen R3 8c7693700c15f32329614a23b737d34cc7e2b0c4, docs/engineering/v0.6/V06_NEXT_P1D_R4_C4_WAL_VERSION_DESIGN_CORRECTIVE_R3.md, Git blob a5b9af68bf1ddfd0ada5e047e0b6a11bf880e7a0. Earlier independent R2 DESIGN_REVIEW_FAIL 019682bc0178504ef233e4560bb1e91508954f76, B01–B07. Old in-place R4 code 81a71467ac7a9b852587b6e5f826d8ee28fc769c is diagnostic only.

Independently check:
B01 preserve all 13 original immutable C4 files and V1 behavior; an author-editable checksum dictionary is not a trust root. Verify proposed externally pinned full R4 code/import/AST tree, verified launcher-before-import, symlinks/import shadow/TOCTOU negative tests.
B02 one canonical R4 version for Genesis/state/WAL/events/journal/checkpoint/ACK, V1-to-R4 and R4-to-V1 rejection, no implicit migration or fallback.
B03 after_append is pre-fsync. Analyze complete survivor versus absent/torn record, directory/fsync/checkpoint/corrupt tail HARD STOP and ACK strictly after durable recovery.
B04 Funding signed cash/economic key independent of transport events, source Mark/rate/fill snapshot first-known-at, one persisted economic effect, crash/ACK_READY/ACK_EMITTED recovery with exact hashes and no circular state hash.
B05 strict V1/R4 runtime import root and storage isolation, no real order/network clients. B06 full negative fixture/test plan and permitted future code surface, old V1 parity and full unmodified CI. B07 audit invented timestamps, settlement IDs and date identities.
Clearly identify which invariants are just specified rather than implemented, remaining BLOCKER/HIGH and whether Option A is actually feasible. Do not modify code, create a trusted manifest or grant an executable R4 patch.

**Write ONLY** one new reviews/v0.6/b_line/V06_R4_1_P1D_C4_WAL_R3_INDEPENDENT_AUDIT.md on docs/v06-r4-1-p1d-wal-design-audit rooted at this exact dispatch commit. Terminal R3_DESIGN_REVIEW_PASS_WITH_LIMITS / R3_DESIGN_REVIEW_FAIL / INCOMPLETE. Regardless, P1D_IMPLEMENTATION_NOT_AUTHORIZED until later separate Controller L2.
