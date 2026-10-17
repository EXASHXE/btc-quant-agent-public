# V065-P0 — Offline research vertical slice (execution-first R4)

**Dispatch:** Controller 0 → Codex Sol Max / Antigravity (Agy/Gemini); one primary implementer.  
**Task ID:** V065-P0-OFFLINE-RESEARCH-PIPELINE-01  
**State:** READY_FOR_IMPLEMENTATION; **NOT** a new reviewer or scientific admission task.  
**Project:** EXASHXE/btc-quant-agent-public, default \`v0.6.5\`.  
**Dispatch baseline:** \`v0.6.5@12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77\`, checked 2026-10-18. Refresh local and remote SHA and inspect dirty state before editing.  
**Working root:** \`/root/workspace/project/quant-0.6.5\` (do not create a branch/worktree by default).  
**Output:** real runnable offline research code + focused automated tests + actual repeatable demo, **not** another policy or design report.

## Owner R4 execution rules

Implement and test directly; no routine R1/R2/R3 audit cycle. Do not dispatch 1-A/2-R/2-C for ordinary integration. Controller can accept on diff, focused tests, and observable demo. At most one code writer for these paths.

**CRITICAL: PRESERVE EXISTING USER CHANGES.** The local checkout already contains 12 modified tracked role/status/docs files and 2 untracked Owner R4 documents/prompts (14 paths total). These edits are deliberately uncommitted. **Do not stash, reset, checkout, clean, overwrite, stage, autoformat, commit, cherry-pick, pull --rebase, or push these files.** Restrict edits to the P0 code/test allowlist below. If a separate agent concurrently edits an overlapping code path, stop and coordinate. Do not claim the shared checkout is clean. No \`AGENTS.md\` / \`GEMINI.md\` local-policy mandate.

## Verified code/data interfaces, reuse rather than rewrite

- Existing D2 QC+manifest v2 implementation: \`scripts/research/r11_d2/binance_core_pilot.py\`. Reuse \`qc_zip\`, \`qc_rows\`, \`verify_checksum\`, \`manifest_summary\` and existing format validation only where their contracts actually fit. The D2 CLI \`verify\` requires a writable workspace and writes \`reports/offline-qc.json\`; do **not** invoke it blindly over historic or protected data. D2 \`acquire\` is forbidden in this task.
- Existing causal clock: \`scripts/research/r11_d2/prospective_causal_clock.py\`, specifically \`PredeclaredSourceSet\`, \`SourceRequirement\`, \`ClockCalibration\`, \`SourcePolicy\`, \`SourceEvidence\`, \`evaluate_fixed_origin\`. Its strongest possible positive result is **\`CLAIMED_TIMING_ELIGIBLE\`**, NEVER an authenticated PIT source approval.
- Existing focused tests: \`tests/research/r11_d2/test_binance_core_pilot.py\` and \`test_prospective_causal_clock.py\`. Reuse existing synthetic fixture patterns; add only P0 coverage.
- Previously downloaded historical pilot artifacts are in Owner-approved \`/root/workspace/project/crypto-data/historical/r10-binance-vision/data\` and \`.../historical/r11-binance-core-pilot/data\`, with original R10/R11 report dirs outside Git. R11 offline QC previously reported 215 attempted/evaluated pilot objects and \`R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS\`, but this is **not** original receiver PIT or a source-rights grant. Check version/record integrity and never blindly promote an old \`offline-qc.json\` lacking a manifest v2 field.
- Production forward stores remain in protected \`Quant-agent\` and migration remains HOLD. Ignore them. Do not touch \`Quant-agent-sanitized\`, \`history\`, A-line/H39/H40/H41/Forward/Final/OOS, account data, TESTNET/LIVE, or any private credentials.

## Build exactly one useful P0 vertical slice

Implement an offline-only command-line entry point, preferably:
\`python3 -m scripts.research.r11_d2.offline_research_pipeline demo --output-dir <NEW_OUTPUT_DIR>\`

You may adjust the module name if integration makes this exact import unsafe, but demonstrate one **single working command** documented in your final handoff. Use Python standard library unless a dependency is already declared. No web, API or WebSocket calls.

Pipeline stages, with typed/structured outputs and stable failure reasons:

1. **Input identity + QC:** Load a small synthetic BTCUSDT fixture and perform meaningful positive/negative QC with D2-compatible schema/records. Reuse existing D2 QC/checksum logic where possible; do not invent a new incompatible checksum or label missing objects as PASS. Emit a compact QC verdict and manifest v2-like inventory; differentiate source file SHA-256, row QC, family/symbol/interval identity and source class. For optional \`inspect-existing\` mode, accept explicit **read-only** paths to frozen D2 report and historical ZIP files; never write alongside input, automatically fetch missing ZIPs, or assume a legacy report has manifest v2 provenance. If adding inspect-existing will delay core demo, put that follow-up outside P0 and ship the demo first.
2. **Fixed-origin decision clock:** Create a predeclared, outcome-independent origin grid (or explicit one-origin fixture set). Reuse the real \`evaluate_fixed_origin\` function with deliberately **synthetic, internally consistent** receiver/feature time claims. Do not synthesize such authenticated receipt claims for **real historical** objects. Label this lane \`DEV_SYNTHETIC_CLAIMED_ONLY\`; keep native source/role/source-age/ack requirements visible.
3. **Missing-Z no-action:** \`Z\` is one candidate feature sourced from native OI-like data, not a future outcome or an eligibility selector. If required Z is missing, stale, malformed, late, or its clock/manifest/period information is unknown, record exactly \`NO_ACTION\` with a stable reason code at the already-fixed origin. **Never** drop that origin from the denominator, forward-fill later Z, backfill causal clocks, invent a trade, or select a favorable subset. Even \`CLAIMED_TIMING_ELIGIBLE\` is **not** a trade signal; absent an independently preregistered strategy, action is still \`NO_ACTION\`.
4. **Outputs:** Produce a deterministic and machine-readable \`qc.json\`, \`manifest.json\`, \`origins.jsonl\` (one row for every scheduled origin, including no-action), \`summary.json\`, and a concise human CLI summary under the selected new output dir. Each origin includes fixed-origin id/time, required X/Z availability, claimed-only clock decision, final action, reason and source/manifest provenance. \`summary.json\` includes counts by action and blocker, known gates, run configuration/code identity where reasonably available, clear \`NO_ALPHA_ESTABLISHED\` and \`NO_TRADES_EXECUTED\`. Avoid self-referential file-hash loops.
5. **One demonstration:** Include at least four origins: an internally consistent claimed-timing fixture, missing Z, deliberately late/stale Z, and invalid QC/identity. **Every** origin appears in the output. Show fail-closed decision mapping. A positive claimed timing status may appear for the synthetic case but may NEVER be rendered as a real PIT-approved or trade-eligible status.
6. **Safe output:** Default to a caller-specified fresh folder under \`/root/workspace/project/crypto-data/research-dev/\` or a test \`tmp_path\`. Reject a protected input/output alias, existing non-empty output without explicit safe overwrite handling, and symlink escapes. Never commit raw market payloads or output files to Git.

## Test and acceptance (targeted, not full repo)

Implement tests at \`tests/research/r11_d2/test_offline_research_pipeline.py\` (and only the smallest necessary extension to existing tests/code). Cover:

- one CLI demo run exits 0, creates all expected files, valid JSON/JSONL, correct manifest identity/QC and summary counts;
- repeated isolated demo runs with the same seeded inputs produce byte-identical normalized **research outputs** (excluding intentionally variable runtime/path metadata, which must be separated);
- missing Z → NO_ACTION without deleting the origin; late/stale Z → NO_ACTION; malformed/unknown provenance → fail closed; no lookahead, no later-value fill;
- manifest/source hash mismatch and unsupported/legacy incomplete manifest v2 → bounded failure, never \`PASS\`;
- no live data/API/WS acquisition, no account/trading calls; tests use generated synthetic data or trusted, intentionally tiny test fixtures;
- no clobber of existing data, no traversal into protected or symlinked output paths.

Run a focused command such as:
\`python3 -m unittest tests.research.r11_d2.test_offline_research_pipeline tests.research.r11_d2.test_prospective_causal_clock tests.research.r11_d2.test_binance_core_pilot\`
(or \`pytest\` on the same exact files if already available). Do not run full repository tests by default. Demonstrate the new one-line CLI on a **fresh** output directory; report actual exit code, file names and action counts.

## Scope, write set and integration

Editable code/test targets only:
- \`scripts/research/r11_d2/offline_research_pipeline.py\` (new);
- \`tests/research/r11_d2/test_offline_research_pipeline.py\` (new);
- existing D2/clock modules/tests **only** if a verified minimal integration issue requires it.

Do not change anything in the 14 dirty Owner R4 paths. No new branch/worktree, PR, CI configuration, package install, systemd modification, collector or live data download. No automatic Git commit or push. Output a factual concise handoff: exact added/changed code paths, sample CLI, actual test counts, demo outputs, code diff, blockers and follow-up P1 dependency. Preserve all current live-data/PIT/economics/Alpha/TESTNET/LIVE/funds gates. **Controller handles ordinary code acceptance directly**; only escalate a genuinely consequential reproduced issue.

## Definition of done

\`P0_DEV_READY\` means a fresh one-line offline demo runs, performs D2-compatible QC/manifest checks, invokes the existing fixed causal clock, **keeps all origins including no-action** and emits deterministic machine-readable artifacts; targeted tests pass and the Owner's uncommitted documents are unchanged.

\`P0_BLOCKED\` means a concrete functional obstruction with an observed minimal reproducer. Do not substitute another process report for code.

**Hard gates unchanged:** SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE.
