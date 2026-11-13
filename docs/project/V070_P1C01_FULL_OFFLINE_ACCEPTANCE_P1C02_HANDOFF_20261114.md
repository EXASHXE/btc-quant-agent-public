# Quant v0.7.0 — P1C01 Full-L0 Acceptance & P1C02 Persistent Source State Handoff

**Controller decision date:** 2026-11-14. **Decision:** `ACCEPT_P1C01_FULL_OFFLINE_SCOPED`.

**Local signed Controller artifact:** `controller-decisions/V070_P1C01_FULL_OFFLINE_CONTROLLER_ACCEPTANCE_20261114.json`. This is synthetic-source, local-only validation, **NOT** Source clock qualification, live data approval, alpha, human-delivery or trading authority.

## Evidence

- Latest FIX02: `lt-p1c01-source-admission-offline-contract-01/`. Contract SHA-256 `85063ee3b869d28382aa3394600619e14e10590e8c1707fdcb122e88a9b77ea6`; request plan `1d21274d15d744f099758031231c0da131e1e40f077ba8609deb2f312b43b5a4`; test file `26dc6131bfeaa52825c950ce58ec151a0093f7e3965cad7ba705fe462e927f7c`.
- Controller independently reran WSL suite: **124 PASS / 1 Windows-only SKIP**, 48 subtests PASS, exit 0, runtime 27.13 sec. Author native Windows 3.14 on fixed local NTFS: **125 PASS / 0 SKIP**, native receipt and logs independently inspected; Controller did **not** rerun a separate native Windows process. Native stage source was cleaned at time of Controller review; signed local author receipts remain.
- Controller independently checked F05: unmodified classifier output accepted only structurally; `dataclasses.replace` copies, UTC +1d/-1d shifts, clock Venue age/width revisions, shallow/deep copy, fabricated external qualification flags all rejected. Forged future quote not fresh/actionable, forged Kline not admitted; weakref GC entry removed.
- F01–F04 original reproducers fixed. Accepted P1-A **308/308** and Q0A5 **287/287** source/evidence files hash match.
- E2E Windows/WSL synthetic summaries differ only in platform and Python version, 23-request Stage1+2; 28>24 refresh veto preserved, R1.2 disabled, Source remains blocked, no real REST/Feishu calls.

## Architectural limitation

The new weakref identity+field-snapshot registry validates an **unmodified classifier object within the same Python process**. It is **not** cryptographic authentication, cannot establish independent UTC, and cannot be serialized across process restarts or module reloads. Future P1C02 MUST revalidate original durable evidence with independent readback and explicit provenance. Never treat a stored `clock_contract_passed` boolean or a stored dataclass as trust.

## P1C02 approved next prompt scope (NOT dispatched)

`V070-P1C02-PERSISTENT-SOURCE-LEDGER-OFFLINE-01`: Gemini 4 Hydrogen High/XHigh bounded L0-M sidecar state engineering under Controller 0-C architecture, source workspace cloned from P1C01 FIX02.

- New isolated sidecar modules only: `win_capture/p1c02_source_state.py` + optional `win_capture/p1c02_offline_recovery.py`, and synthetic tests/fixtures and reports. Do **not** change frozen `q0bc_v2/native/q0b/source.py`, `win_capture/e1_five_tf_bridge.py`, `win_capture/bundle.py`, Q0BC Producer/Outbox, Q0F or real transport.
- Native fixed-NTFS local SQLite, transactionally persistent `source_epoch`, `source_generation`, monotonic `sequence`, boot/session identity and immutable per-symbol interval/bar digest; enforce exact restart/replay semantics. Explicitly treat cross-boot/epoch changes, torn manifest or missing raw as blocked/quarantined.
- All public evidence/rows are synthetic only. No production grant generation, no live HTTP or Feishu, no auto orders; treat mutable clock claims as diagnostic only.
- Simulate crashes by `os._exit` child processes; isolate DB under disposable storage. Verify `PRAGMA integrity_check`, rollback, lock conflict, replay and revision rejection. Cross-process idempotency is keyed by immutable cycle/message ID; repeated identical cycle must not create a second logical effect. New cycle must monotonically progress or be quarantined.
- Ensure SQLite WAL/restart mode and platform drift follow prior accepted Windows native contracts; test both real Windows local C: NTFS and WSL. Windows standalone author-only evidence must not be misrepresented as Controller reexecution.
- 24-hour raw-data deletion is *P1C03*, not in P1C02. No removal of accepted evidence. P1C04 loopback mock after separate acceptance; L1 canary authorization remains separate.

## Gate sequence

`P1C01 ACCEPTED` → `P1C02 sidecar durable state pending` → `P1C03 bounded retention/purge pending` → `P1C04 disabled loopback integration pending` → only then discuss separate Owner-bounded real public diagnostics.

**Unchanged flags:** `SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false`.
