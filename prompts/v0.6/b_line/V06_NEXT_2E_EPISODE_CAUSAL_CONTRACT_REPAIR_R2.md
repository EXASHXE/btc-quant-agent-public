# ChatGPT-2-E — Canonical episode causal input repair R2 (synthetic only)
Task owner: ChatGPT-0 B-line Controller; governance: five sessions 0/1/2-R/2-C/2-E. Authority is the immutable Git commit containing this task, to be resolved and verified by the executor. Work only from the stated source SHA on a new isolated branch; record real Git blob, parent, diff, test commands, CI, and remote PUSH_VERIFIED. No self-certified independent acceptance or automatic merge. Forbidden: H39/H40/H41/Forward/Final protected contents, reserved outcomes, local owner data roots, historical PnL trials, market collection, private exchange/account access, TESTNET/LIVE and monetary write operations. G2_ALPHA_NO_GO; SOURCE_NOT_ADMITTED.

Base exact frozen code a144640acda5340b2b120ad5a451c3d193dea81c, parent 13e3a710b137efeec2e21e3002f748834ec0cc22. Independent audit exact SHA 60ec10e6a039482a14f36fa4eef1035adc9da8e1, blob 0bcc33d0bc19124223442bf87c9088a90dd6e436; verdict EPISODE_SYNTHETIC_REVIEW_FAIL. Source module blob bf944dd2bcdb1d844f2ab91834e0c9b1703383fd; tests blob d2101ef53e5ad07a41177d7758599659d7901071. Use branch feature/v06-next-episode-causal-input-repair-r2.

ONLY MODIFY these two existing paths:
scripts/strategy_research/g2_next_episode_identity_r1.py
tests/test_v06_g2_next_episode_identity_r1.py
No new file; no old research/CI/holdout or market source. No real numeric opportunity measurements. Stay deterministic on invented clocks.

Implement four witnessed fixes without trading/strategy redesign:
E01: A confirmation must carry an unambiguous completed bar identity/window and receiver-known-at witness; 30m 12:00–12:30 cannot be used at 12:05, prior 11:30–12:00 may qualify when first received. Fail closed if proof unavailable; do not trust caller CONFIRMED alone.
E02: an invalid FUTURE_STATE must not mutate lineage/cohort. Clarify explicit seed reservation separately from invalid confirmations; valid later seed must remain eligible under appropriate rearm rules, while legitimate precommitted provisional seed remains protected.
E03: required price/confirmation/quote/OI source evidence windows must not overlap missing/censored gaps; decision-second-only gap check is insufficient. Distinguish optional OI absent UNKNOWN from proven complete OI.
E04: do not present an arbitrary source_identity_hash string as a cryptographically verified data-manifest hash. Either verify canonical hex digest plus external witness flag (which itself cannot prove provenance without source receipts) or rename/explicitly tag a SYNTHETIC_OPAQUE_ID and fail closed before source-qualified counts. Preserve backward-compatible synthetic fixtures only if they cannot be mistaken for admitted source.

Begin with 4 real RED synthetic regressions from the independent audit, then implement and GREEN them and preserve all prior canonical-ID/permutation/side/cooldown/occupancy/clock unit tests. New fields must be versioned or explicitly breaking; do not silently reinterpret existing seed/alert records. Explicitly keep rate_status=RATE_NOT_ADMITTED. Run focused pytest on both source/test fixtures and available lint; run full unmodified CI only if practical, reporting known H40 failure honestly.

Output remote exact final SHA + path/blob diff, four RED/GREEN commands/results, policy/shape version and independent review request. Terminal EPISODE_R2_READY_FOR_INDEPENDENT_REVIEW / CONTRACT_REDESIGN_REQUIRED / FAIL. If E01–E04 cannot be safely resolved in only two files, stop; do not dilute requirements.
