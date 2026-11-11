# Quant v0.7.0 — Gemini Three-Report Audit & Accelerated MVP Integration Plan

**Review date:** 2026-11-11. **Status:** PLANNING / READ-ONLY EVIDENCE RECONCILIATION. **Owner priority:** fast first usable 2–12h read-only monitoring MVP, not further proliferation of control layers.

**Controlling workflow:** [lean delegated execution](V070_EXECUTION_DELEGATION_POLICY_20261111.md); [MVP closure home](V070_MVP_CLOSURE_HOME_20261111.md).

## 1. Original Gemini source reports inspected (not auto-accepted)

Original location on authorized local Windows:
C:\Users\99508\.gemini\antigravity\brain\5dfd9438-0949-485e-8bec-f9d3b7aaad17\

1. **V070_Q0A2_SOURCE_TRUST_CLOSURE_02_PREFLIGHT_REPORT.md** (approx. 496 lines): Source custody/time/retention, strict Windows watchdog, NTFS writer, 45 bytecode spill, old Source vs Q0B timeframe mismatch.
2. **V070_Q0F_FEISHU_PROVIDER_ADAPTER_01_PREFLIGHT_REPORT.md** (approx. 578 lines): unique authoritative outbox, Feishu mock/live separation, current gate and transport, correct Provider status and UNKNOWN treatment, credential secrecy.
3. **V070_MVP_M2_UNIFIED_E2E_INTERFACE_MAP_01_REPORT.md** (approx. 612 lines): single owner of each state, code-level interface mapping, distinct append-only Shadow DB, dashboard reuse and proposed 24-case three-symbol M2 test plan.

**Evidence labels:** Gemini describes inspected code and makes architecture recommendations; proposed Sol task plans are **not executed work**. R1.1 remediated and positive-semantic worktrees were independently found locally; final 0-C Q0R acceptance was not found. Treat every report's independent assumptions (e.g. official Feishu API details, time authority availability, endpoint weights) as unverified until checked against the source and runtime.

## 2. Reconciled findings

| Domain | Supported finding | Minimum solution for MVP | Defer / avoid |
|---|---|---|---|
| **Q0BC semantics** | IMPL-01 delivered 108 tests, remediation one-line routing fix delivered 125 V2 tests; genuine OFFLINE_MOCK positive semantic route is **NOT EXECUTED**, latest proof stopped for missing Controller approval-doc/pins though Owner approved specified test parameters | 0-C creates truthful binding from original Owner approval; Gemini reviews actual non-seamed native READY→eligibility→outbox→gate→attempt; resolve economics erratum with versioned decision; narrow 0-C acceptance | New producer/state-machine rewrite; repetitive hash approval loops |
| **Event/state ownership** | Q0BC V2 has transactional Outbox; Q0C V1 also has Dispatcher/ledger; Gemini rejects dual authority | Q0BC is sole episode/transition/eligibility/outbox authority. Reuse Q0C card/HMAC/Mock transport utilities selectively; **never instantiate V1 Dispatcher** | Duplicate DB and dedup keys |
| **Time/current gate mismatch** | Engine accepts quotes up to 60s; Producer applies stricter 30s; 15m rejected confirmation can be consumed, 4H veto does not consume it | Define one explicit multi-stage freshness contract with reason codes and negative tests; no stale re-alert; do not silently alter accepted Q0B behavior | Treat every WATCH as a new alert |
| **Q0A2 real source** | Windows native deadline observed 120021.7979ms (>120s); current time/retention anchor not independently qualified; genuine NTFS production writer/race unproven; 45 .pyc out-of-scope files remain | Parallel technical Source closure; budget the watchdog earlier than 120s, test on genuine fixed NTFS, trustworthy exchange/current time receipts, align 1D/4H/1H/15m/5m and quote API; reconcile old bytecode incident internally | Block the synthetic M2 suite pending Source repairs; soften SOURCE_BLOCKED without evidence |
| **Q0F Feishu** | No real Provider implementation or authority; Gemini proposes 1,000ms pre-send gate and pre-transport zero-byte cancellation | Implement minimal Feishu card/transport and Mock tests with a short pre-send revalidation window; keep secrets in memory; exact success is HTTP 200 + integer code 0; UNKNOWN never blind-resends | Comprehensive notifications framework/dual state DB; live send without one-time destination consent |
| **M2 integration** | A detailed 24-scenario BTC/ETH/SOL interface and test map exists; Q0BC DB DDL is schema-fenced | One Sol work package using canonical Producer, Q0F mock transport, decoupled append-only Shadow (no Q0BC schema edit) and existing HTML renderer | Separate full frameworks for Shadow and Dashboard |
| **Statistics** | Program C history insufficient/negative, no qualified S1 after-cost edge | Record truthful NO_SETUP, missed/no-fill and H5/H10; forward Shadow only when qualified | Refit protected 2024–2026 historical outcomes; Alpha language |

### Core implementation priority

1. **Fix Controller-owned test provenance, not Owner consent:** the Owner-approved OFFLINE_MOCK parameters and fingerprint are documented in lt-q0bc-positive-semantic-proof-01; a real Controller-owned binding is missing. Do not invent 'new Owner approval required' for the same granted parameter set. Do not fabricate identity documents.
2. **Close only concrete functional issues:** actual non-seamed eligibility/Outbox and R1.1 economics erratum; evaluate 30s vs 60s quote split as an interface contract; verify non-replay crash boundaries.
3. **Avoid overengineering:** do not make raw SHA/manifests or 45 bytecode files recurring Owner tickets. Treat ordinary cache cleanup only after a documented safe scope and preserve source; keep investigation subordinate to Source readiness.
4. **One integrated artifact:** single runnable synthetic 2030 BTC/ETH/SOL demonstration with no live network and a truthful end-to-end HTML/report.

## 3. Four deliverable milestones (not six serial mini-phases)

### M0 — Q0R independent closure and scoped 0-C acceptance (P0, now)

**Owner:** 0-C. **Auditor:** Gemini Argon (non-author) on current Q0R. **Author:** Codex Sol for only documented defects. **Acceptance:** actual positive Owner-scoped OFFLINE_MOCK non-seamed sequence; stable native identity/plan; queue atomicity; crash/restart and UNKNOWN; no regressions; reasoned erratum decision. Existing 125/112/37 PASS receipts do not need gratuitous reruns. Separate actual approval material generated by 0-C from original Owner consent, not by Sol acting as Owner.

**Exit:** one concise decision — ACCEPT_OFFLINE_SCOPED, NEEDS_SPECIFIC_FIX, or REJECT; issue a small explicit fix list if blocked. Do not claim formal acceptance before actual evidence.

### M1 — 3-symbol unified synthetic product E2E (P0, after essential M0)

**Work package:** V070-MVP-M2-E2E-OFFLINE-INTEGRATION-01. **Owner:** Codex Sol implementation / 0-C acceptance. **Inputs:** accepted Q0BC + Q0B native + Q0F mock card/transport.

**Single path:** 2030 Source Mock → one Q0BC native Engine → 4H regime / 1H setup / completed 15m confirmation / 5m quote → eligibility/cost → one transaction Outbox → mock Feishu → independent append-only Shadow → read-only Dashboard.

**Accept:** BTC/ETH/SOL, planned 24 scenarios including nonsetup/source veto/timeout/duplicate/restart/false 15m/late quote/TP or stop ambiguity; one replayable command, short report, HTML. No external send, no account or secret.

### Parallel W1 — Q0A2 trustworthy public Source (P0, begin offline engineering alongside M0/M1)

**Owner:** Codex Sol dedicated worktree; 0-C technical acceptance. **Scope:** Windows native full-process ≤120s with budget reserve; actual fixed NTFS pinned writer; independent present/retention anchor; correct transport/intervals/quote; public endpoint/region/right checks. **Current:** SOURCE_BLOCKED. **Do not** fake success from local WSL clock or a self-hash bundle.

**Business simplification:** request one bounded approved public read-only operating envelope for a finite three-symbol pilot after checks, not a fresh Owner prompt for every GET. Do not expand 2026 protected historical reads or invent a license.

### Parallel W2 — Q0F minimal Feishu adapter (P0, begin offline work alongside M1)

**Owner:** Codex Sol separate integration-safe worktree; Gemini reviews dispatch/UNKNOWN if needed. **Scope:** one canonical Q0BC queue, card v2/Mock transport, zero external send, no V1 Dispatcher, real provider interface kept inactive, same-process coordinator when holding exclusive producer lock, no I/O inside DB transactions. Real Feishu recipient/secret configured and approved **once** later; no per-card approval.

### M2 — Genuine finite operational pilot (P0)

**Dependency:** M1 integration acceptance + W1 Source qualified and rights/one-time venue grant; separately W2 real channel setup/one-time approval. Three symbols; authorized public REST and authorized Feishu send separately; exact alertable price/stop/TP/cost; truthfully classify NO_SETUP/BLOCKED; event/provider/Shadow trace. No account/orders. Real input never self-promotes research status.

### M3 — 10-symbol operational MVP (P0/P1)

Add >=10 liquid symbols, measured request weights, incremental cache and warmup, bounded scheduler, per-symbol quarantine, 4H/1H/15m close-time execution, 5m candidate revalidation, dedup/UNKNOWN, safe restart, H5/H10 manual response actionability, complete NO_SETUP denominator and Shadow. Aim provider-acceptance P95 <=120s as an objective, not a measured achievement. One 0-C stage acceptance and rollback plan.

**Post-MVP:** [Factor Registry & Strategy Lab](V070_POST_MVP_FACTOR_REGISTRY_STRATEGY_LAB_PLAN_20261111.md) can be prepared lightly but cannot preempt P0. Existing 69 factor/28 strategy inventory is not evidence of 28 profitable live strategies.

## 4. Minimal owner decisions and reporting format

**Already delegated for routine L0:** isolated offline work, mock/test, Gemini audit, Codex fixes, docs/code commits to existing agreed branches, internal hashes/Controller receipts. **Only escalate actual external configuration:** initial venue rights/scope and source mode; initial real Feishu target/secret/sending envelope; privileged host actions/protected research/account/trading. Do not ask Owner to decide internal R1.1 test fixture paths, SHA256 value, database filename, dashboard placeholder (offline use .invalid) or whether to include comprehensive test logs.

Owner-facing update **only**: (1) what now works, (2) what still blocks the next milestone, (3) which worker is assigned and the next outcome, (4) any genuine external permission needed. No 100-page report requirement.

## 5. Reconcile after newly received evidence

If a signed Controller Q0R acceptance, newer Gemini report, completed Q0A2 writer test or real provider evidence appears, reread exact receipts and update milestone status. Do not silently promote a worker-reported test or drafted protocol to a product release.
