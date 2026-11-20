# QUANT v0.8.0 — Hermes First, Pi in Parallel: Controller Work Plan

- Owner direction: V080-OWNER-0C-HERMES-FIRST-PI-PARALLEL-PLAN-20261120
- Controller plan: 2026-11-20
- Status: PLANNED / H1_AND_P1_READY_FOR_OWNER_FORWARDING / NOT_DISPATCHED
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
| H1 Hermes plugin | Gemini 4 Neon XHigh, Sol fallback | workspaces/lt-v080-gemini-neon-hermes-quant-feishu-h1-01/ ONLY | PROMPT_READY / NOT_DISPATCHED |
| P1 Pi ADR | GPT-6.2 Astra Extra High | workspaces/lt-v080-astra-pi-quant-agent-architecture-p1-01/ ONLY | PROMPT_READY / NOT_DISPATCHED |
| Controller | 0-C | freeze V1 contract, integrate docs, task audit, acceptance decisions | ACTIVE |
| Pi prototype P2 | Not assigned | Future separate work root; consumes H1 conformance fixtures and P1 ADR | NOT_DISPATCHED |
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

- [H1 — Hermes/QUANT/Feishu full task](../prompts/v0.8/V080_HERMES_QUANT_FEISHU_H1_20261120.md)
- [P1 — Astra Pi architecture task](../prompts/v0.8/V080_ASTRA_PI_QUANT_AGENT_ARCHITECTURE_P1_20261120.md)

One recommended immediate Owner action: **Forward the H1 complete prompt to Gemini 4 Neon XHigh.** P1 may be independently forwarded to Astra in parallel if desired, without blocking H1 or B5.

Neither H1 nor P1 has been automatically dispatched, and no real network action or credentials have been activated.
