# Quant exploratory MVP — manual read-only operation

Use EXPLORATORY_MVP for hypothetical4–24hour/1–2day market-side reviews. STRICT_RESEARCH remains the accepted native/research path. Neither mode authorizes trading, accounts or alerts. S1 trend_pullback only; S2/S3 disabled. All Source/Shadow/Economic qualification flags remain false in the exploratory product.

## Install and run the deterministic example

From this release directory, with the tested Linux x86_64/CPython3.13 environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/requirements-lock.txt
.venv/bin/quant mvp doctor
.venv/bin/quant mvp demo --output work/positive
.venv/bin/quant mvp status --output work/positive
.venv/bin/quant mvp episodes --output work/positive
.venv/bin/quant mvp dashboard --output work/positive
.venv/bin/quant mvp recover --output work/positive
```

Open `work/positive/dashboard/latest.html` in a local browser. The demo is explicitly fixed historical SYNTHETIC data; its BTC ARMED and ETH/SOL NO_SETUP are not current signals. A single SQLite file `work/positive/mvp.sqlite` retains immutable data, original timestamps, plans, clock holds/reconciliations, lifecycle and observation evidence. `dashboard/latest.json` retains full proof; terminal output omits bulky bar prefixes.

Run later synthetic observations and the economic evaluator:

```bash
.venv/bin/quant mvp demo-followup --output work/positive
.venv/bin/quant mvp observe --output work/positive --episode-id EPISODE_ID_FROM_EPISODES
.venv/bin/quant mvp evaluate --output work/positive --report-output work/evaluation_new
```

The followup creates a finite fabricated later path, then uses the existing Shadow/first-passage logic and C method. A target touch is conditional market-side evidence. Missing mandatory source coverage cancels the lifecycle, the original plan remains unchanged, and C returns INSUFFICIENT_SUPPORT. No fill, executable/realized R or profit is inferred. An interrupted import can be resumed with recover (or reimport the same packet), after revalidation and a fresh actual durability stamp; an incomplete import never counts as admitted data. Every evaluate output path must be new. After reopening the CLI the same source, decisions and episode IDs persist.

Other complete examples:

```bash
.venv/bin/quant mvp demo --output work/no_setup --scenario all-no-setup
.venv/bin/quant mvp demo --output work/reconciled --scenario clock-reconciled
.venv/bin/quant mvp demo --output work/blocked --scenario clock-blocked
```

The reconciled example first detects a1760ms jump and holds all new candidates, then verifies a second deterministic snapshot and complete mandatory bars, records a separate exploratory clock epoch and resumes with CLOCK_DEGRADED_RECONCILED still displayed. It is QA only, not an independent Owner/auditor attestation or a repair of this WSL host. The irreconcilable example remains MVP_DATA_NOT_READY. Dataset content is never rewritten to make it pass.

## Separately authorized real-data imports

Current genuine data/rights/trusted import authority are absent: **MVP_DATA_NOT_READY**. No MVP command opens an exchange socket, downloads history or fetches a time endpoint. Do not use protected research/FINAL_HOLDOUT, original worktrees or private-account data. A future source adapter needs independent applicable rights and source-specific access authorization first.

```bash
.venv/bin/quant mvp init --output work/authorized
.venv/bin/quant mvp import --output work/authorized --dataset /approved/current_dataset.json --permission /approved/signed_import_permission.json
.venv/bin/quant mvp reconcile --output work/authorized --dataset /approved/independent_witness.json --permission /approved/signed_witness_permission.json
.venv/bin/quant mvp review --output work/authorized --holding-hours 24
.venv/bin/quant mvp status --output work/authorized
.venv/bin/quant mvp episodes --output work/authorized
.venv/bin/quant mvp observe --output work/authorized --episode-id ORIGINAL_EPISODE_ID
.venv/bin/quant mvp dashboard --output work/authorized
.venv/bin/quant mvp evaluate --output work/authorized --report-output work/authorized_evaluation
.venv/bin/quant mvp limitations
```

The external dataset schema is H_COMPLETED_DATASET_V1. `dataset.json` from a demo is a concrete schema example, never a lawful real-data authorization. Real imports use H_AUTHORIZED_IMPORT_UNQUALIFIED; synthetic imports are restricted to exact built-in deterministic fixtures, so arbitrary real data cannot be relabeled synthetic. Store evidence classes cannot be mixed. Completed archive rows and original combined WS events are supported. WS events require explicit `k.x=true`, exact outer/inner symbol and stream/interval identity, `T+1` end, alignment and valid finite OHLCV. Original source event may be UNKNOWN for an archive; the limitation remains visible. No publication timestamp is fabricated.

Each package has source_id, capture_origin, transport_provenance, rows and a fresh source Reference: lower_ms/upper_ms, received_mono_ms, boot_id and provenance. Bounds are independently supplied in the importing host's actual monotonic/boot domain, width<=5000ms and age<=300s. They are a labelled low-frequency reference, not strict100ms UTC qualification. Each row retains original source event and receive/available/durable wall+monotonic clocks. The compiler view conservatively uses source snapshot upper-bound availability; it does not rewrite original event/capture timestamps or claim the data was available at a historical close. Actual local import durability and review clocks are stored and ordered independently. Imported historical warmup is allowed only through its separately approved rights/provenance, observed before the actual review.

Real import requires H_IMPORT_PERMISSION_V1 signed by the authentic independently established Owner and a different trusted auditor, using the original canonical Ed25519 verification path. The two signed bodies must agree and bind dataset canonical SHA256, source_id, H mode/contract hash, installed rights hash, applicable prospective/historical permission, region/venue, cache/retention, source transport and chronology references. Genuine keys/rights are not supplied by this task. Private keys stay outside the worker. No new arbitrary Owner identity or trusted-root bypass is provided. The original F authority roots are empty by default; historical BBO/task permission does not authorize this import. Public-root provisioning is a separate independent authority action.

For clock reconciliation the second separately authorized dataset must have a different authenticated capture origin, agree with all admitted candle identities/OHLCV, validate its source chronology and contain complete mandatory history. It must be fresh in the actual current boot/monotonic domain. A different filename or a worker-written claim of independence is insufficient without genuine external signatures on imported data. Reconciliation only releases observational quarantine and starts a new MVP epoch; all prior failures remain in the append-only journal and the CLOCK_DEGRADED warning persists. Unreconciled rejected/corrected data requires a new independently reviewed dataset/store version; never edit/delete bad records or force-clear the hold.

Mandatory warmup is60completed1D and60completed4H per symbol with no gaps/revisions and the latest expected closes. Optional1H must be contiguous and adequate or is omitted. No missing bars are synthesized. Run one/two manual review cycles daily; there is no scheduler. Initial close grace is120s, configurable60–300s at store creation. The latest source close, conservative source time bounds, grace and freshness must pass; otherwise no candidate is produced. Holdings are4–48h; an existing trigger's plan/horizon is immutable. Late/stale data, future data, uncertain local samples, clock steps, restarts into a different boot, source disagreements and missing warmup produce holds or MVP_DATA_NOT_READY. A clock hold can clear only through complete independent data reconciliation, never by increasing a global threshold.

## Strict Research and verification

```bash
.venv/bin/quant --mode STRICT_RESEARCH doctor
.venv/bin/quant strict native --help
.venv/bin/quant strict qualification --help
```

The original quant-native and quant-qualification remain callable directly. Their source code,50ms sticky clock stop,100ms independent UTC, source-specific signatures, provenance, warmup, availability and native/economic acceptance contracts are unchanged. MVP permissions/receipts/clock reconciliation are incompatible with strict admission and cannot set SOURCE_QUALIFIED, SHADOW_QUALIFIED or ECONOMICALLY_VALIDATED. Current real Strict authority/clock/native evidence remain blocked.

Build and verify with the frozen build/QA toolchain:

```bash
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/toolchain-lock.txt
.venv/bin/python -B tools/build_mvp.py
.venv/bin/python -B tools/offline_pytest.py -q -o 'pythonpath=tests tools tests/native .' -p no:cacheprovider --junitxml=work/tests.xml
.venv/bin/python -m ruff check src tests tools deployment
.venv/bin/python -m compileall -q src tests tools deployment
.venv/bin/python -m mypy src/btc_quant_agent/platform/mvp --follow-imports silent --ignore-missing-imports
.venv/bin/python -B tools/verify_release.py
```

The public source packet intentionally excludes historical original research sources. Its unchanged legacy original-verifier AST comparison may explicitly SKIP there; report the skip, never count it as PASS. No future market/data/host/economic qualification is conferred by this offline build or its synthetic evidence. Controller0-C performs independent acceptance.
