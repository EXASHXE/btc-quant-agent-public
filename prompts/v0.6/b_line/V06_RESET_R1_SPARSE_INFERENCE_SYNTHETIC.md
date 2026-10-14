# P1 — F1–F3 Sparse Inference Synthetic Calibration R1

**Owner:** ChatGPT-0, B-line Primary Controller. **Authority:** exact immutable commit containing this prompt. Executors MUST fetch and verify that exact commit and file Git blob; do not substitute moving `v0.6-docs` or later branch heads. **Root doc parent:** `5d0e639f76d58f7adb3809801421e2b053955d91`. Separate worker worktrees and no overlapping writes. **All tasks remain G2_ALPHA_NO_GO / TESTNET_NOT_AUTHORIZED / LIVE_NOT_AUTHORIZED / REAL_FUNDS_WRITE_NONE.** No protected H39/H40/H41/Forward/Final Holdout, reserved OOS, owner data roots, private repos, accounts, credentials, real trading, historical outcome/price-label extraction, performance scoring, parameter sweeps, silent merges or backfill. Never self-attest independent review; report exact source/code/commit/blob SHAs and an honest terminal disposition.

**Owner:** Codex Sol High / statistical method analyst, separate from episode developer. **Independent reviewer:** ChatGPT-3 science Challenger. **Code base:** `13e3a710b137efeec2e21e3002f748834ec0cc22` (known P1A full green). New isolated branch `feature/v06-reset-r1-synthetic-inference-calibration`.

Original F1–F3 research authority `f25954b45577cebb7624fae86cd91df9071a87ab`; `scripts/strategy_research/g2_flow_funding_entries_r1/statistics.py` blob `f86ee6c20c8bc08f0e42dcb4d586b4d908290018` contains `b_se=max(b_se,1e-6)` within block max-|T| resamples. Previous simultaneous inference `SIMULTANEOUS_INFERENCE_UNCALIBRATED`; F3 development n=12 and observed proxy-positive descriptions do NOT establish Alpha, true causal Mark/basis increment or reliable coverage.

**WRITE EXACTLY TWO NEW FILES (ADD only):**
- `scripts/strategy_research/g2_sparse_inference_synthetic_calibration_r1.py`
- `tests/test_v06_g2_sparse_inference_synthetic_calibration_r1.py`
No modification to original F1–F3 `statistics.py`, legacy results, research experiment selection, future evaluation budget, H39/H40/H41 data or test identities. Do not open its historical trade-level data, use historical PnL, trade labels, event arrays, trial score JSON, or replay the old runner. Read immutable old *method source code* for method diagnosis only.

Implement deterministic **invented-data-only** negative and power simulation comparisons:
- original clipped-SE studentization vs at least one principled variance-degeneracy-safe method (e.g. nonstudentized block-mean max statistic or explicitly conservative bootstrap CI with zero-variance discipline);
- all-zero blocks, one event in 90%+ zero blocks, constant nonzero blocks, unequal block size, strongly clustered autocorrelation, degenerate null, heavy tails, sign-flipped null, multi-arm max correction and null FWER behavior;
- finite predeclared seeds, simulation count, known DGP, nominal alpha, CI empirical coverage, Type I error with Monte Carlo uncertainty, power only on synthetic planted effect with unambiguous units;
- compute an outcome-blind **future** support/power feasibility region across effective independent weeks/event-rate/cost noise. Do not pick method thresholds using old observed F3 returns or make an F3 significance claim.

Gate if no method controls under synthetic null: `METHOD_BLOCKED`, no remedy by 1e-6 floor tweak or dropping empty weeks. If method passes synthetic calibration, publish `METHOD_CANDIDATE_CALIBRATED_ON_SYNTHETIC_ONLY`; historical interval remains uncalibrated until entirely separately governed result use. Pre-reg-required methods/constraints must be documented in code docstrings and test report. All simulated values invented and explicitly declared.
Run actual targeted tests and reproducibility check with two seeds, capture exact SHA and no protected input. Independent scientist must review prior to later adoption.
