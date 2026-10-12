# B-Line CI Risk-Mapped Fast Path R1 — Benchmark and Release Gates

## 1. Baseline Full Suite vs. Focused Fast-Path Benchmark

All local measurements were collected on the same developer workstation (`/root/workspace/project/quant-v0.6/gemini-normal-ci-riskmap-r1`, Python `3.12.3`, Linux x86_64) against exact Gemini R3 baseline SHA `97f4040b9380f2069575a989c066d1daeef15194` and Fast-Path R1 code SHA `1e5eb35afef0c20ad0e45585c3648024919cda76`.

| Execution Scope | Reference Run / Command | Test Files Selected | Pytest Cases Executed | Pytest Runtime (s) | Pip / Workflow Overhead |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Baseline Full Suite (GitHub Actions R3)** | [GH Actions Run `38270967488`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38270967488) (`97f4040b`) | 196 (unfiltered `pytest -q --durations=20`) | 3,454 passed, 2 skipped | **904.17s** (15m 04s) | ~45–75s (`actions/checkout`, `setup-python`, `pip install -e '.[dev,research]'`, `ruff`, `mypy`, `compileall`) |
| **Focused FEED + BRIDGE Coupled Suite (Local Executor R3 Report)** | Original R3 executor local benchmark (`97f4040b`) | 21 (`12 FEED + 9 BRIDGE`) | 394 passed, 0 skipped | **15.28s** | 0s (pre-installed local environment) |
| **Focused FEED + BRIDGE Coupled Suite (Measured Local R1)** | `PYTHONPATH=src pytest -q --durations=20 tests/test_v06_forward_public_feed_r1_*.py tests/test_v06_market_event_bridge_r2_*.py` | 21 (`12 FEED + 9 BRIDGE`) | 394 passed, 0 failed, 0 skipped | **15.03s** | 0s local (`<= 60s` target satisfied with 44.97s margin) |
| **Focused CI Planner Self-Test Suite (Measured Local R1)** | `python3 scripts/ci/test_plan.py run --profile focused` (`1e5eb35a`) | 1 (`tests/test_ci_test_plan.py`) | 52 passed, 0 failed, 0 skipped | **0.72s** (`1.094s` subprocess wrapper) | Tiny CI-only install (`pytest`, `ruff`) when diff is strictly CI-only; full `.[dev,research]` + `mypy` when accompanied by docs/evidence |

### Separation of Pytest Runtime vs. Workflow Overhead

- **Raw Pytest Runtime Reduction (FEED/BRIDGE changes)**: `904.17s -> 15.03s` (a `60.16x` reduction in pytest execution time, saving ~14.8 minutes of H40/H41 scientific discovery/holdout test execution per push on scoped FEED/BRIDGE commits).
- **GitHub Actions Workflow Overhead**: On GitHub Actions `ubuntu-latest`, when a commit touches `scripts/market_data/forward_public_feed_r1/**` or `scripts/integration/market_event_bridge_r2/**`, the job still executes `actions/checkout@v4`, `actions/setup-python@v5`, `pip install -e '.[dev,research]'`, `ruff check`, `mypy`, and `compileall` before invoking `python scripts/ci/test_plan.py run --profile focused`. That workflow/environment setup overhead is independent of pytest runtime and is never conflated with the `15.03s` pytest figure.

---

## 2. Preservation of Mandatory Release Gates & Full CI

Fast-Path R1 accelerates iterative developer feedback on scoped FEED and BRIDGE commits; **it does not weaken, replace, or authorize bypassing standard full release assurance**:

1. **Forced `PROFILE=full` Manual Gate (`workflow_dispatch`)**:
   - `.github/workflows/ci.yml` retains `workflow_dispatch` with `inputs.profile: [focused, integration, full]`.
   - When `PROFILE=full` is selected, `scripts/ci/test_plan.py` overrides `plan["mode"]` (`mode = args.profile if args.profile != "focused" else plan["mode"]`) and invokes unfiltered `pytest -q --durations=20 --junitxml=ci-junit.xml` across all 196 test files (3,454+ tests), plus the `compatibility` matrix job across Python `3.11` and `3.13`.
2. **Weekly Scheduled Full Gate (`schedule`)**:
   - `.github/workflows/ci.yml` retains `cron: "21 3 * * 1"` which forces `PROFILE=full` automatically every week.
3. **In-Flight Concurrency Cancellation**:
   - `.github/workflows/ci.yml` retains `concurrency: group: ci-${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`.
4. **Controller Exact-SHA Full Release Gate Authority**:
   - Focused CI execution (`394` tests for FEED/BRIDGE or `52` tests for CI planner) must never be reported as full-suite (`3,454` tests) verification.
   - Before merging any protected behavior change or promoting this planner branch into production CI authority, a downstream Controller must still execute and review an exact-SHA `full` gate when required by governance.
