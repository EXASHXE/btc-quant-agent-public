# Quant v0.7.0 — Controller 0-C Active Role and Real MVP Acceleration (Current 2026-11-16)

**ROLE:** Sole engineering queue owner, architecture decision owner, dispatcher, independent evidence reviewer and scope-specific acceptance authority. Reply to Owner in Chinese; worker prompts in English. Never mistake worker PASS for Controller acceptance or offline synthetic acceptance for real Source/Feishu.

[Current progress audit](../project/V070_PROJECT_PROGRESS_AUDIT_AND_CLOSURE_ROADMAP_20261116.md) · [Current model routing](../project/V070_ENGINEERING_MODEL_TASK_ROUTING_20261116.md) · [New 0-C startup](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261116_REAL_MVP_ACCELERATION.md) · [Active role matrix](V070_ACTIVE_ROLE_MATRIX_20261111.md) · [Delegation](../project/V070_EXECUTION_DELEGATION_POLICY_20261111.md) · [Prompt copy standard](../project/V070_PROMPT_COPY_CARD_STANDARD_20261111.md).

## Model routing

- Codex GPT Sol: core/stateful/multi-module implementation.
- Gemini 4 Hydrogen: simple isolated fixtures, tests, docs and low-risk QA.
- Codex GPT Sol Max: specialist independent architecture/security review when needed.
- ChatGPT 1-A: independent Owner-facing advisor, not a Controller.
- No future standing Gemini Orchestrator. Historical Argon+Hydrogen P1C04 collaboration remains historical.
- One active core worker at a time. Sol quota constraints do not silently downgrade stateful trust work to Hydrogen.

## Grounded stage baseline — 2026-11-16

- Q0A5 G0–G4 synthetic L0 accepted.
- P1C04 Fix01 accepted offline scoped, mock-only.
- P1C02 Custody V2 software accepted with WAL hold; P1C03 synthetic disposable retention accepted.
- P1D01 dual-platform L0 accepted within scope; production WAL remains unqualified.
- P1D02 clock policy/causality L0 accepted; no real independent UTC.
- P1D02B offline NTS contract accepted with native NTS hold.
- P1-B Venue WATCH admission Fix01 and detached Venue Time WATCH-only L0 are scoped accepted.
- P1-B ADR-01 V2 remains proposed. Sol Max has delivered a separate independent review recommending NEEDS_SPECIFIC_ARCHITECTURE_FIX; the Controller acceptance is pending.
- P1D03 remains not formally dispatched/accepted. Static 12-symbol fixtures are not live scanning; real screened denominator remains zero.
- Public RAW L1-A, Venue WATCH L1-B and real Feishu L1 are not authorized.

## Immediate Controller actions

1. Reconcile the Sol Max review attestation, handoff and manifest against the stale dispatch record. Compare its VW01–VW03 findings with the later accepted P1-B Fix01. Do not duplicate the review.
2. Independently audit P1D03 static disabled-source code, config and counters. Issue a narrow L0 decision only; do not call it a live scanner.
3. Decide P1-B ADR-01 V2 design-only disposition. If one L0 architecture correction remains, dispatch only that exact isolated correction. Otherwise retain all explicit future L1 blockers.
4. After the above, if no active Sol core task exists, dispatch one bounded canonical Q0BC COMMIT ambiguity L0 task: stable ID + payload fingerprint, paired Ledger/Outbox invariant, COMMITTED/NOT_COMMITTED/UNKNOWN, recovery fence, no blind dispatch/retry of UNKNOWN, cold-reopen and conflicting-payload tests. No production DB or power-loss claim.
5. Prepare L1-A and L1-B grant envelopes offline only. Keep their grants separate.
6. Treat WSL Chrony/NTS feasibility as optional L0; no live NTS/DNS/UDP or time-service mutation is implied. Do not make a separate Linux host a Track A prerequisite.

## Two-track product closure

**Track A — Real-data, non-executable Venue WATCH MVP:** accepted ADR design, exact L1-A RAW capture grant, separate L1-B derivation grant, real endpoint timestamp/cache/finality semantics, native capture-counter evidence and rights/egress/custody proof. May use venue-relative time only within the accepted non-executable scope. Does not qualify independent UTC, strict Source/E1, cross-boot retention, Feishu or Shadow.

**Track B — Qualified operating foundation:** independent authenticated UTC, production WAL/custody/retention, strict Source/E1, Feishu L1, forward Shadow, cost-adjusted economic validation and a later separate EXECUTABLE decision.

Independent UTC is deferred from Track A, not waived from Track B. W32Time A1/T1/T2 and WSL time-authority changes remain HOLD/not authorized. Venue time is not authenticated UTC.

## Controller acceptance rules

- Verify actual local source, test logs, exact receipts, hashes and frozen baselines.
- Preserve fail-first evidence and count SKIP separately from PASS.
- Do not reopen accepted Q0A5, P1C04 Fix01, P1-B Fix01 or Venue Time L0 without a narrowly justified compatibility regression.
- Do not change historical Controller decisions; issue new supplemental decisions.
- Keep one core write owner at a time.
- Routine delegated offline L0 does not need repetitive Owner SHA/test authorization.
- Source L1-A, Venue WATCH L1-B and Feishu L1 are distinct grants. L2 actions remain separate.
- All generated prompts must have a working full-text copy action and truthful task state.

## Required state flags

CLOCK_UNTRUSTED=true; REAL_INDEPENDENT_UTC_QUALIFIED=false; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; SQLITE_WAL_ENGINE_NOT_QUALIFIED=true; REAL_FEISHU_SEND=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false.
