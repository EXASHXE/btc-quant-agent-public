# Program E finite native candle runtime

Controller acceptance PENDING. Outcome recommendation is recorded in E7 after
validation. Source/Shadow/economic qualification stay FALSE; account UNKNOWN/VETO.
The package keeps the accepted `quant` CLI and adds `quant-native`.

From this directory, install the frozen local packet with no registry access:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/requirements-lock.txt
.venv/bin/quant-native doctor
.venv/bin/quant doctor
```

This packet's native wheels target Linux x86_64/Python 3.13. Other platforms need
separately verified dependencies; Windows native execution is NOT_RUN.

`quant-native doctor` is socket-free. The shipped Owner/auditor trust maps are
empty; neither a CLI flag nor caller-asserted clock/TLS booleans open capture.
`capture` requires authenticated exact grant and auditor admission, frozen trust,
final source/wheel/config hashes, an open UTC window and unused output. It takes
the shared cross-phase lock and a registry lock. No waiting for a future window,
no grant renewal, retry, reconnect, background service or account operation exists.

Only after the independent Owner ceremony and Controller authorization:

```bash
mkdir -p state captures
quant-native capture --grant private/owner-envelope.json --audit private/auditor-admission.json --config private/frozen-candle-config.json --wheel release/wheelhouse/quant_advisory_platform-0.7.0.post1-py3-none-any.whl --registry state/native.sqlite
quant-native inspect --registry state/native.sqlite --session EXACT_SIGNED_SESSION_ID
quant-native audit-challenge --registry state/native.sqlite --session EXACT_SIGNED_SESSION_ID
quant-native verify-audit --registry state/native.sqlite --session EXACT_SIGNED_SESSION_ID --audit private/independent-capture-audit.json
```

These are invocation examples, NOT acquisition permission. Current genuine grants,
rights, independent keys and windows are absent. Do not run capture with synthetic
keys against a real venue. Test-only authorities can only reach loopback proxies.
The signed output is an absolute unused directory with a pre-existing parent.
Each registry must remain in controlled local storage without symlink components.
Launch after the controlling process releases its exclusive cross-phase lease;
a held lease fails closed rather than recursively acquiring it.

Inspect `terminal.json`, the append-only SQLite event chain, raw frames, immutable
normalized receipts, startup/refresh clock probes, TLS peer fingerprints and
persisted authorization envelopes. Budget counts conservatively charge attempted
CONNECT routes before sockets and all admitted frames (including partial/control).
The terminal transport-attempt count must not be interpreted as exchange acceptance.
No partial, rejected, duplicated or unacknowledged receipt becomes an eligible bar.

If capture crashes, stop all writers, preserve evidence and use:

```bash
quant-native recover --registry state/native.sqlite
```

Recovery verifies the chain and marks abandoned reservations CRASHED. It never
reconnects or reuses a grant/output. FAILED_CLOSURE, unsettled rows and failed
terminal-file persistence remain evidence gaps. Reconcile them independently;
never delete the registry to reuse a consumed session. Retention is not an
unattended deletion daemon: Owner must perform the independently approved expiry
procedure; overdue previous sessions prevent further capture in that registry.

Actual native receipts remain NATIVE_UNQUALIFIED until separately accepted
clock/source/auditor/warmup/availability evidence exists. The accepted D model is
synthetic-only. E therefore provides an explicitly labeled synthetic network
compatibility adapter and a SOURCE_BLOCKED native view using the existing HTML
renderer. Genuine native observations cannot be converted into synthetic D rows.
Future qualification/promotion requires an independently accepted product schema;
this release cannot silently grant positive S1 eligibility.

Run the bounded fabricated network demonstration on an authorized local-socket
host, choosing a fresh output directory:

```bash
python3 -B tools/native_network_demo.py artifacts/my_network_demo
PYTHONPATH=src:tests/native python3 -B tools/offline_pytest.py -q -p no:cacheprovider --basetemp=audit/my_tests --junitxml=audit/my_tests.xml
python3 -m ruff check src tests tools
python3 -B tools/build_release.py
python3 -B tools/verify_release.py --original-inputs
```

The demo uses actual loopback CONNECT/TLS/WS with fabricated certificates and
clock schedules. Each original close gets a distinct finite synthetic session;
no receipt time is rebased. The S1 plan, later Shadow observation and C evaluation
remain synthetic evidence with zero native/economic samples. Existing D operator
commands and dashboard behavior are documented in README_OPERATOR.md.

The public source packet excludes capture artifacts, generated keys, signatures,
raw native evidence, dependencies, protected research and holdout. Canonical
planning documents remain GitHub docs/engineering; no PR is merged or deployed.
