# quant-agent v0.6 — Gemini NORMAL task: B-line CI Risk-Mapped Fast Path R1

MODE: **Gemini ordinary/standard mode, NOT Boost.** This is a bounded deterministic engineering task, not a long speculative architecture goal. Do not launch nested workers or open-ended reasoning loops. Implement, test, push and stop with verified evidence. Controller review [R3 and performance L2](https://github.com/EXASHXE/btc-quant-agent-public/blob/23a5e3ca99e4224550dfd04d44c908e4e38adaf1/reviews/v0.6/b_line/V06_GEMINI_R3_CODEX_AUDIT_AND_CI_ARCHITECTURE_OPTIMIZATION_CONTROLLER_L2_R1.md) is authority.

TASK_ID: V06_GEMINI_NORMAL_FAST_CI_RISKMAP_R1
REPO: EXASHXE/btc-quant-agent-public
BRANCH: feature/v06-bline-gemini-normal-ci-riskmap-fastpath-r1
EXACT_START_SHA: 97f4040b9380f2069575a989c066d1daeef15194
WORKTREE: /root/workspace/project/quant-v0.6/gemini-normal-ci-riskmap-r1
SCRATCH: /tmp/btc-normal-ci-riskmap-r1
ALLOWED_WRITES:
- scripts/ci/test_plan.py
- tests/test_ci_test_plan.py
- docs/engineering/ci_fastpath_r1/**
- evidence/v0.6/b_line/ci_fastpath_r1/**
NO OTHER WRITE PERMISSIONS. No changes to workflow YAML, business engine, R3 A/B/C source, protected old projects, test body outside planner tests or runtime safety policy. Never read/stat/list Quant-agent/data, Quant-agent-sanitized, H39/H40/H41/Forward protected data, heldout 2024–25 or old protected 2026 records. Don't connect Binance, local proxy, real LLM/Feishu, orders, funds or private API. No force push, merge or history rewrite.

## Why

On exact R3 SHA, GitHub Actions 38270967488 completed a real full suite: 3454 passed, 2 skipped, 9 warnings, 904.17s of pytest. Planner scripts/ci/test_plan.py classify() line 191–193 falls back full=True for any unmapped executable path. The new feed and bridge modules were never explicitly risk-mapped; thus even a 1-line bridge change triggers 15 minutes of costly H40/H41 full science testing. Locally the feed+bridge focused set (394) takes ~15.28s according to original executor. This is not an excuse to delete or skip scientific tests at release gates. The repository already has weekly/manual full CI and cancel-in-progress concurrency.

## Precise implementation

1. Add two **explicit independent ownership dependency matrices** to scripts/ci/test_plan.py:
   - Owner FEED: scripts/market_data/forward_public_feed_r1/** including the 2026 Binance /public and /market websocket routing, proxy_route.py, order_book.py, contracts.py, health.py, time_authority.py, replay.py, durability.py, cli.py. Minimum focused tests: existing tests/test_v06_forward_public_feed_r1_*.py PLUS all tests/test_v06_market_event_bridge_r2_*.py (because downstream uses source timestamps, book, funding, contracts) and tests/test_ci_test_plan.py if boundary map changes.
   - Owner BRIDGE: scripts/integration/market_event_bridge_r2/** including bridge_engine, portable_ci_refs, Mark, book, funding, source_qualification, CLI. Minimum tests: existing tests/test_v06_market_event_bridge_r2_*.py PLUS tests/test_v06_forward_public_feed_r1_*.py. Add exact downstream consumer interface probes already in bridge test files; if there is no true pinned B/C test, do not invent one. Do not include heavy H40/H41 by accident.
   - Narrow script namespaces with no guaranteed owning tests remain FULL. Never use general scripts/** or all tests/** exemptions.
2. Path matching must be robust to Windows separator/path traversal and Git rename/delete. Unknown executable source, new standalone critical source area, changed pyproject.toml/pytest.ini/tests/conftest.py, deleted/renamed production/test source, unknown merge-base and test selection empty -> FULL or fail-closed; under no circumstances count deleted tests as sufficient focused coverage.
3. If a Python test file changes directly, select it **and** dependent owner tests when its name belongs to existing FEED or BRIDGE suites. If its associated owner source also changes, select union. File deletion should force full even though old file cannot be loaded.
4. Two new exact ownership maps must survive adding new Python files inside *known* owner roots. But dangerous broad changes to *shared* project-level schemas or clock/wallet base modules cannot use the owner map without additional independent tests. If unable to prove dependency coverage, keep FULL.
5. Existing tests/test_ci_test_plan.py scenarios (all 12 old cases) must pass unmodified. Add >=35 meaningful new pytest cases covering:
   - every public FEED file category -> focused with both suites;
   - every BRIDGE file category -> focused with both suites;
   - same-commit FEED+BRIDGE+changed tests union, stable dedup/order;
   - CI-only -> only CI planner tests, docs-only -> no business tests;
   - unknown source -> full, test directory deletion/rename -> full, malformed Git baseline -> full;
   - critical pyproject/pytest.ini/conftest -> full;
   - misclassified config or shared domain -> existing domain full/dependent risk mapping, not escape;
   - forced PROFILE full must still choose entire unfiltered suite;
   - mandatory compatibility release full/weekly full unchanged;
   - explicit simulation of code changed + test removed => full;
   - evidence-only addition with no source edit should not install huge test dependency graph;
   - receipt contains exact revision SHA and chosen source/test path set.
6. Make executable dry-run test plan fixture using synthetic path lists: A single diff containing modified bridge_engine and cli must select both FEED and BRIDGE, count includes their tests and must NOT choose H40/H41; source unknown must choose full. Write JSON risk map matrix and tests to protect decisions from regression.
7. Distinguish local targeted suite from final release assurance. Preserve existing workflow dispatch and weekly full; **do not weaken standard full CI**. A downstream Controller must still run final exact-SHA full once before merging protected behavior changes. This task cannot authorize bypass of that gate.
8. Benchmark: record baseline full run from 38270967488 (904.17s) and real focused benchmark measured on same machine. Clearly separate pytest runtime from pip installation/workflow overhead. Target <=60s focused pytest in clean developer environment but if measured longer, report actual; no fake speedup claims.
9. Run locally first: Ruff on touched Python, compileall on scripts/ci+tests/test_ci_test_plan, pytest -q tests/test_ci_test_plan.py --noconftest. Then optionally dry-run full and focused plans from synthetic diffs. Only 1 final GitHub push (with at most 2 commits) after local tests to avoid repeated 15-minute GH runs. Recheck actual GitHub run head SHA, planner mode and test step execution. If CI is focused, do not misreport 3454 all tested. The old R3 exact SHA already has a green full baseline; final new planner branch must be independently reviewed before taking over production CI.
10. Record initial and final test file-count, selected coverage, git diff, no restricted paths touched. JSON receipts and report need precise file and commands.

Deliverables:
- Updated scripts/ci/test_plan.py and tests/test_ci_test_plan.py only.
- docs/engineering/ci_fastpath_r1/MAPPING_AND_SAFETY_RATIONALE.md
- docs/engineering/ci_fastpath_r1/BENCHMARK_AND_RELEASE_GATES.md
- evidence/v0.6/b_line/ci_fastpath_r1/BEFORE_AFTER_RISK_PLAN.json
- evidence/v0.6/b_line/ci_fastpath_r1/TEST_AND_CI_EXACT_SHA.json

Terminal response fields:
TASK_ID / MODE=NORMAL / BRANCH / START_SHA / FINAL_REMOTE_SHA / COMMITS_PARENTS / CHANGED_SCOPE / FOCUSED_SUITE_NUMBER / LOCAL_TEST_PASSED_FAILED_SKIPPED / BASELINE_FULL_SEC / FOCUSED_PYTEST_SEC / CI_RUN_HEAD_SHA / CI_JOB_TESTS_EXECUTED / UNKNOWN_PATH_FAIL_CLOSED / DELETION_RENAME_FAIL_CLOSED / FULL_RELEASE_GATE_RETAINED / PROTECTED_PATH_READS=0 / PRIVATE_NETWORK_CALLS=0 / TERMINAL=FASTPATH_MAPPED_VALIDATED or FASTPATH_BLOCKED_EVIDENCED.

Do not start another long architecture review or rewrite modules. Once scoped owner mapping works and negative tests pass, commit and finish.
