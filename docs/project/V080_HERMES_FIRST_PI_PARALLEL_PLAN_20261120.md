# QUANT v0.8.0 — Hermes First, Pi in Parallel: Historical Controller Work Plan

## Controlling 2026-11-26 update — RC1 and Owner-confirmed T3
The current accepted local source baseline is v1.0-rc1 at 2a40471; P3 closed NO_CANDIDATE_BEATS_B2_V1 (9/24 trials), P4 not run, final OOS sealed; Stage 3 scoped acceptance recorded locally. Operator upgrade pending, remote code/tag publication and hosted CI unverified, S6 unauthorized. Current product is personal trading intelligence / market structure radar; no validated trading strategy. Current research horizon ~4h–5d; frozen B2 V1 remains unchanged.
Both web ChatGPT GPT-6.2 Sol and Gemini 4 Neon remain coequal combined 1-A + Controller 0-C, mutual audit and planning, one queue, one accountable Controller, no Worker self-acceptance. Both may use T3 MCP to inspect local tasks read-only, and launch/send an exact bounded task to Codex or AGY **only after Owner explicitly confirms T3 dispatch in a prompt identifying that task/prompt and executor**. No automatic dispatch, steering, restart, recurring tasks, permission escalation or live operations. Existing Owner-direct bounded offline forwarding (2026-11-24) remains valid without extra EXECUTE. T3 capability is not authorization; a draft/card/peer report does not grant launch authority. Record actual task/thread/run status, use exact provider options, pinned local base and non-overlapping write sets; no public sensitive identifiers. Keep full English copy-button cards and Chinese Owner communication.
See the canonical current checkpoint and T3 dispatch protocol linked below. **All older status, routing and execution restrictions below are historical where inconsistent with this controlling update; historical evidence and restrictions on real operations remain intact.**

- [Current checkpoint and roadmap](V080_CURRENT_CHECKPOINT_AND_ROADMAP_20261126.md)
- [Owner-confirmed T3 remote dispatch](V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md)

---


**SUPERSEDED FOR FUTURE EXECUTION SEQUENCE (Owner 2026-11-20):** [H-first, Pi-during-field-trial controlling plan](V080_HERMES_H_FIRST_PI_FIELD_TRIAL_SEQUENCE_20261120.md). The parallel H1/P1 architectural work was already delivered historically; **do not start Pi P2 engineering until Hermes is independently accepted, starts an authorized actual-use trial, and has initial operational feedback**. Pi P1 stays accepted ARCHITECTURE_ONLY. All original decisions and source pins below are retained as historical context.


- Owner direction: V080-OWNER-0C-HERMES-FIRST-PI-PARALLEL-PLAN-20261120
- Controller plan: 2026-11-20
- Status: P1_ACCEPTED_ARCHITECTURE_ONLY / H1_P0_HOLD / H1_CORRECTION_PROMPT_READY_NOT_DISPATCHED / P2_BLOCKED
- Baseline: B1–B5 independently accepted OFFLINE only; no live Binance, private account, Feishu or trading activation.

## Architecture decision

Immediate TRACK H: existing Hermes Agent v0.16.0 / upstream c2fa302e9 + a QUANT-specific read-only local tool facade + deterministic outbox/rendering + Feishu one-shot send for future approved notifications + Feishu Gateway WebSocket for future approved inbound conversation.

Parallel TRACK P: Astra analyzes Pi SDK and designs a dedicated minimal TypeScript Quant-Agent over the same frozen Quant-Agent Contract V1. Pi prototype is future work, not dispatched with this plan.

OpenClaw is DEFERRED; do not repeat three-platform comparison.

QUANT Core is the only authority for public market source provenance, Regime / Setup / Trigger, immutable episode/card status/version/reasons, entry/SL/TP/net R, expiry/reprice and journal. Neither Hermes nor Pi may upgrade WATCH to EXECUTABLE, overwrite numerical values or claim B3 private-account clearance.

## Data flow

QUANT Core (B2/B4/B5 accepted public market data and local journal)
  -> QUANT-owned read-only authenticated facade
  -> V080_QUANT_AGENT_CONTRACT_V1
  -> durable event outbox + deterministic renderer
  -> future separately authorized Hermes one-shot Feishu outbound
  -> user

User future Feishu private chat
  -> Hermes Gateway inbound websocket / user allowlist
  -> V1 read-only QUANT tool plugin
  -> optional model explanation, postvalidated to exact QUANT facts
  -> final card/version/staleness recheck
  -> future authorized Feishu reply

Pi later replaces the conversation/tool/channel client, NOT the QUANT Core, facade, source contracts or business math.

## Verified local Hermes behavior

On local host, hermes --version reports Hermes Agent v0.16.0 (2026.6.5), upstream c2fa302e9 at /usr/local/lib/hermes-agent. Its plugin.yaml + register(ctx) / ctx.register_tool mechanism is described in the installed plugin documentation. The installed tools/send_message_tool.py has a dedicated _send_feishu() branch that instantiates a FeishuAdapter and calls adapter.send() for standalone outbound; hermes_cli/send_cmd.py exposes it through hermes send. The incoming Feishu chat path uses the Hermes Gateway WebSocket adapter. Thus H1 should reuse both native paths, not recreate the Feishu gateway. This is source review, NOT confirmation of a real Feishu send or a configured bot.

## Frozen common interface and capabilities

Contract: [Quant-Agent Contract V1](../architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md)

Read-only tools:
list_active_signals, get_signal_detail, get_market_context,
get_latest_reprice, get_signal_history, get_strategy_summary.

request_reprice is a future state-producing command and is DISABLED; only QUANT Core may make acquisition/reprice decisions subject to a separately activated B5 public-source cadence.

No generic shell, browser, arbitrary SQL/network, credentials, private account or TRADE tools in the agent's authority. Host process isolation is mandatory; tool-model visibility alone is insufficient. Synthetic cards must be visibly marked and must NOT be sent as genuine market alerts.

## Independently verified B5 state

B5 Phase A worker delivered at:
workspaces/lt-v080-personal-mvp-live-public-b5-01/

Controller independently reran B5/B1/B2/B4 27/89/54/28 offline tests (198 PASS), verified 58-file SHA manifest, reproduced wheel hash, 16 synthetic cards, eight reprices, clean/mixed installs and disabled live gates. Decision is SCOPED_ACCEPTED_OFFLINE_PHYSICAL_BINDING_READY at:
controller-decisions/V080_CONTROLLER_B5_PHASE_A_OFFLINE_ACCEPTANCE_20261120.json

Phase B actual public network NOT_AUTHORIZED. No region/route, approved retention, physical TLS peer, observed funding weight or trusted one-run activation was established. One bounded real run never grants recurring unattended scans.

## Track assignments and disjoint write sets

| Track | Assigned model | Task / write set | State |
|---|---|---|---|
| QUANT source | Sol Extra High | B5 Phase A already accepted; B5 Phase B requires separate Owner+0-C capability activation | OFFLINE_ACCEPTED / LIVE_NOT_AUTHORIZED |
| H1 Hermes original | Gemini 4 Neon XHigh, Sol fallback | workspaces/lt-v080-gemini-neon-hermes-quant-feishu-h1-01/ ONLY | DELIVERED / P0_HOLD after 54 independent PASS |
| H1 consolidated P0 correction | Gemini 4 Neon XHigh | workspaces/lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01/ ONLY | PROMPT_READY / NOT_DISPATCHED |
| P1 Pi ADR | GPT-6.2 Astra Extra High | workspaces/lt-v080-astra-pi-quant-agent-architecture-p1-01/ ONLY | SCOPED_ACCEPTED_ARCHITECTURE_ONLY |
| Controller | 0-C | freeze V1 contract, integrate docs, task audit, acceptance decisions | ACTIVE |
| Pi prototype P2 | Not assigned | Future separate work root; consumes accepted corrected H1 conformance fixtures and P1 ADR | BLOCKED_INPUT / NOT_DISPATCHED |
| OpenClaw | No executor | Deferred fallback only | DEFERRED |

The H1 and P1 workers may run concurrently because H1 implements code in its own isolated worktree while P1 writes read-only architecture reports into a disjoint worktree. Neither edits the canonical V1 contract, QUANT protected code, docs/engineering branch or the other's work root. Controller 0-C owns integration and one final acceptance per delivery.

## H1 offline exit criteria and future real Feishu gate

Offline H1: 6 read-only V1 tools and disabled request_reprice; exact source/status/reason/Decimal/expiry verification; deterministic event_id/outbox/idempotency, model-free first notice, optional validated explanation; mocked Hermes one-shot Feishu outbound and Gateway inbound private-chat commands; recipient authorizations and OS isolation; local performance measurements. Synthetic-only tests, no real messages.

Future live Feishu needs separate Owner app/bot/DM recipient allowlist and local credentials, Controller-approved platform activation and a bounded functional test. Genuine market cards additionally require separate B5 Phase B public-origin acceptance; continuous scanning requires another explicit cadence/region/budget approval. H1 offline acceptance grants neither permission.

Measure in future: discovered setups versus notified, source-to-alert delay, user response, +5/+10 actionability, duplicates/expired/suppressed, model factual consistency and token/cost, gateway disconnect/unknown receipt. Real conclusions require genuine observations.

## P1 exit criteria and next comparison

Astra P1 must pin Pi SDK sources and produce a TypeScript V1 client, provider/auth/channel separation, Feishu identity design, process permissions, session/checkpoint plan, precise ADR tradeoffs, Hermes-to-Pi migration and a bounded P2 mock prototype spec. Pi must not require B1–B5 rewrites. Do not presume that ChatGPT OAuth grants API quotas or that Google AI Pro consumer subscription includes Gemini AI Studio API allowance.

Pi P2 is a future offline-only prototype; run both on H1 V1 fixtures and measure fidelity, p50/p95 tool time, rendering, explanations, provider fallback, reconnect, operational complexity and tokens. No real dual-send to one recipient. The decision to migrate waits for H1 real-use feedback and actual Pi benchmark evidence.

## Canonical prompts and immediate Owner action

- [H1 — original Hermes/QUANT/Feishu task, delivered P0 HOLD](../prompts/v0.8/V080_HERMES_QUANT_FEISHU_H1_20261120.md)
- [Controller P0 interpretations and independent evidence](../architecture/V080_QUANT_AGENT_V1_P0_CONTROLLER_DISPOSITIONS_20261120.md)
- [Controller canonical Python/Node vectors](../architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json)
- [H1 — one integrated P0 correction prompt (not dispatched)](../prompts/v0.8/V080_HERMES_H1_P0_INTEROP_REMEDIATION_20261120.md)
- [P1 — Astra Pi architecture task](../prompts/v0.8/V080_ASTRA_PI_QUANT_AGENT_ARCHITECTURE_P1_20261120.md)

Immediate Controller action: **Reconcile the H1 P0 correction workroot observed locally at 2026-11-20 17:34 HKT, before forwarding or starting any additional worker.** The last Controller record (17:12) called the correction NOT_DISPATCHED, but initial code and tests now exist in the designated isolated root. A workroot alone is not independently verified authorization, completion or acceptance. Verify Owner forwarding, worker identity and the exact scope before reviewing a sealed correction. P1 is already accepted architecture-only; Pi P2 is blocked until corrected H1 V1 vectors/reference export are independently accepted. Neither P2 nor live Feishu/public calls are permitted.

The original H1 and P1 were Owner-forwarded and delivered; Controller accepted P1 architecture only and held H1 for P0. The H1 correction prompt and Pi P2 have NOT been dispatched. No real network action or credential activation occurred.
