# Program S: offline Controller review candidate — S_PARTIAL

No Binance request is authorized or performed by S. This is not a production deployment or a new Strict qualification. The release contains the hardened existing Windows capture and a **non-actionable synthetic history audit** consumer. Authentic operational access/Owner scope records are absent. The consumer intentionally refuses CURRENT_MANUAL_REVIEW and public raw bundles lacking an independent current Windows retention anchor. Do not run a real test until Controller reviews these limitations and issues a new exact scope.

## Reproduce offline

Windows x64/Python3.14.0 was actually tested. No API credentials, time-service changes or reboot:

```powershell
py -3.14 -B -m unittest tests.test_windows_capture_offline tests.test_s_hardening -v
py -3.14 -B tools/native_demo.py
py -3.14 -B tools/native_clock.py
```

All test networking is guarded to loopback. The original10 cases and S cases run natively; Windows-only tests are not counted as passing on WSL. Certificates/keys and authority records used by unit tests are fabricated QA data, not Owner identities or permission. Native demo creates a new fixed NTFS temporary directory, verifies native filesystem APIs and captures14 fabricated HTTP200 responses via127.0.0.1 CONNECT/TLS. Read `audit/S_NATIVE_NTFS_RECEIPT.json` for the exact path, environment, source hashes and clocks. It is not real market evidence. W32Time currently reports unavailable/stopped; raw status is preserved and strictUTC remainsfalse. Sleep/resume/restart faults are injected; no actual sleep/reboot occurred.

Install the reproducible wheel offline in a fresh Windows venv:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install --no-index --no-deps release\quant_windows_handoff-0.7.0.post1-py3-none-any.whl
.venv\Scripts\quant-win-capture --help
```

`tools/windows_install.py` independently creates a native NTFS venv, installs without an index, checks installed module hashes/native boot calls and proves `--allow-live-public-https` alone exits before creating output or connecting.

On WSL, use the accepted O environment; the wheel does not overlay Quant or C:

```bash
PYTHONDONTWRITEBYTECODE=1 ../lt-program-o-clock-remediation-01/release/O_final_env/bin/python -B -m pytest -q tests/test_wsl_handoff_e2e.py tests/test_s_consumer.py -p no:cacheprovider
```

Set `QUANT_WIN_NATIVE_QA_BUNDLE` to the actual `/mnt/c/.../bundle` path from the native receipt to execute the cross-OS case; otherwise that one case is a SKIP, never PASS. The independent S receipt includes its execution with no skip. For the artifact demo, use `tools/wsl_release_check.py` (local only). `regression_input/tools/run_o_tests.py` runs the unchanged O672 cases with the C154 domain inside its permitted workspace; original A–P/C files are never written.

Build twice with frozen existing O setuptools82.0.1/wheel0.46.3, no downloads:

```bash
PYTHONDONTWRITEBYTECODE=1 ../lt-program-o-clock-remediation-01/release/O_final_env/bin/python -B tools/build_release.py
```

## Future access profile — NOT AUTHORIZATION

Outer `J_OPERATIONAL_ACCESS_V1` schema, J policySHA340c3c2b0f7788203b8fdcab36b74fdd982a4d3d7e276b03a69fe681511707ba remain unchanged. S adds strict content checks: verified, hash-bound eligibility/use/exclusions JSON; physical operator and egress KR Owner declarations; actual personal noncommercial readonly purpose; honest current operational source review with official references; cache permission and24h maximum; complete FINAL_HOLDOUT [1769904000000,1785542400000) and all other explicit exclusions. This is an operational review record, not Binance-issued legal approval or proof of account/trading eligibility. Do not synthesize reviewer identities or hashes. Operator files must be ordinary local files without traversal/reparse points.

Required evidence content is precisely validated by `win_capture/access.py`. Eligibility includes `operator_physical_country=KR`, `egress_country=KR`, `declaration_kind=OWNER_DECLARATION_NOT_LEGAL_CERTIFICATION`, `review_status=VERIFIED_OPERATIONAL_SCOPE`, `applicable_restriction_found=false` only if supported by actual current evidence, `official_references`, `reviewed_at_UTC` (display provenance), plus `review_boot_id/review_qpc_ms` from native Windows to bound review age to24h without WSL wall time. Use/cache evidence includes `purpose=PERSONAL_NONCOMMERCIAL_READONLY_ADVISORY`, `cache_hours=24`, `retention_permission_reviewed=true` only when justified.

The separately supplied `S_ONE_MANUAL_SCAN_AUTH_V1` record binds Owner reference, single-use session/output/reservation database, exact capture sourceSHA and S policySHA, Access/evidenceSHA, actual native boot identity and QPC [start,end) window at most120s, exact host/routes/symbols/GET and24 requests/40 conservative weight/120s/24h cache. No synthetic reference may pass the production profile. `win_capture.access.source_hash()` and `POLICY_HASH` expose final fingerprints; the external wheel/build receipt must also be reviewed. The registry is synchronous SQLite, consumed before output/network attempts and never renewed on failure. Owner must protect the registry from deletion/tampering; this is not an independent cryptographic Owner signing service.

Only127.0.0.1 with an explicitly approved port/permitted_reference may be configured. Production uses `HTTPSConnection.set_tunnel(fapi.binance.com,443)`, normal certificate-chain and hostname verification, no direct fallback, rotation, redirects or retry. Finite joined socket-deadline watchdogs are internal foreground-session cleanup, not a daemon or collector. Grant remaining time bounds request timeouts and admission is checked again after durable persistence and before sealing. HTTP403/418/429/451 or TLS/proxy failure stops the attempt. No private routes, keys, account operations or alerts.

## Time, receipts and replay boundary

Native boot identity requires both kernel BootIdentifier and kernel BootTime; missing either fails closed. QPC frequency never supplies identity. QPC/Unbiased coherence retains50ms plus actual sampling bounds; coarseTick64 adds a separate resolution-aware discontinuity check. FILETIME is diagnostic, not strictUTC. Venue-time references bound completed bars/current partial4H separately; mandatory history, no-chase, pivot/target/expiry, as-of and source completeness checks reuse the accepted compiler.

Raw bytes are atomically fsynced before their raw-durable sample; a separate journal-ack event follows the full SQLite commit. Receipts are integrity/hash-chain evidence under TLS, not cryptographically signed exchange publications. Production provenance cannot be inferred from synthetic tests. An independent trusted expected bundle digest/authentic review channel remains a Controller gate; self-consistent hashes alone do not prove identity.

Consumer files are copied through pinned, no-follow directory descriptors into a private snapshot before validation. Changed manifests, raw symlinks and tampering fail; post-check source replacement cannot change the frozen audit input. Existing output reuse fails. Independent historical audits may replay to distinct output directories, always marked NON-ACTIONABLE; replay cannot refresh quote age or create a new current forecast. Historical S1 is reconstructed for QA, not retroactively issued. `CURRENT_MANUAL_REVIEW` refuses without using WSL wall/monotonic, even for an otherwise valid bundle. Public bundles are refused before raw copy when no independent current Windows retention anchor is implemented.

## Retention and remaining blockers

`S_QA_CACHE_PATHS.json` records exact native QA/cache paths and copies. These are synthetic, not recovered N data. No background deletion is created. For future genuine data, all copies retain the original maximum24h deadline; boot discontinuity/expiry must block use. `cache_status` checks the native domain; `purge_receipt` records actual absence with Owner reference/prior manifestSHA and never deletes. Owner must authorize and perform exact-path cleanup, then retain a hash-only receipt. Do not use wildcard deletion or extend retention by copying. S never accesses or restores deleted N payloads.

Remaining before a genuine whole-product test: authentic reviewed rights/cache/Owner scope; independent Windows current-retention/review anchor and public-bundle consumer acceptance; independent bundle authentication/digest trust; further independent review of producer directory/reparse race handling. This packet proves static NTFS/reparse rejection and consumer pinned-copy races, not every adversarial producer race. No genuine current S1 or forward Shadow evidence exists.

SOURCE_QUALIFIED=false, SHADOW_QUALIFIED=false, ECONOMICALLY_VALIDATED=false; ACCOUNT_UNKNOWN/ACCOUNT_VETO; S2/S3 disabled. Frozen C rejects the exact Windows class with SOURCE_CLASS_INVALID and INSUFFICIENT_SUPPORT. No actual fills, PnL, Alpha, long-term performance or strictUTC qualification are claimed. Submit to0-C; do not merge, deploy, start collectors or launch successors.
