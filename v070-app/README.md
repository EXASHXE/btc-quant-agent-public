# Quant v0.7.0 — Public Code Review Snapshot (2026-11-09)

**Purpose:** Owner-requested, immutable-style public review of the *current accepted offline application code*. This is not a second documentation authority, a production deployment, a native research release or a statement of trading profitability.

## Contents and provenance

- \`src/btc_quant_agent\` and \`src/program_c\`: complete accepted Program O application/evaluator source as present in \`lt-program-o-clock-remediation-01\`.
- \`tests/\`, \`tools/\`, \`configs/\`, \`contracts/\`, \`fixtures/\`, \`inputs/\`, \`deployment/\`, \`pyproject.toml\` and operator READMEs: associated offline build/testing/configuration/packaging source and known synthetic fixtures.
- \`diagnostics/clock-p2/\`: separate experimental host-diagnostic source from the failed P2 WSL time-service intervention. Not an application production dependency. **Do not execute host service changes from these tools for a code review.**
- \`SNAPSHOT_MANIFEST.json\`: SHA-256 and byte size of every copied file, source lineage and exclusions.

No native exchange payloads, account details, signing keys, sealed evidence, protected holdout rows, runtime virtual environments, compiled wheel bundles, cached objects or unrelated R/M/Q worktrees are exported here.

The snapshot was copied without refactoring: **duplicate resource files, old compatibility layers, and overlapping CLI paths are intentionally retained** for an independent reviewer to identify. Do not delete them from the original project based only on this snapshot.

## Current engineering qualification

Program O: 0-C accepted only the offline operational clock contract, with 672 distinct offline regression cases reported. S1/Shadow/dashboard source and scenario tests have prior offline scoped acceptance. One real public REST capture in Program N passed HTTP transport but failed the clock gate before source admission. Program P2 stopped the guest timesyncd service under exact Owner approval; a control-clock failure after ~3.29 seconds forced rollback. The actual host, real source and real Shadow remain **NOT QUALIFIED**. No after-cost strategy edge has been established.

This snapshot does not contain the full authenticated Controller evidence body; refer to the dated public planning summary and original local receipts. Its manifest proves byte copying, not acceptance of a different platform.

## Reproduction and review (offline-safe)

From this directory, in a disposable Python 3.11+ virtual environment:

\`\`\`bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q src tests tools deployment
\`\`\`

The package has optional \`public\` dependencies for REST adapter experiments. Unit tests may exercise mocks/synthetic fixtures. **Do not run live scans, native diagnostics, service-stop tools, or any real exchange requests** as part of outside review. Do not supply personal API keys.

Core entry points after installation are \`quant\`, \`quant-native\`, and \`quant-qualification\`; only inspect documented offline \`--help\` and mock/demo paths unless independently authorized.

## Where to start reviewing

1. \`src/btc_quant_agent/platform/unified_cli.py\` and \`platform/core.py\` for entry points.
2. \`platform/live/{cli,rest,source,operational_clock,swing_review,product}.py\` for bounded venue read-only intake and review policy.
3. \`platform/{regime,rc_strategy,rc_store,rc_operator,rc_dashboard,qualified_source}.py\` and \`src/btc_quant_agent/indicators.py\` for decisions, risk and persistence.
4. \`src/program_c/\` for source-neutral economic methodology, costs and first-passage outcomes.
5. \`tests/\`, \`fixtures/\`, \`contracts/\` for test seams and duplication.
6. \`diagnostics/clock-p2/\` for the unqualified WSL clock investigation.

Authoritative forward planning and review request:
- https://github.com/EXASHXE/btc-quant-agent-public/tree/docs/engineering
- [Dated status](../docs/project/V070_STATUS_AND_HANDOFF_20261109.md)
- [Intraday MVP roadmap](../docs/project/V070_INTRADAY_MVP_ACCELERATION_PLAN_20261109.md)
- [Independent review prompt](../prompts/v0.7/V070_EXTERNAL_FULL_CODE_STRATEGY_REVIEW_20261109.md)

## Inherited study and access constraints

This snapshot is public, read-only for reviewers. No user-account actions, auto trading or trade execution. Never open or infer restricted 2024/2025/2026 historical research, 2026-02-01 to 2026-08-01 FINAL_HOLDOUT, or original R/M/Q raw payloads. Do not transform synthetic performance into market Alpha. Any source, signed grant, host qualification, timestamps and legal venue usage must be independently verified.
