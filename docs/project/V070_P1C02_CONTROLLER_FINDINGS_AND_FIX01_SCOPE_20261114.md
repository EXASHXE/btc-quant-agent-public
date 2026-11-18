# Quant v0.7.0 — P1C02 Controller Independent Review & FIX01 Plan (2026-11-14)

**Controller decision:** `NEEDS_SPECIFIC_FIX` — P1C02 is **NOT YET ACCEPTED**. Signed local decision: `controller-decisions/V070_P1C02_CONTROLLER_INDEPENDENT_FINDINGS_20261114.json`. All Source and Feishu live authority remains blocked. No next worker was dispatched.

## Grounded baseline

- Hydrogen delivered `lt-p1c02-persistent-source-state-offline-01/`, new source sidecar `win_capture/p1c02_source_state.py` SHA256 `a14f89feb8eda57e03486f41bf6fc7de996797aeff014bdec8596e8197be98d7`, offline harness SHA256 `f49e5296ace112e60bc4592a39ebaf70c9ab7f81bcec9fd75f3c7ad036344488`.
- Author Windows fixed C: NTFS native test evidence: **161 PASS / 0 SKIP** (Controller inspected raw logs, did not independently run native Windows). Controller independently ran WSL **160 PASS / 1 Windows-only SKIP / 48 subtests PASS / exit 0**.
- Controller independently checked Q0A5 287/287 and P1-A 308/308 original hashes and P1C01 162/162 inherited hashes; no changes.
- SQLite WAL + FULL synchronous 8-table dedicated source state, real crash/rollback/replay test coverage delivered, no Producer Outbox mutation or external calls.

## Independently reproduced defects

### P1C02-F01 — unverified restart incorrectly marked replayable

1. Prepare and commit a synthetic `seq1` sealed bundle, close DB.
2. Remove `raw/klines_snapshot.json`, reopen DB.
3. `recover_on_restart(capture_session_id, verify_bundles=False)` returned `ok=True`, `can_replay_synthetic_observations=True`, `verified_bundles_count=0`, one committed record and no errors.
4. Control call `verify_bundles=True` returned `ok=False`, replay false, quarantined true.

**Required FIX:** An explicitly skipped check may provide diagnostic metadata, **never** a verified/replayable recovery. Require positive verified sealed-file binding before `can_replay_synthetic_observations=True`; inspect all committed cycles, not just the newest.

### P1C02-F02 — verify/commit TOCTOU

1. Prepared a valid cycle, wrote sealed raw+manifest.
2. `commit_cycle(..., on_before_sqlite_commit=callback)` callback modified `raw/klines_snapshot.json` after initial filesystem verification.
3. Returned `accepted=True, state=COMMITTED`, count=1, even though raw no longer matched.
4. Cold restart eventually detected the mismatch and quarantined the stream; but immediate successful commit was incorrect.

**Required FIX:** Strict path pinning/custody and bounded pre/post-commit revalidation, explicit non-atomic cross-resource state semantics and durable quarantine on detected mutation. Do not assert impossible atomicity between SQLite and a separate filesystem. Callback injection must not obtain a successful accepted COMMITTED outcome with corrupted raw. If a deterministic trust guarantee is impossible under the current storage constraints, STOP and present the architecture choice.

### P1C02-F03 — valid foreign Q0A4 Bundle treated as different candidate's evidence

`verify_sealed_cycle_bundle` branch for `Q0A4_STAGE_BUNDLE_MANIFEST_V1` returns `verify_q0a4_stage_bundle_readonly` without enforcing `expected_cycle`, `expected_bar_root_sha256`, or `expected_payload_sha256`. Controller used the **genuine valid previously accepted** Q0A4 `s1_MIXED_m0` synthetic bundle as the sealed directory for an unrelated P1C02 `seq1` candidate. Actual `prepare=PREPARED; commit=COMMITTED; restart ok=True; verified_bundles_count=1; replay=True`.

**Required FIX (highest priority):** The Q0A4 verification helper remains usable for **standalone read-only audit**, but the P1C02 cycle commit/recover path must reject Q0A4 historical stage manifests as incompatible unless a new formal cross-version mapping contract is independently approved (out of scope for this FIX). For this narrow FIX, reject foreign Q0A4 schema in commit/recover. Identity-to-raw binding must include capture session, cycle_id, boot ID, generation, epoch, sequence, bar root and payload.

## Next task and stop gates

**Hydrogen FIX01:** `V070-P1C02-CONTROLLER-FINDINGS-FIX01` (prompt-only, not dispatched). Only bounded edits within existing P1C02 isolated workspace, preserve prior logs and statuses. Add real fail-first tests for F01/F02/F03 then minimal implementation fixes; run P1C02 targeted, native Windows fixed C: NTFS full test suite and real crash/restart, WSL full suite and synthetic E2E. Controller final acceptance PENDING. No privilege, actual Binance, Feishu, account/trading or protected data.

## Mandatory route correction

P1C02 author report mistakenly redefines follow-on phases; this is **not accepted**. Existing P1-B ADR dictates:
- **P1C03:** detached raw-capture retention/index and <=24h allowlisted, scoped purge **simulation in disposable synthetic L0 fixture workspaces only**; no accepted-evidence deletion.
- **P1C04:** local disabled loopback/TLS mock source/E1/Shadow integration with no real Binance/Feishu calls.
- Independently authenticated external UTC, public diagnostic L1 and qualified L1 are separate subsequent architecture/readiness and Owner envelope gates. Do **not** combine or activate them in P1C03/P1C04.

**Authority flags:** `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false; R1.2 disabled`.
