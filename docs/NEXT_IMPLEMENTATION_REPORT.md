# BTC Quant Agent v0.2.2 Research Hardening Report

## Release identity

- GitHub repository: <https://github.com/EXASHXE/btc-quant-agent> (private)
- Branch: `codex/v0.2.2-research-hardening`
- Baseline commit: `45f764b3d20ee4bbbb923a5b139b153e2c435026`
- Baseline tag: `v0.2.1-baseline`
- Implementation commit before this report: `e30dcfe7946cf9a103936738a80cb49b413e8432`
- Package/strategy/feature version: `0.2.2`
- Strategy status: `EXPERIMENTAL`
- Execution defaults: `disabled`, `auto_execute=false`, `allow_live=false`

## Audit findings and changes

### Correctness and causality

- OLD: SQLite connections used the native connection context manager, which commits or rolls
  back but does not close. NEW: the repository owns a context manager that commits, rolls back
  on exceptions, and always closes. WHY: remove the observed `ResourceWarning` and deterministic
  resource leak. EXPECTED IMPACT: stable daemon/database behavior under repeated scans.
- OLD: a signal immediately scanned all future 1m bars, resolved its final outcome, and used
  `busy_until` to skip intervening decisions. NEW: `EventDrivenBacktestEngine` advances one 1m
  event at a time through pending entry, fill, open position, invalidation, expiry, stop, target,
  funding and timeout states. WHY: live/backtest lifecycle parity. EXPECTED IMPACT: removes this
  lifecycle look-ahead and allows signals to be invalidated before fill.
- OLD: every decision rebuilt historical lists and every derivative as-of query linearly scanned
  its history. NEW: timeframe histories use bounded deques and derivative lookup uses sorted
  timestamps plus `bisect_right`. WHY: remove quadratic behavior and match live history limits.
  EXPECTED IMPACT: linear event traversal with bounded decision windows.
- OLD: estimated Funding was always deducted as a trade friction. NEW: backtests apply signed
  Funding cashflow only when a filled position crosses an explicit settlement timestamp; the risk
  engine separately reserves `funding_stress_rate × max_expected_funding_events`. WHY: separate
  realized cashflow from conservative risk budgeting.

### Data integrity

- Added `quantctl collect-derivatives`, immutable backward as-of snapshots, SHA-256 checksums,
  per-field coverage, event ranges and known-gap reporting.
- Candle downloads now write a companion data manifest. Formal research runs require a manifest
  and copy it into the run artifacts.
- `enable_order_book_factor=false` is the default across live, backtest and research. Order book is
  fetched only when explicitly enabled.
- Without supplied point-in-time derivatives, formal multi-year baseline runs explicitly disable
  derivatives and order book; D/E ablations are marked skipped rather than dynamically changing
  the score denominator and calling it the same strategy.
- Fixed an inherited `.gitignore` bug: `data/` matched `src/btc_quant_agent/data/`, so the baseline
  tag omitted the source data adapters even though they existed locally. The rule is now `/data/`
  and all package data modules are tracked on this branch. The published baseline tag remains an
  immutable record of the imported state.

### Execution and API safety

- Execution plan preparation and submission reject any signal whose `data_health != OK`.
- Both stages reload the latest closed 4H/1H/15m market state, refresh TTL/invalidation, and require
  the source signal to remain `ACTIVE`.
- Entry, stop and target use direction-aware tick rounding. Quantity is reduced if necessary and
  rounded risk plus friction and net RR are recomputed and stored in the immutable plan.
- Every API route requires `Authorization: Bearer <BTC_QUANT_API_TOKEN>`. The Skill HTTP wrapper
  requires and supplies the same token. The default Docker port remains localhost-only.
- `setup_score` is replaced by distinct `pattern_score` and `factor_score` fields. Old SQLite JSON
  containing `setup_score` remains readable and maps to the legacy factor score.

### Research tooling

- Added causal `quantctl replay` output with timestamp, price, 4H macro, 1H regime, 15m structure,
  EMA, support/resistance, factor groups/score, setup, decision and rejection reason.
- Added baseline splits by year, direction, setup and regime; A–E ablation; chronological 12/3/3
  walk-forward; final six-month holdout; factor-threshold stability; 1.0/1.5/2.0x cost stress;
  shuffle Monte Carlo; ordinary bootstrap and block bootstrap.
- Formal runs write `research_report.md`, `research_report.json`, `equity_curve.csv`,
  `trades.parquet`, `config.toml` and `data_manifest.json`, including Git SHA, versions, config
  hash, dataset checksum and random seed. Parquet output requires the `research` optional extra.

## Changed files

- Packaging/CI/config: `.env.example`, `.github/workflows/ci.yml`, `.gitignore`, `pyproject.toml`,
  `configs/default.toml`, `docker-compose.yml`, `CHANGELOG.md`, `README.md`.
- Core: `backtest.py`, `config.py`, `domain.py`, `engine.py`, `risk.py`, `service.py`, `storage.py`,
  `explain.py`, `research.py`, `cli.py`.
- Data: all modules under `src/btc_quant_agent/data/`, including new `collector.py`, `funding.py`
  and `manifest.py`.
- Execution/API/Skill: `api.py`, `execution/models.py`, `execution/service.py`, Skill instructions
  and `skill-template/scripts/quant_tool.py`.
- Tests: 10 existing test/helper files updated; new event-backtest, data-manifest, execution-guard
  and research suites added.

## Verification

- Python: 3.12.3 locally; GitHub CI matrix: 3.11, 3.12, 3.13.
- Tests: **89 passed**.
- `python -W error::ResourceWarning -m unittest discover -s tests`: **89 passed**.
- Coverage: **74% overall** (up from 70% while adding research/data/CLI code).
- Required core coverage: risk 100%, engine 95%, strategies 89%, regime 100%, backtest 92%,
  execution guard 93%. Execution service integration coverage is 59% and remains a testing gap.
- Ruff: passed.
- Mypy strict: passed, 35 source files.
- Compileall: passed for `src` and `skill-template/scripts`.
- Event backtest performance smoke: 100,000 synthetic 1m bars in **1.85 seconds**, maximum RSS
  **64,400 KiB**, with bounded 500/500/500 live-equivalent decision histories.

## Historical data coverage and research status

No historical market dataset was included in the uploaded archive. Therefore no 2021-to-current
baseline, ablation, walk-forward or final holdout result is claimed in this release. The collector,
manifest contract and research harness are ready, but the strategy remains `EXPERIMENTAL` and Edge
is unassessed. Funding settlement CSV columns are `timestamp_ms,funding_rate,mark_price`; derivatives
coverage must be genuine point-in-time observations and must not be backfilled from current values.

## Known limitations and remaining risks

- A formal research run still needs canonical continuous BTCUSDT 1m data, explicit funding events,
  and preferably a separately collected point-in-time derivatives interval. Large datasets and all
  generated artifacts are intentionally Git-ignored.
- The Binance derivatives collector is designed for recurring cron/daemon invocation from now
  forward; Binance's short history windows cannot reconstruct missing multi-year OI/taker history.
- Order-book evidence remains forward-experimental until reliable point-in-time L2 history exists.
- Intrabar stop/target ambiguity remains conservative: stop wins when both occur in one 1m bar.
- `execution/service.py` has lower integration coverage than the hard guard because exchange failure
  and failsafe branches require more signed-client scenario tests. Live execution remains disabled.
- No parameter, structure, indicator or validation gate was changed to manufacture a positive
  result. No profitability, win-rate or validation claim is made.
