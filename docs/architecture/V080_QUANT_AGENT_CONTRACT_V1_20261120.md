# QUANT v0.8.0 — Quant-Agent Contract V1 (Controller-Frozen Interface)

> **Current navigation (2026-11-28):** [Wave D checkpoint](../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.


## Controlling 2026-11-26 update — RC1 and Owner-confirmed T3
The current accepted local source baseline is v1.0-rc1 at 2a40471; P3 closed NO_CANDIDATE_BEATS_B2_V1 (9/24 trials), P4 not run, final OOS sealed; Stage 3 scoped acceptance recorded locally. Operator upgrade pending, remote code/tag publication and hosted CI unverified, S6 unauthorized. Current product is personal trading intelligence / market structure radar; no validated trading strategy. Current research horizon ~4h–5d; frozen B2 V1 remains unchanged.
Both web ChatGPT GPT-6.2 Sol and Gemini 4 Neon remain coequal combined 1-A + Controller 0-C, mutual audit and planning, one queue, one accountable Controller, no Worker self-acceptance. Both may use T3 MCP to inspect local tasks read-only, and launch/send an exact bounded task to Codex or AGY **only after Owner explicitly confirms T3 dispatch in a prompt identifying that task/prompt and executor**. No automatic dispatch, steering, restart, recurring tasks, permission escalation or live operations. Existing Owner-direct bounded offline forwarding (2026-11-24) remains valid without extra EXECUTE. T3 capability is not authorization; a draft/card/peer report does not grant launch authority. Record actual task/thread/run status, use exact provider options, pinned local base and non-overlapping write sets; no public sensitive identifiers. Keep full English copy-button cards and Chinese Owner communication.
See the canonical current checkpoint and T3 dispatch protocol linked below. **All older status, routing and execution restrictions below are historical where inconsistent with this controlling update; historical evidence and restrictions on real operations remain intact.**

- [Current checkpoint and roadmap](../project/V080_CURRENT_CHECKPOINT_AND_ROADMAP_20261126.md)
- [Owner-confirmed T3 remote dispatch](../project/V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md)

---


- Contract ID: `V080_QUANT_AGENT_CONTRACT_V1`
- Owner direction: `V080-OWNER-0C-HERMES-FIRST-PI-PARALLEL-PLAN-20261120`
- Status: `INTERFACE_FROZEN_FOR_H1_AND_P1_OFFLINE_WORK`
- Maintainer/acceptance: Controller 0-C
- Consumers: Hermes H1 now; Pi P1/P2 later
- Evidence source: QUANT Core read-only, approved market-side cards and journals
- **No live public/private/Feishu/trading permission is implied by this contract.**

## 1. Authority and trust

QUANT Core alone owns source provenance, Regime/Setup/Trigger, signal/episode identity and version, market status and reason codes, entry/stop/TP and after-cost net R, expiry, reprice, no-chase and immutable journals. QUANT Core's B1–B5 accepted evidence and numerical semantics must not be changed by an agent.

Hermes/Pi may read, filter, render, request (but not perform) approved operations and explain the **preexisting** QUANT market card. They cannot replace or mutate core status or numeric fields; in particular, a WATCH or SOURCE_BLOCKED signal may not be promoted by LLM opinion. The user-facing alert must state its **source evidence class**, **as-of**, **freshness** and **account unavailability**.

Agent surfaces cannot directly access B1–B5 SQLite files, B3 private account DB, raw exchange payload archives, OS keyring or TRADE modules. A small QUANT-owned facade reads approved market journals in a separate least-privilege OS process and presents a versioned local transport. Authoritative data are read at the facade and checked again before every reply/send. Plugin is an untrusted presentation boundary.

## 2. Transport, identity and isolation

Default: versioned request-response over local Unix-domain socket with restrictive `0700` parent / `0600` socket or equivalent OS-authenticated local channel, and peer UID binding where platform supports it. Loopback HTTP only with an independently verified local principal/authentication boundary; **localhost alone is not authorization**.

- Each request: `contract_id`, `request_id` (unique stable non-secret), `tool`, `args`, `principal_id` (server-authenticated), `recipient_scope`, `deadline_ms`.
- Each response: `contract_id`, `request_id`, `generated_at_ms`, `status` = `OK|ERROR`, `data` or `error`, `server_as_of_ms`, `source_evidence_class`.
- Requests may not choose a filesystem path or send a raw SQL query.
- `principal_id`/recipient authorization must be supplied by the trusted local gateway identity mapping, not accepted from an untrusted chat-text value. Audit the authenticated caller and requested tool without secrets.
- Outputs must have strict max size, pagination/cursor bounds, timeout, rate limits and deterministic JSON serialization. No streaming of arbitrary source files.
- `V1` is immutable. Future migration uses a new version or additive explicitly optional fields; P1 reads, never edits this contract.

## 3. Authoritative signal projection

The V1 `SignalSnapshot` is a **projection** of a verified QUANT card. Minimum fields:

| Field | Type/rule |
|---|---|
| `episode_id` | Opaque stable string, Core-assigned |
| `card_id` | Opaque content-linked Core identifier |
| `card_version` | Explicit immutable Core journal/version marker; if no native integer, use deterministic immutable journal event sequence plus source hash; never invent a mutable 'latest' version |
| `symbol`, `direction`, `strategy_family` | Exact QUANT Core values, enums validated |
| `market_status` | The exact Core status, including `EXECUTABLE`, `WATCH`, `INVALID`, `NO_SETUP`, `SOURCE_BLOCKED`, `NOT_EVALUATED` when supported |
| `status_reason_codes` | Original ordered Core reason codes, no agent reinterpretation |
| `source_evidence_class` | Exact segregated evidence: `SYNTHETIC_QA_ONLY` or separately accepted genuine public class; unknown/ambiguous must fail closed |
| `source_origin`, `source_receipt_sha256`, `source_publication_sha256` | Verified references where present; missing critical refs block genuine classification |
| `source_as_of_ms`, `evaluated_at_ms`, `observed_at_ms` | Distinct, UTC epoch milliseconds where known; never relabel receipt time as venue publication |
| `absolute_expiry_ms` | Core expiration, or explicit `null` with `EXPIRY_UNKNOWN`; agent must not infer TTL |
| `freshness_state` | `CURRENT|STALE|UNKNOWN`, determined by Core under its current clock policy; not an alternative `market_status` |
| `account_context_status` | For H1, `UNAVAILABLE`; do not make B3 private data available |
| `account_overlay`, `portfolio_exposure_limits`, `safe_position_size` | `MANUAL_ACCOUNT_CHECK_REQUIRED`, `UNKNOWN`, `UNKNOWN` in H1 |
| `plan` | Optional exact Core-projected entry band/hard SL/TP1–3/net R/first obstacles and fee assumptions; all prices, quantities and ratios **decimal strings**, not floats |
| `latest_reprice` | Reference to immutable Core reprice receipt/version; no invented observations |
| `reasons`, `human_action` | Explicit Core reason/event or deterministic renderer notice; mark generated explanation text separately |
| `verified_at_ms`, `contract_version` | Facade integrity verification timing and contract identity |

Do not publish sensitive private fields. If a field is unavailable in accepted Core cards, return a typed `UNKNOWN`/`null` rather than fabricate it. Every response carries the source evidence banner and `NOT_A_REAL_TRADE_SIGNAL` for synthetic cards.

An Agent-generated explanation must appear in separate `explanation` and `explanation_provenance` fields, not merge into `SignalSnapshot`. It is never accepted as a QUANT card change.

## 4. V1 tool allowlist and business semantics

Initial **read-only** tools:

| Tool | Inputs | Semantics |
|---|---|---|
| `list_active_signals` | `limit<=50`, `cursor`, `as_of_ms`, `statuses[]` | Core-verified non-expired signal summaries; return status and evidence explicitly, never infer active from cache alone |
| `get_signal_detail` | `episode_id`, optional `card_id` | Exact immutable card with original plan and reasons; recheck latest status/expiry separately |
| `get_market_context` | approved `symbol`, optional `as_of_ms` | Market-side source context only, no private account or unsanctioned acquisition |
| `get_latest_reprice` | `episode_id` | Latest already-recorded immutable +5/+10 receipt if available; none is `NOT_AVAILABLE` |
| `get_signal_history` | `limit<=50`, cursor, bounded time range | Read immutable card history, with status transitions and source evidence |
| `get_strategy_summary` | optional family/period | Definition and recorded counts only; no profitability/economic claims without prospective evidence |

Separate **state-producing business action**:
- `request_reprice`: `episode_id`, `idempotency_key`, bounded desired time, authenticated human principal.
- `DISABLED_BY_DEFAULT`; returns `REPRICE_NOT_AUTHORIZED` in H1 and Pi prototype.
- An approved future version must route to QUANT Core scheduler/source policy and budget; never let Hermes/Pi acquire new exchange data, write a card, or bypass B5 source consent. User speech is not activation.

Do not expose terminal, shell, generic HTTP/browser, filesystem, credential, SQL, Feishu send or order placement as a model tool.

## 5. Errors, consistency and freshness

Use typed errors: `UNAUTHORIZED`, `UNKNOWN_TOOL`, `INVALID_ARGUMENT`, `NOT_FOUND`, `SOURCE_UNAVAILABLE`, `SOURCE_BLOCKED`, `STALE_CARD`, `EXPIRED`, `INTEGRITY_FAILURE`, `REPRICE_NOT_AUTHORIZED`, `RATE_LIMITED`, `TIMEOUT`, `INTERNAL_REDACTED`.

Never resolve an error by manufacturing a successful card. Unknown freshness, inconsistent status/version, missing source class, tampered digest or clock uncertainty must cause explicit warning or fail closed before **outbound** delivery.

On a notification action or Feishu reply:
1. Re-read Core snapshot and latest episode/version/expiry **immediately before send**.
2. Confirm recipient allowlist, correct evidence classification and operator-approved capability.
3. If card is expired, superseded, INVALID or source unavailable, suppress any affirmative entry notice and show current Core reason/status instead.
4. Synthetic cards are always test-only and must not be sent as genuine trading alerts.

## 6. Deterministic notification identity and delivery semantics

Notification `event_id = SHA256(canonical_json([contract_id,channel,recipient,episode_id,card_id,card_version,market_status]))`, not an LLM-derived text hash.

The local outbox is append-only with idempotent event creation and persistent states:
`CREATED -> READY -> ATTEMPTED -> PROVIDER_ACK`; failures classified as `RETRYABLE|PERMANENT|UNKNOWN_DELIVERY`. Retry with bounded backoff and expiry checks; `UNKNOWN_DELIVERY` requires cautious reconciliation and may cause duplicates, so **do not claim end-to-end exactly-once Feishu delivery**. Record platform message IDs and timestamps when supplied; receipt is not proof of user's visual reading.

Immediate notification text is deterministic and model-free. The LLM explanation is optional, separately measured, and must not change numeric fields, market status or reason codes. Explanations failing schema/consistency validation are discarded in favor of the exact Core card.

## 7. H1/P1 common test fixtures and acceptance

Both consumers must run the same shared, frozen conformance suite with:
- WATCH, EXECUTABLE, INVALID, SOURCE_BLOCKED, NO_SETUP, expired and superseded status.
- Synthetic vs separately hypothetical genuine evidence; attempts to relabel QA as genuine must fail.
- Missing/unknown source timestamps and clock skew.
- Backfilled/revised historical card cannot overwrite an earlier card; out-of-order event.
- A long/short B2 market plan with Decimal string exactness, TP/SL and net-R and +5/+10 reprices.
- Private B3 DB inaccessible and account status UNAVAILABLE.
- Authn/authz negative: unlisted principal, chat ID spoof, wrong recipient, tool not allowed, direct socket untrusted peer.
- Outbox duplicate, gateway restart, unknown provider delivery, stale suppression and retry after expiry.
- Model/provider failure without delaying model-free notification.
- `request_reprice` refusal before any source request or state mutation.
- Zero real Binance/Feishu/model outbound/network requests in offline acceptance.

H1 owns the executable mock/reference implementation and conformance fixtures under its **isolated** work root, based on this frozen schema. Astra P1 analyzes the architecture and reuse strategy without editing H1 files; subsequent Pi prototype can reuse versioned H1 tests only after Controller acceptance.

## 8. Capability activation gates

The following remain separate and **NOT AUTHORIZED** under the owner planning directive: (1) B5 Phase B genuine public source or recurring scanning; (2) real Feishu bot/user and delivery; (3) real private Futures USER_DATA; (4) trading or portfolio clearance; (5) live OAuth/model usage or paid quota claims. No cross-capability permission inheritance.

Hermes plugin and Pi SDK have no authority to expand a Core source run. Owner-approved local bot credentials and model logins are configured **only by Owner** after separate gates; never inspect, paste, duplicate or store them in QA artifacts.

## 9. Freeze policy and review

- Controller 0-C freezes V1 at this canonical document and its immutable SHA-256 after docs commit.
- H1 implements V1 with a single core writer. P1 reads same V1 for ADR/SDK planning. No shared concurrent modifications to V1, B1–B5, or canonical docs.
- Any contract breaking change needs Controller review and a new version number, with fixtures demonstrating compatibility or migration.
- No H1/P1 worker is automatically dispatched by writing this document.
