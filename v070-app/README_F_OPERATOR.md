# Program F operator reference — 0.7.0.post2

This release extends the accepted E finite runtime and D S1/Shadow/HTML product. It does not authorize any real acquisition. Current host clock is unqualified; genuine Owner/auditor roots and rights are absent. Native schema acceptance is empty. All shipped production entrypoints deny admission. Account remains ACCOUNT_UNKNOWN/ACCOUNT_VETO, S2/S3 RESEARCH_ONLY_DISABLED, economic validation false.

## Reproduce the local release

Run from this isolated directory on Linux x86_64/Python 3.13:

```bash
python3 -B tools/build_release.py
python3 -m venv release/operator_env
release/operator_env/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/requirements-lock.txt
release/operator_env/bin/python -m pip check
release/operator_env/bin/quant doctor
release/operator_env/bin/quant-native doctor
release/operator_env/bin/quant-qualification doctor
PYTHONPATH=src:tests/native python3 -B tools/offline_pytest.py -q -p no:cacheprovider --junitxml=audit/operator_tests.xml
python3 -B tools/verify_release.py --original-inputs
```

The wheelhouse contains locally reconstructed or RECORD-verified cached dependencies; see release/dependency_provenance.json and dependency_record_deviations.json. This receipt qualifies the tested Linux/Python combination only. It does not qualify native Windows or the host UTC clock.

## Existing product and local synthetic network evidence

The accepted `quant` replay/review/status/dashboard/recover/export/evaluate interface remains available; see README_OPERATOR.md. The `quant-native` finite capture/inspect/recover/audit interface remains; see README_NATIVE_OPERATOR.md. F adds a required `--host-admission` file to genuine `quant-native capture`.

Reproduce the offline network demonstration with a fresh output path:

```bash
python3 -B tools/native_qualification_demo.py artifacts/operator_network
```

The tool uses only fabricated TLS certificates, ephemeral test signers, simulated source timestamps and loopback sockets. No QA private signing key is persisted. It runs finite sessions at each synthetic close, with no reconnect. The virtual 60-day history is not genuine prospective accumulation. Seven QA stage names are never a genuine Source qualification. The demonstration produces BTC ARMED, ETH/SOL NO_SETUP, immutable plans, later CANCELED lifecycle with TARGET_FIRST market-side observation, existing HTML, and an INSUFFICIENT_SUPPORT C report. A target observation is not an executed opportunity or trading profit.

Final captured demonstration artifacts are under artifacts/verified_qualified_network: native.sqlite, qualification.sqlite, shadow.sqlite, initial/latest.html, product/latest.html, snapshots, and evaluation/scientific_report.md. qa_roots.json is public fabricated QA identity evidence, never installed production trust.

## Production authority and manual workflow

Use external authentic credentials only after Controller schema acceptance and independently authorized host/rights remediation. Never copy QA trust into production. See F2_OWNER_ACTION_PACKET_NON_AUTHORIZING.md. Freeze the exact source, wheel and config hashes before Owner/auditor signatures. Empty installed authority/schema roots are deliberate default-deny stubs; changing them requires independently established trust and rebuilding the release. The inherited source hash includes packaged authority/schema roots; the final wheel hash also binds those roots.

The following are interface examples using externally supplied paths, not authorizing commands or an approved window. Invoke `--help` for all required options:

```bash
quant-native capture --help
quant-qualification register-plan --registry native.sqlite --ledger qualification.sqlite --owner /external/owner-plan.json --auditor /external/auditor-plan.json
quant-qualification attach-host --registry native.sqlite --ledger qualification.sqlite --session EXTERNAL_SESSION --signature /external/host-admission.json
quant-qualification attach-audit --registry native.sqlite --ledger qualification.sqlite --signature /external/timed-capture-audit.json
quant-qualification assess --registry native.sqlite --ledger qualification.sqlite --asof-ms ACTUAL_REVIEW_MS
quant-qualification review --registry native.sqlite --ledger qualification.sqlite --shadow shadow.sqlite --symbol BTCUSDT --trigger-ms COMPLETED_4H_CLOSE_MS --asof-ms ACTUAL_REVIEW_MS
quant-qualification observe --registry native.sqlite --ledger qualification.sqlite --shadow shadow.sqlite --episode EPISODE_ID --asof-ms LATER_OBSERVATION_MS
quant-qualification dashboard --registry native.sqlite --ledger qualification.sqlite --shadow shadow.sqlite --output dashboard
quant-qualification export --registry native.sqlite --ledger qualification.sqlite --shadow shadow.sqlite --output evaluation
```

The availability plan must be registered before collection starts. Owner and independent auditor sign the same F_AVAILABILITY_PLAN_V1. Every finite E grant binds source/config/wheel/scope/window/session/output/budgets/rights. F_HOST_CLOCK_ADMISSION_V1 binds independent host diagnostics, boot, two actual source clock probes, original-target TLS and final hashes. F_CAPTURE_AUDIT_V1 extends the inherited detached audit with audited_ms and the exact host credential hash. It signs terminal/raw/normalized prefixes after durable closure; it must already exist by review time. No backdating is permitted.

The qualification ledger enforces seven evidence transitions. Mandatory 60 completed daily and 60 four-hour candles per symbol, a predeclared seven-day denominator, freshness, gap/correction resolution, signed provenance, original-target TLS, independent clock, durable lineage and schema acceptance are all required. Optional incomplete 1H history cannot remove mandatory 1D/4H requirements. Reviews use the existing S1 compiler and existing renderer with an explicit native schema, not a synthetic relabel. Native C export stays blocked until an independently accepted native economic provenance contract exists; the immutable C evaluator still evaluates the explicit QA export without claiming real economics.

Never retry consumed sessions or reuse outputs. On interruption use the accepted read-only inspect/recover flow to terminally mark abandoned capture; do not reconnect. Each subsequent session requires new finite authority. No unattended collection or grant renewal is provided.

## Clock diagnostics

```bash
python3 -B tools/clock_diagnostics.py audit/operator_clock_profile.json 15
python3 -B tools/clock_qualification.py audit/operator_clock_epoch.json
```

These are bounded read-only diagnostics. Existing receipts establish a real >1.7-second host wall-clock step relative to monotonic/RAW/BOOTTIME. The historical E failing pair was not retained, so its exact upstream cause remains unknown. Wider sample brackets now stop as uncertainty rather than proving a step; the 50ms sticky stop, 100ms independent uncertainty, 300s maximum probe age and 120s refresh are retained. No system time/NTP change is authorized or performed. Local fabricated clocks do not repair the host.

Controller 0-C performs independent acceptance. No Source, Shadow or economic qualification is asserted by this delivery.
