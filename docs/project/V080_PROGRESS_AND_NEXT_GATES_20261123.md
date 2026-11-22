# QUANT v0.8.0 — Verified Progress, Evidence Boundaries and Next Gates (2026-11-23)

- **Status:** 1-A OWNER-REQUESTED DOCUMENTATION SYNCHRONIZATION / ADVISORY; **not** a Controller acceptance, dispatch or production grant.
- **Evidence checkpoint:** 2026-11-22 22:23 +08:00, plus direct read-only inspection of local Controller records, matching decision SHA256 values and existing sealed worker files.
- **Repository:** code/runtime branch `v0.8.0`; sole canonical documentation branch `docs/engineering`.
- **Project purpose:** personal, noncommercial, read-only trading intelligence; 2–12 h holding; 1D→4H→1H→15m→5m; initial Binance USDT-M BTC/ETH/SOL. TRADE disabled.

## 1. Evidence hierarchy and current ceiling

For every new review, first check actual `/root/workspace/project/quant-0.8.0/controller-decisions/`, workroots, manifests, QA and runtime receipts, then current `docs/engineering` HEAD. This checkpoint can become stale; newer genuine Controller receipts supersede it. **Worker-reported PASS ≠ independently reproduced PASS ≠ Controller scoped acceptance ≠ real authorization ≠ genuine live observation.**

| Domain/stage | Verified decision at checkpoint | What it does NOT prove |
|---|---|---|
| R1/B1–B5, H1 corrected, H2-A/H2-B, H3/H3-B, H4 | Independently scoped OFFLINE accepts, H4 336 tests PASS and 103 seals | No real Binance/Feishu/LLM |
| S1 / A1/post2/post3 | OFFLINE local derivatives accepted | Production host/release/route/enrollment readiness absent |
| S2 V2 one-run Canary derivative | `SCOPED_ACCEPTED_S2V2_OFFLINE_DERIVATIVE_ONLY`; 39/39 seals; 55/55 tests, 10 fail-closed checks and 14 frozen V1 rollback cases reported independently PASS | No physical network transport, real signed grant, production enrollment, KR-specific venue proof or authentic 2-GET |
| Optional account risk + local CLI | `SCOPED_ACCEPTED_OPTIONAL_RISK_LOCAL_CLI_OFFLINE_ONLY`; 36/36 seals; 12/12 tests and 6 fail-closed checks | Account overlay disabled by default; synthetic 2%/3% trade-risk and 6%/8% daily limits are proposals, not real position sizing |
| Astra S3 admission research | `SCOPED_ACCEPTED_S3_DOCUMENTARY_RESEARCH_ONLY`; 9/9 sealed research files | Does not establish historic fundingRate general IP debit `d` or admit an alternate source contract |
| Optional Feishu onboarding | `SCOPED_ACCEPTED_FEISHU_OPTIONAL_ONBOARDING_OFFLINE_ONLY`; local Mode0 Core CLI and Mode1 Hermes six reads | Mode2 real Feishu outbound/inbound disabled; genuine provider authentication absent |
| S3 full genuine market + B2 | `FUNDING_WEIGHT_UNRESOLVED / NOT_AUTHORIZED` | No real strategy card, source eligibility or real net R |
| S4 real Feishu | `NOT_AUTHORIZED`; app/tenant/recipient/client and callback binding missing | No real delivery or authenticated human chat |
| S5 first Hermes/QUANT real human loop | `NOT_OBSERVED / NOT_AUTHORIZED` | Offline H4 and local Mode0/1 do not count |
| S6 recurring H; S7 Pi P2; S8 private overlay | S6 unauthorized; Pi P2 Owner-deferred; Layer2 real read-only unapproved | No continuing scans, Pi runtime, real account fills, or TRADE |

### Exact 2026-11-22 Controller receipts (source is CODE workroot, not copied into docs)

- `controller-decisions/V080_CONTROLLER_S2V2_WSL2_OFFLINE_DERIVATIVE_SCOPED_ACCEPTANCE_20261122.json` — SHA256 `a83511b288d49ec6a69e6853117242a099026f97f78727e67297983eae94bca8`.
- `controller-decisions/V080_CONTROLLER_OPTIONAL_RISK_LOCAL_CLI_OFFLINE_SCOPED_ACCEPTANCE_20261122.json` — SHA256 `cd895065eda8a9b0ab6a578c7b8dec165947d05ed46c29d3c3788604eb7bb1d5`.
- `controller-decisions/V080_CONTROLLER_S3_ADMISSION_RESEARCH_SCOPED_ACCEPTANCE_20261122.json` — SHA256 `41538880277d065953deeda4dd02247d36be9f002629ba1f3ad846adb7560f4e`.
- `controller-decisions/V080_CONTROLLER_S2V2_RISK_S3_THREE_TRACK_CONSOLIDATED_REVIEW_20261122.json` — SHA256 `53dd621c319b300948d670677b955d4f8742ffe95303ea28f849789fd5fdb115`.
- Subsequent **planning only**, `controller-decisions/V080_CONTROLLER_NEXT_STAGE_WSL2_S2_RELEASE_AND_S3_PREP_PLAN_20261122.json`, issued 22:23; SHA256 `0eb397989ce1d7146e8094c89190cc46fda637c7ef71f512be657936f650d59c`; `new_dispatch_issued=false`.
- Feishu local onboarding record: `controller-decisions/V080_CONTROLLER_NEON_FEISHU_OPTIONAL_ONBOARDING_OFFLINE_SCOPED_ACCEPTANCE_20261122.json`, issued 17:07.

Independent local SHA256 verification of the first four Controller files matched, and `SHA256SUMS` of the three S2/risk/S3 worker packages rechecked as 39+36+9 matches. This does **not** claim an additional fresh 55/12-test rerun by 1-A.

## 2. Genuine blockers, not administrative placeholders

**S2 public Canary:** standalone V2 wheel has a synthetic transport by design; physical network-capable derivative has not been accepted. KR is Owner-declared/attested; applicability of the particular USD-M public routes is unproved. Real direct Windows→WSL2 egress, TLS CA/SNI/peer, independent shared-IP headroom, runtime UID/storage enrollment, acceptable restore/reboot behavior, genuine Controller verification key, exact release grant and Owner foreground challenge are unresolved. V2's `COHERENT_PRIVILEGED_ROLLBACK_RESIDUAL` is explicitly documented; do not represent two local stores as immunity to administrator-coordinated rollback. Zero live authorization.

**S3 full market:** Plan A has 39 GET with budget `39+3d`, where history `/fapi/v1/fundingRate` general IP debit `d` remains UNKNOWN. The release bound of 64 requires a documented integer `d≤8`, but this necessary inequality is not authoritative evidence of `d` or sufficient shared/native/family headroom. Plan B: 36 GET / known weight 39, **diagnostic only** (`NOT_EVALUATED`, no strategy cards). Plan C: future funding-cost bound not demonstrated; research only. Do not silently replace B2/B4 or certify live eligibility.

**S4 Feishu:** local Mode0/Mode1 can be independently useful without provider access. Actual app/tenant, recipient and client identities, provider auth, one deterministic sender, authenticated inbound callbacks, finite quotas and authorized send/receive are separate holds. Do not assume local tests satisfy S5.

**S5:** no verified true source→Core→Hermes/Feishu→human-use episode. A genuine `NO_SETUP` on a separately admitted market run is a valid truthful local decision result; never synthesize EXECUTABLE to manufacture a notification.

## 3. Revised single-line priority sequence (1-A advisory; Controller retains queue and acceptance)

| Priority | Owner-visible milestone | Executor / efficiency | Exit / hold |
|---|---|---|---|
| **P0a NOW** | Default-disabled S2 real-transport-capable **offline** release-bound candidate, reuse accepted V2; loopback TLS/no-proxy/zero-retry and exact two routes | Sol XHigh for security-sensitive physical seam; one isolated workroot | Independent 0-C acceptance; no real DNS/TCP/GET or live grant in this task |
| **P0b PARALLEL** | Minimal KR/WSL2 Owner-local evidence inventory; reuse accepted probes/collectors; no new validator | Owner evidence + Neon (use lower effort/Hydrogen for purely mechanical docs if appropriate) | Per-gate VERIFIED/UNKNOWN/BLOCKED with attributable, sanitized evidence; no VPN/region bypass |
| **P0c PARALLEL OWNER PREP** | Gather Feishu app/tenant/recipient/client/callback prerequisites, no provider connection yet | Owner; Hydrogen for non-sensitive checklist | Readiness inventory only, not S4 activation |
| **NEXT REAL MILESTONE — SEPARATE** | Controller review + actual S2 venue/route/restore/shared-IP approval + exact one-time signed authorization, followed only by authorized two GET | Owner and 0-C; operator per exact future authorization | Real S2 results `NOT_EVALUATED`, 0 cards, 0 retries; hold cleanly if any input unknown. No automatic authorization by this roadmap |
| **P1 CONDITIONAL** | S3 release-bound zero-retry **offline** candidate from pinned H2-A 3-file patch; Plan A unchanged, B diagnostic; no real route | Sol High/ XHigh on security-signature changes | Scoped offline QA, never invent `d`; may progress while S2 real is externally blocked **only if it does not displace S2 resolution** |
| **AFTER SEPARATE GATES** | Genuine S3 local Core decision via accepted Mode0 CLI → separately authorized S4 sender/inbound → S5 human loop | Sol H/Core integrator, Owner 0-C; Feishu owner separately scoped | Source provenance + immutable decision + actual send/query/response/unknown telemetry; no fake signal |
| **AFTER S5** | S6 bounded field use → QI1 and QL1 in a shared immutable schema → QB1 backtesting → QR1 research | Sol (QL1/H), Neon or Sol (QI1), Astra only on real architecture forks | Genuine measurements, no lookahead/fee omissions; Pi P2 offline shadow only after H baseline; no second sender |

**Key 1-A adjustment to the 22:23 planning note:** keep the two planned P0 *offline* efforts, but explicitly insert a **separate genuine S2 readiness/authorization/one-shot Canary milestone** before treating S3 engineering as the critical product path. Offline S3 work can be performed conditionally while external S2 prerequisites remain blocked, but should not become an infinite replacement for the first actual public GET. Keep Owner Feishu setup as lightweight parallel preparation. Freeze risk CLI rather than expanding it now.

No new worker is dispatched by this document; existing 22:23 Controller plan is **planning only**. The Owner Direct Offline Protocol permits named, bounded work only when Owner explicitly forwards a complete card and says execute (record `OWNER_DIRECT_OFFLINE_STARTED`); real Binance/Feishu/LLM/private/TRADE remain separately gated.

## 4. Product boundaries and role/prompt rules

- Core B2/B4 owns WATCH/EXECUTABLE/NO_SETUP, SL/TP, net R and source eligibility. AI explains or challenges, never promotes/rewrites numerical decisions.
- QI1/QL1 implementation is **after genuine S5 baseline** (design research may proceed earlier only if it does not block H). QL1 preserves episode, delivery, human response, AI annotation and **hypothetical vs verified** outcomes. QB1 must use point-in-time/no-lookahead and venue-aware costs; QR1 is hypothesis-driven, independently validated, Owner-approved.
- Controller 0-C: single task queue/independent acceptance; 1-A: advisory only. Astra: major architecture/methodology forks; Sol: complex integrated engineering; Neon: peer complex executor on disjoint scope; Hydrogen: low-risk docs/fixtures/checklists. Account for complexity, quota and cost rather than always XHigh.
- Every Owner-facing full task/new-chat prompt MUST be delivered as a **copyable card containing the complete prompt with a copy control/button where UI supports it**. Prefer a complete WritingBlock/CodeBlock with built-in Copy when custom clipboard controls are unavailable; never simulate a fake button, deliver truncated text or only a URL. See [mandatory prompt-card standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md).
- Canonical newly prepared 0-C bootstrap: [2026-11-23 Controller 0-C startup prompt](../prompts/v0.8/V080_NEW_CHAT_CONTROLLER_0C_20261123.md).

**No source code edits, live provider calls, private-account calls or order actions are authorized by this progress document.**
