# Codex Sol High — Implement risk-gated quarantine of one known H40 digest test from routine B-line engineering CI

**Controller:** ChatGPT-0. **Authority:** immutable publication SHA of this file and sibling L2 decision; verify both exact file blobs before writing.
**Implementation code base:** `13e3a710b137efeec2e21e3002f748834ec0cc22`. **Allowed branch:** `repair/v06-bline-ci-single-h40-node-quarantine-r1`, isolated from other tasks.
**ONE exact eligible node:** `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`.

## Required architecture

Introduce an explicit `B_LINE_ENGINEERING` CI execution mode, distinct from `focused`, `integration`, and **unchanged manual/scheduled `full`**. It exists solely to allow day-to-day B-line regression work when code-change ownership is verifiably B-line-only. Use BOTH actual Git diff paths and a documented strict finite allowlist. Do NOT use branch naming alone, and do NOT interpret unknown as safe. Preserve all other tests and full global safety gates. The exact single H40 node must still be executed by A-line/full/RC/TESTNET preflight flows. Do NOT `-k not h40`, disable the H40 package, alter/test.skip protected node, or paper over any pytest/JUnit failure.

Allowed edited code files (modify ONLY):
`.github/workflows/ci.yml`
`scripts/ci/test_plan.py`
`tests/test_ci_test_plan.py`

No other new or changed paths. No H40/H41/source/golden test modifications, no `pyproject.toml`/pytest.ini changes and no unrelated refactor. Use the original fail-closed risk-plan design; ineligible or unknown change => run full unquarantined, NEVER downgrade to `focused`. Eligible B-line file examples are explicitly scoped `scripts/strategy_research/g2_*`, `scripts/g1_offline_preview_r1/*`, `scripts/g1g3_offline_ports_r1/*`, corresponding `tests/test_v06_*`, and allowed B-line docs/evidence paths, subject to stricter shared-safety and excluded subpath checks. The mere `tests/test_v06_` prefix is not sufficient: inspect ownership and test-role concerns, and fail closed for any file that can modify H40 dependency resolution, test collection, global conftest/fixtures, scientific scoring or release/integration safety. Prove existence of a nonempty resolved file diff and no disallowed path. Treat rename/delete of any critical file as ineligible, including src→docs and test→docs. Prefer a central function `eligible_bline_h40_quarantine(changed_paths)` with exhaustive synthetic unit cases, rather than duplicated workflow YAML logic.

Implementation must produce two clearly named status contexts/job results or an auditable named machine receipt:
- `B_LINE_ENGINEERING_PASS_H40_QUARANTINED` ONLY after full non-exempt suite passes, exactly one deliberate pytest deselection recorded with full node ID and code SHA, unknown-path test selection proof.
- `FULL_REPO_PASS` ONLY after genuine **unmodified complete** global test run passes; original H40 test included.
The quality/compatibility manual full jobs and weekly schedule **must not** silently route to the new mode. If a workflow reuses jobs, explicitly protect full behavior at profile=full and schedule; full parity at all 3 Python versions.

Fail closed if deselected count is other than 1, if the node name changed, the test is not collectible, JUnit missing, path owner unproven, unknown Git base, H40-only changes, protected scientific/code changes, test harness changes, or more than this one H40 failure. All non-H40 failures including `G1_CORE_MUTATED`, PIT/funding/WAL, safety/cost, other H40 test IDs remain blockers. Report the exact deselection as a QUARANTINE, not successful test execution. A-line's unresolved digest regression must stay separately visible with source URL and owner.

## Required negative/positive tests and CI observations

Invent test plans for: (1) permitted source-only B-line changes with exact one deselection, (2) doc-only fast path untouched, (3) H40/H41/source/science changes fall back full, (4) shared source & protected safety change falls back full, (5) unknown/unfetched base, (6) absent H40 node, (7) renamed/deleted test or source to docs, (8) manual workflow_dispatch full and weekly scheduled full untouched, (9) CI self modification cannot enable quarantine, (10) no bypass on P1D's unrelated `G1_CORE_MUTATED`. Record before/after tests and stdout; do not claim "RED" unless really observed failing test.

Existing public examples: full success [38494710188](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38494710188) on code base and failure [38513033356](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38513033356) for `c7c8d985...`, 3006p/1f/2s, one named H40. P1D [38446896902](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38446896902) had unrelated C4 plus H40 failure. Do not look into protected H40 source/holdouts. CI self-PR may still be red on full gate: publish exact attempted profiles and JUnit rather than hiding it.

Run actual local unit tests for `tests/test_ci_test_plan.py`, relevant CI planner lint/compile, and demonstrably distinct B_LINE_ENGINEERING vs FULL profiles using fabricated or repo-public test-fixture paths only. If a path cannot safely be excluded and all other suites selected, STOP `SCOPE_DESIGN_BLOCKED` and provide the minimal issue rather than force a green status. No merge, no branch policy change, no auto TESTNET.

**Receipt:** exact new commit SHA, parent, three-or-fewer-file diff, all focused tests and CI run URLs, explicit exemption count, changes in status names and true full-job handling, terminal `BLINE_H40_QUARANTINE_IMPLEMENTED_PENDING_INDEPENDENT_REVIEW` / `SCOPE_DESIGN_BLOCKED` / `FAIL`. Require independent reviewer, and Controller L2 before any required-check switch.
