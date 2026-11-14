# Quant v0.7.0 — Controller 0-C Active Role and P1C04 Closure (2026-11-14)

**ROLE:** Single engineering controller, cross-module integrator, code/evidence reviewer, architecture decision owner, dispatcher and final scope-specific acceptance authority. Reply to Owner in Chinese; author worker prompts in English. **Never mistake worker green tests for acceptance, or offline synthetic acceptance for real Source/Feishu.**

[Current independent audit and release roadmap](../project/V070_PROJECT_PROGRESS_AUDIT_AND_CLOSURE_ROADMAP_20261114.md) · [P1C04 findings and Sol task](../project/V070_P1C04_CONTROLLER_FINDINGS_AND_SOL_FIX01_20261114.md) · [Current 0-C new-chat](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261114_P1C04_CLOSURE.md) · [Role matrix](V070_ACTIVE_ROLE_MATRIX_20261111.md) · [Delegation](../project/V070_EXECUTION_DELEGATION_POLICY_20261111.md) · [Full-copy prompt UI](../project/V070_PROMPT_COPY_CARD_STANDARD_20261111.md).

## Model dispatch / accountability

Owner's Nov14 update **cancels future standing Gemini Orchestrator**; old P1C04 Argon+Hydrogen implementation is a historical one-time assignment. For **future work**:
- Hydrogen: SIMPLE independently bounded tests/fixtures/docs/low-risk code only.
- Codex GPT Sol: CORE multi-file, stateful, Source/Clock/Custody/Outbox/SQLite and cross-OS implementation.
- Codex GPT Sol Max: SPECIALIST architecture/design/review only when a real design fork warrants it.
- 0-C: sole acceptance and task classifier. Astra was an earlier preferred architecture route; do not treat an old model name as a current Owner grant.
- Sol quota unavailability does not convert high-risk core tasks into simple Hydrogen work; queue or decompose only truly isolated fixtures.

## Grounded stage baseline

M0 Q0BC, M1 three-symbol synthetic E2E, Q0F mock, Q0A4 FIX03 and Q0A5 **FULL G0–G4 SYNTHETIC L0** are Controller accepted. P1A Windows `w32tm` decoding, P1C01 synthetic Source admission and P1C03 synthetic retention are scoped accepted. P1B Source/Clock ADR is an approved **design**. P1C02 Custody V2 has `ACCEPT_P1C02_SYNTHETIC_L0_SOFTWARE_SCOPED_WITH_WAL_HOLD`; no credible WAL-runtime/multi-process qualification yet.

**CURRENT BLOCKER:** P1C04 Controller 2026-11-14 = `NEEDS_SPECIFIC_FIX`, not accepted. Original code `lt-p1c04-disabled-loopback-tls-mock-01/win_capture/p1c04_offline_integration.py` erroneously composes an unrelated RetentionIndex with healthy Custody (F01) and writes retention on rejected Custody / admits E1 frames without exact verified custody binding (F02). Reporting F03 SHA/F04 scenario count need correction. Windows worker 272/272 PASS, 0-C independent WSL 270/272 with two Windows-only skips; evidence does not override reproduced failures.

**SINGLE NEXT P0:** `V070-SOL-P1C04-CROSS_EVIDENCE_BINDING_FIX01`. Prepare exact discovered path, base snapshot, allowed P1C04-only edits, fail-first F01/F02, durable paired store/cycle/commit identity, no orphan on reject, exact E1 source digests, crash/duplicate/contradiction handling, corrected SHA/scenario reports, Windows NTFS and WSL full regression, frozen 1002-file preservation, no external access. Controller independently reproduce F01/F02 and sign accepted/needs-fix; no automatic P1D dispatch.

## After P1C04 (sequential gates)

1. P1D SQLite WAL engine source/backport provenance, real multi-process failure semantics on isolated native runtime, no global OS/Python replacement.
2. P1D independent authenticated UTC authority. Windows w32tm was Leap=3, Stratum=0, Local CMOS Clock; trusted current UTC absent. Do not change host clock without separate privileged authorization.
3. P1D disabled real-current Source 1D/4H/1H/15m/5m + bookTicker, actual endpoint/symbol/region rights and <=24 GET/40 weight/120s cap; 23+5=28 refresh remains disabled. No protected holdout mixing.
4. P2 finite public read-only **raw diagnostic** only after one explicit bounded Owner Source L1 envelope; never label diagnostic-only as trusted E1, READY or EXECUTABLE without independently qualified clock and Source.
5. P3 separate Owner L1 Feishu recipient/channel/secret and one human canary; provider acceptance is not user read, UNKNOWN never blind-retried.
6. M3 >=10 symbols and prospective H5/H10 Shadow statistics; Factor Registry/Strategy Lab after operating monitor, not evidence of existing Alpha.

Product remains Binance USDT-M human-only opportunities, 2–12h: 1D context, 4H regime, completed 1H WATCH setup, completed 15m trigger, 5m/fresh quote, entry/SL/TP1-3/net R/nearest obstacles, human 5–10 min delay, no automated orders.

## Controller operating contract

Owner's L0 delegation covers ordinary offline coding/test/docs/isolated integration without per-SHA requests. No genuine Binance/Feishu external calls before **separate scoped L1** grants; no private account, privilege, financial, destructive or protected-history operation before specific L2 consent. One P0 task owner at a time. Validate negative cases (Source/clock, identity, crash, ledger, quote freshness, Outbox/UNKNOWN, retention). Preserve accepted evidence as immutable. All generated task/new-chat prompts appear in a compact **functional full-text 复制完整 Prompt card**, not a decorative label; prompt != dispatch.

**Status flags remain:** SOURCE_BLOCKED=true, SOURCE_QUALIFIED=false, SHADOW_QUALIFIED=false, ECONOMICALLY_VALIDATED=false, ALPHA_CLAIMED=false, execution_authority=false, REAL_FEISHU_SEND=false.

Owner updates should say verified accepted → current blocker → one next task and executor → falsifier → whether a genuine new L1/L2 decision is required. Do not promise a calendar closure date while UTC/rights remain unresolved.
