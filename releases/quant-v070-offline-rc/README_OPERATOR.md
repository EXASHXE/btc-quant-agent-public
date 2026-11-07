# Quant v0.7.0 unified offline release candidate

Controller acceptance PENDING. Source, Shadow and economic qualification FALSE.
Native admission is NATIVE_BLOCKED_AUTHORITY. Account is ACCOUNT_UNKNOWN/ACCOUNT_VETO.
Only S1 trend_pullback is active; S2/S3 are RESEARCH_ONLY_DISABLED.
The CLI makes no account, market, order or alert request and starts no collector.

Use Python 3.11+ in this directory. This delivery was tested on Linux/Python 3.13;
Windows commands are provided but native Windows execution is NOT_RUN.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/requirements-lock.txt
.venv/bin/quant doctor
.venv/bin/quant replay --output artifacts/my_demo
.venv/bin/quant status --output artifacts/my_demo
.venv/bin/quant dashboard --output artifacts/my_demo
.venv/bin/quant recover --output artifacts/my_demo
.venv/bin/quant export --output artifacts/my_demo
.venv/bin/quant evaluate --input artifacts/my_demo/latest-program-c-episode-export.json --output artifacts/my_evaluation
.venv/bin/quant replay --all-no-setup --output artifacts/my_negative
```

Outputs must stay below the current operator working directory. Choose a fresh
evaluation output: C never silently overwrites reports. Replay uses deterministic
synthetic inputs and is idempotent. Existing state is append-only and verified.
Open `artifacts/my_demo/initial/latest.html` and `artifacts/my_demo/latest.html`;
`state.sqlite` is the durable store; `latest.json` is a recoverable projection.

Manual review once or twice daily (00:00 and 12:00 UTC schedule):

```bash
.venv/bin/quant ingest --output artifacts/my_manual
.venv/bin/quant review --output artifacts/my_manual --symbol BTCUSDT --trigger-ms 1793923200000 --decision-ms 1793923201000
# Repeat review for ETHUSDT and SOLUSDT using the same fixture clocks.
.venv/bin/quant observe --output artifacts/my_manual --episode-id EPISODE_ID_FROM_REVIEW
```

The example times and later observations are fabricated. `observe` only appends
the bounded synthetic fixture. Decisions use completed 1D/4H bars (60 each);
optional 1H confirmation does not replace warmup. Holding horizons are 4–120 hours.
A review does not confirm an actual account position. Plans can expire before
review; a candle touch is not a fill. Planned/after-cost R is ex-ante geometry.
The producer TARGET_FIRST and evaluator MISSING_COVERAGE describe different
claims; the integrated evaluator keeps INSUFFICIENT_SUPPORT and zero real samples.

For source checkout without a wheelhouse:

```bash
python3 -m pip install .
quant doctor
python3 -B tools/build_release.py
PYTHONPATH=src python3 -B tools/offline_pytest.py -q -p no:cacheprovider --basetemp=audit/operator_tests
python3 -m ruff check src tests tools
python3 -m mypy src/btc_quant_agent/platform/swing.py src/btc_quant_agent/platform/swing_store.py src/btc_quant_agent/platform/swing_view.py src/btc_quant_agent/platform/unified_cli.py src/btc_quant_agent/platform/evaluation_adapter.py src/btc_quant_agent/platform/native_preflight.py src/btc_quant_agent/platform/owner_verifier.py src/program_c
```

`tools/build_release.py` uses already installed dependencies and an existing pip
cache only; it fetches nothing. It verifies RECORD hashes, builds the wheel twice
with SOURCE_DATE_EPOCH, and emits a pinned hash lock. Reconstructed dependency
wheels are labeled host artifacts. Native wheels in this local packet target
Linux/Python 3.13; other platforms must create their own qualified dependency
wheelhouse. The Python source/configuration uses portable relative paths.
PowerShell uses `.venv\Scripts\quant.exe`; set `$env:PYTHONPATH="src"` for source tests.

The public code candidate excludes local artifacts, dependency binaries, trust
files, signatures and raw native evidence. `docs/engineering` remains the sole
canonical planning-document authority. No deployment or native experiment is
started by installation. See D5/D6 local receipts for unresolved authority,
rights, TLS, clock, retention and prospective warmup requirements.
