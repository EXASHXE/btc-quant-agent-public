> **LATEST OWNER ROUTING OVERRIDE — 2026-11-13:** [Controlling model task routing](V070_ENGINEERING_MODEL_TASK_ROUTING_20261113.md) assigns **Gemini 4 Hydrogen to SIMPLE work**, **Codex GPT Sol to MODERATELY COMPLEX implementation**, and **Codex GPT Astra to COMPLEX architecture analysis**. Hydrogen is **not** the default author for all engineering. The model availability scan, Argon/Opus audit triage, evidence and Source blocked claims below remain factual historical snapshots. If Sol is quota-blocked, queue medium tasks rather than silently downgrade them to Hydrogen/Flash.

# Quant v0.7.0 — Hydrogen Executor Migration and Post-Argon/Opus Triage (2026-11-13)

**Controller task:** `V070-GEMINI-4-HYDROGEN-EXECUTOR-MIGRATION-20261113`. **Status:** `POLICY_MIGRATED / HYDROGEN_CLI_AVAILABILITY_UNVERIFIED / FALLBACK_ACTIVE`. Owner-facing Controller retains architecture, task scoping, independent review, and acceptance. No worker dispatched and no live Source/Feishu calls.

## Engineering model availability: measured, not assumed

The connected local WSL Antigravity CLI `1.5.7` returned these models via `antigravity models`: `gemini-3.8-flash-high`, `gemini-3.8-flash-medium`, `gemini-3.8-flash-low`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gpt-oss-120b-medium`. Current CLI settings select `Gemini 3.8 Flash (High)`. Gemini CLI is `0.37.0`. **Hydrogen was not listed; no Hydrogen model ID, local tool-call ability, editing, testing, or reasoning mode was verified.** This does not assert that Hydrogen is unavailable in another UI/client or after an update.

**Owner-desired hierarchy:** Gemini 4 Hydrogen is the preferred *conditional* PRIMARY LOCAL L0 IMPLEMENTER. It becomes ACTIVE only after the existing local Antigravity or Gemini environment actually lists it with an exact identifier and an isolated, no-network synthetic file-read/edit/test/review smoke receipt. Until then **Gemini 3.8 Flash remains active fallback**, preserving MVP progress. No invented model IDs or benchmark superiority; no reserved strong-model calls used for the smoke.

## Accepted baseline vs new independent findings

M0 and M1 `ACCEPT_OFFLINE_SCOPED`; Q0F `ACCEPT_OFFLINE_SCOPED`; Q0A3 `ACCEPT_FIXED_OFFLINE_SUBSET`. Q0A4 historical Controller decision on 2026-11-13 was `ACCEPT_OFFLINE_SCOPED`, original author WSL `64/64 PASS`, native Windows `61 PASS / 3 SKIP` (`G29/F15/C14` need `jsonschema`). **That historical acceptance and receipts are preserved, but reliance on Q0A4 for M2 is held pending the newly reported non-author audit integrity fix.**

The Owner supplied two completed reviews in the chat: `V070-Q0A4-R1-R5-INDEPENDENT-AUDIT-01` from Gemini Argon and `V070-OPUS55-M2-READINESS-CRITICAL-ARCHITECTURE-01` from Opus 5.5. Both review opportunities are treated as **used for planning**; no extra runs planned. Their audit report files were **not found** in the local project root during read-only scan; evidence in this Controller round is report text plus independently checked source paths and original receipts. The Controller attempted a fresh temporary adversarial replay but remote command policy refused the command; it is **not** claimed as an independent Controller reproduction.

### Argon triage (priority)

- **F-01 — P1 high/blocking offline integrity claim**: `win_capture/two_stage.py::verify_stage_bundle` verifies self-hashed manifest, stage package and hash-chained `ledger.sqlite` separately but does **not** match `manifest.responses[]` to the original `HTTP_RESPONSE` ledger events, or re-derive serialized clock/quote/candle facts and true request/weight/byte ceilings from verified raw event evidence. Argon reports a successful resealed-copy 121160ms deadline bypass and a rewritten raw `/time` body accepted by verifier. Controller independently confirmed missing static consistency checks, not the entire dynamic replay.
- **F-02 — P1**: `SnapshotFinalizer.finalize_two_stage` uses convex-hull offset span `max(upper)-min(lower)<=2000`, with no nonempty offset interval intersection test, so two disjoint exchange-QPC brackets may be admitted. Argon reports a concrete independent adversarial case; static code confirms this admission predicate.
- **F-03 — P2 test accuracy**: C09 currently fails in `verify_stage_bundle` before hitting `INTERSTAGE_MONOTONIC_REWIND`; fix test to target the precise intended branch and preserve pre-fix evidence truthfully.
- **F-04 — P2**: Exact 2000ms positive boundary missing, Python socket monkeypatch not an OS network sandbox.
- **Evidence correction:** Argon's later text names incorrect Windows-skipped test functions; actual original native Windows receipt proves skipped **G29, F15, C14**. Do not re-label these as PASS.
- **Critical schema reality:** `win_capture/bundle.py` records `LEDGER_INIT` and `HTTP_RESPONSE` event kinds only. Proposed checks against `HTTP_REQUEST` or `BUNDLE_SEALED` cannot be implemented without a versioned schema addition; prefer recomputation from actual `HTTP_RESPONSE` records and raw bytes. A self SHA-256 digest is integrity detection, not an independent external provenance attestation.

### Opus cross-module triage

- `F-01` R1.1 OFFLINE_MOCK/2030/FEISHU_MOCK fences are **intended L0 safety controls**; creation of a separately pinned, **DISABLED** R1.2 M2 profile is a future L1 readiness gate, never permission to relax R1.1.
- `F-02` multiple simultaneous ENTRY_READY signals with 1000ms snapshot gate and 1 msg/s Q0F throttle may lead to stale/deferred alerts. Design a fail-closed fresh-quote/snapshot refresh or truthful expiry, not a TTL extension or blind retry.
- `F-03` verified static batch issue: `win_capture/e1_five_tf_bridge.py::evaluate_three_symbol_batch` directly calls `producer.review(outcome.ingress)` without per-symbol exception isolation. Add precise global versus symbol veto classification in a separate isolated integration workspace.
- `F-04` native Windows Producer persistence unproven due to three jsonschema skips; unified single executable Q0A4→Q0BC→Q0F→Shadow run is absent. Use disposable offline native Windows venv and genuine integrated tests, not author summary.
- Other P1/P2 findings: immutable worst-entry stress R is conservative; user-visible executable quote R is supplementary only; 1D obstacles and confirmation geometry are frozen research topics; Q0F rate-limit deferred audit, Shadow denominator, and retention need scoped follow-ups.
- **Audit proposal inconsistencies requiring Controller correction:** an Opus suggested source envelope of 35 GET/45 weight exceeds existing Q0A4 24/40 caps; 72h at 15min cadence is 288 cycles, while 96 cycles is 24h. Do not promote those figures as approved envelopes without a versioned budget/cadence contract.

## Controller execution sequence

1. **NOW — only one owner-forwarded L0 worker task:** `V070-Q0A4-STAGE-BUNDLE-LEDGER-CROSSCHECK-FIX-03`; actual `verify_stage_bundle` event cross-check and stage raw rederivation, cross-stage bracket intersection, precise branch regression. Executor Hydrogen **only if actual model availability + local smoke established**, otherwise Gemini 3.8 Flash.
2. **THEN — Controller limited acceptance decision:** independently examine fix diff and true receipts, preserve source blocked and no live egress.
3. **NEXT — isolated unified M2 L0 preflight:** Windows jsonschema 3 skips via offline venv, batch exception isolation, single canonical Q0BC Outbox integration, Shadow accounting.
4. **THEN — throttle/freshness queue drain** under 1 msg/s with injected 250ms provider delay and fresh snapshot, correct duplicate/UNKNOWN handling.
5. **THEN — versioned disabled R1.2 contract and finite L1 Source/Feishu envelopes** prepared separately. Never enable Source/Feishu on synthetic-only evidence.

Keep `SOURCE_BLOCKED=true`, `SOURCE_QUALIFIED=false`, `SHADOW_QUALIFIED=false`, `ECONOMICALLY_VALIDATED=false`, `ALPHA_CLAIMED=false`, `execution_authority=false`, `REAL_FEISHU_SEND=false`. Public Source and Feishu L1 permissions require separately scoped Owner action only at actual external activation; neither is currently requested. No automatic trading.

Local machine decision: `controller-decisions/V070_GEMINI4_HYDROGEN_EXECUTOR_MIGRATION_AND_AUDIT_TRIAGE_20261113.json`.
