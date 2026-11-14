# Quant v0.7.0 — P1C04 Independent Controller Findings and Sol FIX01 Scope

**Date:** 2026-11-14. **Independent reviewer:** Controller 0-C.
**Decision:** `NEEDS_SPECIFIC_FIX`. **P1C04 Controller acceptance still BLOCKED; software regression GREEN is not integration evidence-identity acceptance.**
**Local decision:** `controller-decisions/V070_P1C04_CONTROLLER_INDEPENDENT_FINDINGS_20261114.json`.
**Workspace:** `lt-p1c04-disabled-loopback-tls-mock-01/`.

## Verified achievement

Gemini Argon/Hydrogen completed an isolated, disabled-by-default, local loopback TLS synthetic integration, four new modules and four P1C04 test files. Original native Windows Python 3.14 worker receipt **272/272 pass, 0 skip**, on local fixed C: NTFS. Controller independently ran `python3 -B -m unittest discover -s tests -p 'test_*.py'` on WSL Python 3.12: **272 tests, 270 PASS / 2 Windows-only SKIP / 0 FAIL**, 87.753s, exit0. Independently reran frozen hash validator: **1002 checked, 0 mismatch, 0 missing**. No real egress, Feishu or trading grant was asserted. SQLite `SQLITE_WAL_ENGINE_NOT_QUALIFIED` remains.

## Controller F01 — foreign retention index passes custody gate [BLOCKER]

The code in `win_capture/p1c04_offline_integration.py:ComposedCustodyRetentionGate.evaluate` checks two independent boolean recovery readiness values but does not bind the same Source cycle/capture to an authorized retention commit.

**Independent repro:** Commit one `CycleCandidate` into the gate. Create a second, completely independent `RetentionIndex` and unrelated valid synthetic fixture (distinct commit IDs). Call `gate.evaluate(session_id,clock,retention_index_override=foreign_index)`. Actual outcome: `status_code=COMPOSED_SYNTHETIC_REPLAY_PERMITTED`, `can_replay_synthetic=True` despite unrelated index. This proves that conjunction is not sufficient.

**Required:** explicit exact pairing, persisted stable join binding, trust-domain/provenance and store identity; no authorization via arbitrary index override, missing/foreign/duplicate/expired/tampered binding. P1C03's raw is a **separate synthetic retention fixture**; do not call it the same P1C02 raw bytes unless proven.

## Controller F02 — enrollment side-effect after custody rejection; E1 bypasses bound source bytes [BLOCKER]

In `ComposedCustodyRetentionGate.enroll_cycle`, `retention_index.add_fixture(retention_clock)` runs regardless of the `CustodyV2Store.admit_offline_cycle` result. Independent repro: fresh initial cycle with `sequence=2` returns `accepted=False, state=REJECTED, outcome_code=REJECTED_INITIAL_SEQUENCE`; nevertheless, retention SQLite gains one new cycle.

Additionally, `P1C04OfflineIntegrationHarness.run_valid_e2e_flow` evaluates `cap0/cap15["frames_by_symbol"]` directly after a boolean gate check, not via a demonstrated immutable/complete capture digest match to the verified custody evidence. A checked status of unrelated synthetic evidence cannot prove the exact E1 input is covered by the same custody/retention authorization.

**Required:** no orphan retention record on rejected/duplicate custody; exactly once logical paired enrollment with fail-closed cross-DB crash ambiguity; strictly bound capture input digests and Source cycle identity at E1 admission. If real raw data parity is impossible without modifying frozen P1C02/P1C03, retain mock-only explicitly labeled semantics, prohibit pretending it is real custody-qualified Source, and present Controller with a narrowed, truthful alternative.

## Controller F03/F04 — report fidelity [DOCUMENTATION]

- The `STATUS_P1C04.json` and two reports contain **two manually mistyped SHA256 values** while `runs/p1c04/changed_files.json` matches actual bytes:
  - `tests/test_p1c04_source_e1_shadow.py`: actual `bb6ed340c789f58800bd522a3e38a91ea758f8d398534aa3cabc78ccd6077abf`.
  - `fixtures/p1c04/run_p1c04_integration.py`: actual `7989695687fb96a6117cc9700cddd4a907641966e3591ca1495088c2f2cdc062`.
  Regenerate the handoff and machine status digest fields programmatically. Do not edit historical original run receipts.
- The integration runner's actual `scenario_count` is **6**: M01/M21/M22/M23/M24/M25. The separate 29 test methods cover scenario identifiers M01–M25 and N01–N06. Say **6 CLI scenarios**, not 25 CLI-run scenarios.

## Scoped next task (only one task)

Assign **`V070-SOL-P1C04-CROSS_EVIDENCE_BINDING_FIX01`** to Codex GPT **Sol**, complex multi-module contract owner. No standing Gemini Orchestrator role; Hydrogen may be separately used for bounded simple regression work only. Preserve all frozen P1C02/P1C03/Q0BC/transport code and receipts. Implement P1C04-local join and validation; fail first for foreign index, rejected enrollment, altered eval frames, missing identity, duplicate and subprocess crash. Rerun 272 baseline + extra negatives on native fixed NTFS and WSL, TLS zero external egress and frozen hashes. Controller acceptance remains pending. **Do not start P1D/P2/P3/P4 or real Binance/Feishu** until this stage is independently closed.

**Authority:** `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false`.
