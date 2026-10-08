# B-line Test/CI Economy V1 — risk-based verification (2026-10-08)

Authority scope: **engineering workflow efficiency only**. This contract cannot modify frozen strategy success criteria, protected exposure budgets, pre-live approvals, production write permissions, or A-line procedures.

## Policy

Stop running full `pytest -q` at every push, Gemini edit, interim SHA check or docs-only change. Verification cost must be proportional to **changed behavior and risk**. A failed CI lint stage is **CI_STATIC_GATE_BLOCKED**, not a passing or failing test run; incomplete infrastructure is not policy-quality FAIL.

| Stage | Trigger | Required checks | Skippable at this stage |
|---|---|---|---|
| **L0 local loop** | Every small same-scope edit | changed-file Ruff; Python compile; diff/check; relevant unit tests when edited | all-suite pytest; coverage; compatibility matrix; repeated Git HEAD fetch |
| **L1 terminal implementation** | Once per coherent Gemini work package | targeted changed-module tests and callers; stateful/safety adversarial negatives; manifest of test selection + timing + SHA + env; statics on changed paths | unrelated H40/H41/A-line, full coverage, every Python version |
| **L2 Controller acceptance** | One final remote candidate SHA | confirm parent + changed paths + frozen boundary; review new semantic risk, inspect L1 machine evidence/CI; only rerun missing decisive tests | re-execution of identical passed work on identical SHA/env/test selection; broad legacy regression |
| **L3 authority-critical** | protected read/outcome, release RC, final TESTNET promotion, new trust/side-effect boundary | exact immutable runner/code/data/dispatch/policy/seal; independent negative tests, critical security/integration regression; selected full suite if cross-domain or release contract requires it; CI proof | blindly rerunning an unrelated full scientific suite |
| **L4 pre-live** | any real-funds capability request | dedicated independent safety audit; comprehensive live execution/reconciliation/cold-start tests; credentials/approval isolation; audited deployment receipt | any relaxation of real-funds authority or approvals |

**Safety exception:** a code path that can issue exchange writes, change durable approval state, unlock protected data or alter outcome semantics must run its decisive negative/positive contract regardless of test time. L3 is not "skip tests"; it is "run the right tests once against the right immutable release object."

## Standard test selection / change map

- `docs/**`, prompts, reviews, authority note text only: Markdown/JSON/schema/link validation; **no pytest** unless an authority contract or executable fixture changes.
- `scripts/rc2/validation/**`: new `tests/test_rc2_final_holdout_infra_repair_r1.py`, `tests/test_rc2_holdout_r3_runner_*.py`, `tests/test_rc2_holdout_harness_r2.py`, hermetic negative access/dispatch tests. No protected archives, no actual retry.
- `src/btc_quant_agent/market_watch/**`, Tactical rules: market_watch, shadow, tactical + relevant live CasePackage consumers.
- Live approval / intent / exchange gateway / supervisor changes: `tests/test_live_v1_*.py` in the affected safety domain, plus approval denial, stale intent, exact environment binding, pending protection, recovery/TOCTOU cases. Cross-module integration suite once at RC.
- `src/**` unclassified, shared infrastructure or pyproject dependency shifts: fail closed to broader regression or explicit Controller justified mapping, not "zero tests".
- Performance-only changes: reproducible before/after benchmark and semantic equivalence; do not conflate speed and strategy-quality.

## GitHub Actions redesign

- Automatic push/PR: run **FAST** profile only — static checks plus path-selected suites with fail-closed fallback. Do not run every scientific test twice on PR + push + review.
- `workflow_dispatch`: `focused`, `integration`, or `full` profile; full includes coverage only if requested. Must support exact SHA at release.
- Nightly or release-candidate boundary: optional broader suite once; release/TESTNET requires explicit verified exact SHA and focused critical E2E.
- CI failure baselines: enumerate known `EXE001` violations, allow **only** exact known legacy files provisionally; new/touched violations fail. Fix shebang versus executable mode once. Never use blanket `ruff --ignore` to hide newly introduced violations without differential check.
- Use cached pip wheels/venv keyed by Python+dependency lock and isolate test temp directories; cache only hermetic fixture data with content hashes, **never unsealed protected archives**.
- `pytest --durations=20` to publish top slow tests; tag deterministic unit, integration, performance, external/network, exchange/order, protected tests; later evaluate parallelization only on process-isolated, fixture-safe tests. SQLite/global monkeypatch/threading tests require serial checks until proven deterministic.
- Full coverage/compatibility matrices once per release or scheduled run, not every development edit. Python 3.12 is the accepted RC runtime; 3.13/later is optional compatibility, not substitute for 3.12 release certification.
- Keep reusable evidence receipt: `{commit_sha, parent_sha, test_selection, tests_collected, passed, failed, skipped, duration, python_version, platform, dependency_hash, CI URL, artifact_hashes, protected_reads:0}`. Cache pass evidence **only** when code SHA + tests SHA + env + data/fixture digest + verification contract exactly match. Failure never becomes cached PASS.

## Measurable review

Record local/CI setup, lint, test, and total durations by work package. Prioritize fixing (1) one-time historical Ruff EXE001, (2) unconditional all-suite duplicate runs, (3) slow hermetic test groups, (4) full research build dependencies in fast B-line jobs, (5) repeated independent exact-SHA hydration on non-L3 boundaries.

Initial soft targets (monitor, do not weaken validation to satisfy): L0 <30 s, L1 focused <2 min, L2 Controller review avoids rerunning CI; L3 bound by actual safety suite. Never replace a correctness assertion with a timing ceiling.

## Governance

DEVELOPMENT_FAST_PATH remains default. Dispatch one complete work package; Gemini performs same-scope fixes without repeated prompts, Luna deterministic validation, Sol novel semantic/safety review only, Astra exceptional independent pre-live/scientific audit. Testing evidence is not an authority grant. `REAL_FUNDS_WRITE_AUTHORITY=NONE` continues.
