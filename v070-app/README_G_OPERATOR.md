# Program G portable offline deployment

This packet preserves every accepted F application file and its exact 0.7.0.post2 wheel. Quant, quant-native, quant-qualification, S1, Shadow, HTML and C are unchanged. New tools only inspect the host, freeze/verify the environment, rebuild the accepted wheel and check external authority without sockets. They never start acquisition. Default Owner/auditor roots and live native schema pin remain empty. ACCOUNT_UNKNOWN/ACCOUNT_VETO; S2/S3 disabled; real economic evidence zero.

## Approved target and verification

No alternative host has been approved or qualified. The connected desktop is the same WSL2 host. Do not transfer this packet to another device until the Owner approves that specific destination. No cloud provisioning, package download, host installation, time/service/hypervisor/network change or automatic collection is performed by these commands.

The conservative artifact profile is Linux x86_64, glibc>=2.39, CPython3.13.13. The interpreter must already be supplied by the approved host administrator. The packet does not contain a Python distribution. Other ABIs/Python versions need separately verified dependency artifacts and the same tests. A VPS, VM or native Linux machine is a candidate, never automatically clock-qualified.

Obtain the portable ZIP's SHA256 from the independently reviewed G2 receipt and verify it before executing packet code. Start in the verified source packet root; the first two commands materialize the portable ZIP, then all commands run from that new root:

```bash
(cd release && sha256sum -c G_portable.zip.sha256)
python3.13 -m deployment.bundle materialize release/G_portable.zip release/candidate
cd release/candidate
python3.13 -m deployment.bundle verify .
python3.13 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/toolchain-lock.txt
.venv/bin/python -m pip check
.venv/bin/python -m deployment.rebuild --root . --output rebuild
.venv/bin/quant doctor
.venv/bin/quant-native doctor
.venv/bin/quant-qualification doctor
mkdir -p artifacts
.venv/bin/python -m deployment.host_check --output artifacts/host_epoch
```

The first materialize command runs from the independently verified source/deployment packet; the ZIP itself contains no executable bootstrap that runs on extraction. A host-check exit2 is expected without independently authentic clock credentials, even if the bounded local stability sample passes. Observe its result.json and clock_raw.json. Its real local file fsync/atomic replace, SQLite process-crash rollback and lock checks do not establish hardware power-loss persistence. It never changes host time or probes a source.

The inherited F doctors describe the default-deny release state. They do not certify the current host. A new independent host qualification is required after migration, reboot, time correction, suspend/resume or clock epoch change. The accepted50ms sticky stop,100ms independent uncertainty,300s probe maximum age and120s refresh are unchanged. A stable30s sample or synchronized status flag alone never qualifies UTC.

## Full offline checks

```bash
.venv/bin/python -B tools/offline_pytest.py -q -o 'pythonpath=tests tools tests/native .' -p no:cacheprovider --junitxml=artifacts/tests.xml
.venv/bin/python -m ruff check src tests tools deployment
.venv/bin/python -m compileall -q src tests tools deployment
.venv/bin/python -m mypy deployment src/btc_quant_agent/platform/native src/btc_quant_agent/platform/qualification src/btc_quant_agent/platform/rc_strategy.py src/btc_quant_agent/platform/rc_observe.py --follow-imports silent --ignore-missing-imports
.venv/bin/python -B tools/native_qualification_demo.py artifacts/network
```

The final command is finite loopback CONNECT/TLS/WS only. It simulates virtual history, Owner/auditor roles and clocks; never genuine rights, signatures, completed native coverage or UTC qualification. It produces194local sessions/542synthetic bars, versioned qualification, BTC ARMED and ETH/SOL NO_SETUP, later CANCELED Shadow with unchanged plan, existing HTML, and C INSUFFICIENT_SUPPORT. C economic admission for genuine native exports remains blocked. All QA keys/certificates are fabricated. No executable test-signature flag is added to the production CLIs.

## Independent authority intake

Use G3_OWNER_ACTION_PACKET_NON_AUTHORIZING.md after independent host/rights review. No private Owner/auditor key enters this worker or packet. Final installed authentic public roots and live schema pin, if independently approved later, change the source/wheel and require a new freeze/rebuild/test before signatures. The current wheel hash describes the empty-trust offline build only.

For externally authentic credentials, `deployment.admission_check` accepts --grant, --audit, --config, --wheel, --rights, --host-certificate, --registry and --report. It uses the existing canonical Ed25519 verifier, exact source/config/wheel/window and independent host epoch. The separately reviewed rights dossier's exact bytes must match the signed/pinned rights hash. A file containing permission assertions has no authority without that independent signed trust. It checks unused identity and storage but never reserves, connects, renews or starts a collector. Success is only AUTHORITY_PREFLIGHT_ONLY_RUNTIME_ENFORCEMENT_REQUIRED. The existing quant-native launcher must recheck everything and perform the genuine durable reservation/TLS/clock/queue/budget/terminal enforcement under a separate exact currently open grant. Do not invoke it on the strength of this packet.

The native clock source probes needed for host evidence also need explicit independent permission. Missing external proof is a block, not permission to issue a preliminary network request. Capture uses only approved CONNECT, no direct fallback, exact closed-kline streams and finite windows, no retry or reconnect. Independent timed capture audit must bind the exact host credential and exist after closure but before the scheduled review. Neither a transport diagnostic nor this packet qualifies Source, Shadow or economics.

For rollback, stop the foreground local exercise and leave immutable evidence untouched. Select the previously verified release in a separate directory; do not overwrite a trusted root, journal, grant, output, clock stop or capture reservation. A consumed session never becomes reusable by rollback. No merge, deployment or successor dispatch is automatic.
