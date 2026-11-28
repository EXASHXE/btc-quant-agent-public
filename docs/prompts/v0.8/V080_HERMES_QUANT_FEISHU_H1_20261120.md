# QUANT v0.8.0 — H1 Hermes + QUANT + Feishu Offline Integration

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

Task ID: V080-HERMES-QUANT-FEISHU-INTEGRATION-H1-01
Primary executor: Gemini 4 Neon XHigh
Fallback: GPT-6.2 Sol High/Extra High if Neon capacity is insufficient
Dispatcher and sole independent acceptance: Controller 0-C
Status: READY_FOR_OWNER_FORWARDING / NOT_DISPATCHED
Scope: OFFLINE SYNTHETIC INTEGRATION ONLY. Real Feishu, Binance, model account, credentials and execution calls are NOT AUTHORIZED.

## 0. Mission and non-negotiable boundary

Build one complete, isolated Hermes H1 integration package for the future QUANT-to-Feishu notification and conversation workflow. Deliver QUANT read-only local tools, deterministic market-card rendering, durable idempotent notification outbox, simulated Feishu chat commands, optional model-assisted explanation with strict fact checking, and useful interaction/performance metrics.

QUANT Core alone owns data provenance, market Regime/Setup/Trigger, SignalEpisode and card identity, WATCH/EXECUTABLE/INVALID/SOURCE_BLOCKED and other statuses, reasons, entry band, hard SL, TP1/TP2/TP3, net after-cost R, expiry, no-chase, reprices and immutable journals. Hermes must never rewrite or upgrade a Core status or numeric field, invent account risk clearance, read B3 private account, trade or independently acquire Binance data.

Develop offline first: no actual Feishu bot send/connection, Hermes gateway real login/start, real OAuth/API/model token use, actual Binance request, external deployment or autonomous polling. Plugin configuration and test profiles must not touch the Owner's real Hermes config or credentials. Do not dispatch any other worker from within H1.

## 1. Mandatory read-first and source pins

Project root: /root/workspace/project/quant-0.8.0/
Code baseline: v0.8.0 @ bd144f2d15836bb84786c91aec571df77351bf5c
Documentation: /root/workspace/project/quant-docs-engineering/ branch docs/engineering; verify its latest HEAD and status.

Read and hash the controller-frozen shared contract:
docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md
Contract ID V080_QUANT_AGENT_CONTRACT_V1; H1 and Pi P1 are read-only consumers of this shared document. NO H1 modifications to V1.

Read canonical Project Home, Roadmap, Model Routing Policy, Documentation Branch Policy, Prompt Copy Card Standard and Owner's V080-OWNER-0C-HERMES-FIRST-PI-PARALLEL-PLAN-20261120.

Accepted QUANT read-only inputs:
- B2 market cards, SignalEpisode, Decimal risk engine, append-only journal:
  workspaces/lt-v080-sol62-personal-mvp-market-decision-b2-01/
- B4 source receipt, causal public fixture bridge:
  workspaces/lt-v080-personal-mvp-public-source-bridge-b4-01/
- B5 Phase A official-host physical-source binding and synthetic cards:
  workspaces/lt-v080-personal-mvp-live-public-b5-01/
  Controller status SCOPED_ACCEPTED_OFFLINE_PHYSICAL_BINDING_READY; genuine Phase B NOT AUTHORIZED.
- B3 is a forbidden private-data boundary. Do not import or read its private database.

Check Controller decisions, manifests, accepted wheel hashes and source immutability. Stop on any mismatch.

Actual installed Hermes on this machine: /usr/local/lib/hermes-agent, observed v0.16.0, upstream commit c2fa302e9. Read the local source/docs, not a guessed future API:
- website/docs/user-guide/features/plugins.md
- website/docs/guides/build-a-hermes-plugin.md
- hermes_cli/send_cmd.py
- tools/send_message_tool.py, including _send_feishu
- gateway/platforms/feishu.py
- installed plugin/gateway/Feishu tests.

Controller confirmed installed Hermes has plugin.yaml with register(ctx) and register_tool, project/user plugin opt-in, a standalone _send_feishu outbound path used by hermes send, and a Feishu WebSocket gateway for inbound conversation. Independently verify the actual signatures, optional dependencies and mock boundaries. Do not assume a running gateway is required for standalone Feishu outbound. Conversely, do not assume one-shot outbound provides multi-turn inbound chat.

Create a single isolated work root:
workspaces/lt-v080-gemini-neon-hermes-quant-feishu-h1-01/
No writes to B1–B5, Program J, /usr/local/lib/hermes-agent, real ~/.hermes profiles, live Feishu config, canonical docs, controller decisions or Pi P1 workroot. If needed use a fresh scratch HERMES_HOME with deterministic fake configuration.

## 2. Quant-Agent Contract V1 facade

Provide one small QUANT-owned local API service, preferably a protected Unix-domain socket with peer UID checks and restrictive filesystem ACLs. Hermes plugin must never read QUANT source SQLite directly. Localhost without authenticated OS principal is insufficient.

Facade process:
- Reads only selected approved market-side B2/B4/B5 synthetic journal fixtures using read-only connections and integrity/source/chain verification.
- Projects the exact canonical V1 SignalSnapshot: episode_id, immutable card_id and card_version, symbol, direction, family, original market_status and reason codes, source evidence class and digests, source/data-as-of and observed times, absolute expiry, freshness, Decimal string plan fields and immutable reprice references.
- Account fields stay UNAVAILABLE / MANUAL_ACCOUNT_CHECK_REQUIRED / UNKNOWN sizing.
- Does not invent a native card integer version; if source has no version, use a deterministic immutable journal/event identity with documented mapping. Unknown source field stays UNKNOWN/null, never fabricated.
- Revalidates source/version/status/expiry at each read and again just before notification or chat reply.
- Enforces request identity, local authenticated principal, recipient/tool allowlist, bounded cursors and pagination, max payload size, timeout and redacted errors.
- Refuses caller-supplied SQL, file paths, unknown symbols, private data, forged genuine-source labels and arbitrary tool names.

Exactly seven V1 tools:
1. list_active_signals — bounded verified summaries
2. get_signal_detail — exact immutable card
3. get_market_context — public-only accepted source context
4. get_latest_reprice — latest ALREADY-RECORDED +5/+10 result
5. get_signal_history — bounded immutable journal
6. get_strategy_summary — factual family definitions/counts, no profitability claim
7. request_reprice — hard-disabled, always REPRICE_NOT_AUTHORIZED, no new acquisition or mutation.

No generic shell, terminal, browser, arbitrary HTTP, filesystem, SQL, secret, trade or Feishu sending operation is exposed as a model tool. Hermes may ship privileged built-ins; isolate the actual host process/user/container so model tool hiding is not the sole protection.

V1 schema and typed errors must remain immutable. If incompatible, stop and escalate the exact field/contract issue instead of silently changing the shared contract.

## 3. Hermes plugin and offline Feishu chat flows

Implement a normal Hermes plugin using actual installed plugin manifest and register(ctx) APIs. It calls only the authenticated local QUANT facade and has no direct QUANT DB/file privileges.

Use an isolated fake Hermes profile. Do not run hermes gateway setup with real credentials, enable any real bot or start a real Feishu gateway.

Mock private Feishu conversations with these deterministic Chinese workflows:
- 当前机会: list current verified signals.
- 查看 BTCUSDT / 查看 episode: exact card details.
- 为什么 WATCH: display original Core reason codes and optional constrained explanation.
- 复价: read latest recorded reprice, never fetch new market data.
- 最近信号: bounded signal history.
- 策略说明: precise strategy description, without positive-alpha claims.

Unknown natural language may be routed through an optional strict command-intent parser, but the parser must produce allowlisted tool args only. Protect against prompt injection, quoted fake commands, forged chat identity, unauthorized users, group or bot-self events, stale callbacks and cross-session state leakage. Private DM and Owner allowlist are the only proposed later live scopes.

Implement model-optional explanation for an existing signal card, completely outside the immediate alert path. Use short validated numeric/status context, schema-validated response, no invented prices or reasons, no hallucinated entry advice and an automatic fallback to deterministic QUANT facts when model unavailable/quota exhausted/response invalid. Do not merge LLM content into the immutable Core card.

## 4. Deterministic outbox + Feishu delivery interface

Outbox event_id is SHA256(canonical_json([contract_id, channel, recipient, episode_id, card_id, card_version, market_status])).

Implement persisted transaction-safe states CREATED, READY, ATTEMPTED, PROVIDER_ACK and classified RETRYABLE/PERMANENT/UNKNOWN_DELIVERY. Deduplicate enqueue, protect against repeated workers and crashes, cap retries/backoff, expire stale messages and retain provider acknowledgment/message_id where available.

Do not claim end-to-end exactly-once delivery. After UNKNOWN_DELIVERY, treat duplicate risk explicitly; provider ack is not user read receipt. On every send/retry, recheck latest Core version, source evidence class, market status, freshness, absolute expiry and recipient authorization. Suppress misleading stale/superseded/executable announcements rather than sending an outdated card.

Model-free renderer preserves exact symbol, direction, market_status and original reason codes, entry range, stop, TP1/TP2/TP3, net R, source as-of and expiry, account unavailable and source banner. An EXECUTABLE synthetic card must still be labeled SYNTHETIC_QA_ONLY / NOT_A_REAL_TRADE_SIGNAL, never delivered as genuine.

Provide two mockable delivery paths:
A. Hermes standalone outbound via the installed hermes send / _send_feishu implementation — confirm implementation and mock physical Feishu SDK, no real send. No LLM or gateway dependency on this immediate notification path if current code supports direct outbound.
B. Hermes Feishu WebSocket gateway for inbound multi-turn chat — test fake gateway event callbacks and responses, do not implement a new Feishu gateway.

Record when the actual gateway is required, how identity is mapped to a chat, mock send result, errors and uncertainty. The Sender must not open real production Feishu credentials during offline QA.

## 5. Local performance evidence

Measure local-only mock timeline:
QUANT source as-of -> verified card -> outbox created -> attempt start -> provider mock acknowledgment -> inbound user request -> current-status confirmation -> reply, distinguishing model latency, tool latency and queue delay. Also record duplicate/expired/missed alerts, +5/+10 actionability, explanation consistency, model quota/provider error/fallback, reconnection and unknown ack.

Clearly label every simulated latency and synthetic PnL/signal denominator. Do not claim real Feishu delivery, actual human response delay or live market signal success from offline data. No external telemetry or unredacted chat content in logs.

## 6. Adversarial offline QA

All tests must run loopback-only within a network-isolated Linux namespace. Minimum scenarios:
- Frozen V1 schema and exact source Decimal/status/reasons fidelity, no mutable remapping.
- WATCH/EXECUTABLE/INVALID/SOURCE_BLOCKED/NO_SETUP/expired/superseded and synthetic-vs-genuine misclassification.
- Feishu private DM commands, user/chat allowlist rejects, cross-chat confusion, unauthorized group, quote spoof, bot-self event, malformed input.
- Duplicate event ID and concurrent enqueue; crash during send/ack; delayed Feishu message_id; 429/5xx and permanent errors; gateway restart; UNKNOWN_DELIVERY; expiry before retry.
- Expired or superseded card between enqueue and actual send gets suppressed; no stale notification accepted.
- Model timeout/quota/error/hallucinated values fails cleanly; deterministic model-free notice remains available.
- request_reprice yields REPRICE_NOT_AUTHORIZED before any B5 source action or journal write.
- Sandbox process cannot use generic OS/filesystem/credential tools and cannot access B3 private DB.
- Installed Hermes plugin registration/Feishu mocks work against v0.16.0 exact local source interfaces; clean install and mixed package compatibility.
- No real Feishu/Binance/model API requests, no user key/secret reads, no real Hermes gateway activation.
- Accepted B1–B5/R1/Astra/Program J seals and tracked code/docs trees remain byte-identical.

No arbitrary test-count target; deliver actual PASS/FAIL/SKIP and exact commands/logs, comprehensive negative coverage and final SHA256SUMS.

## 7. Deliverables, stop conditions and final handoff

All files confined to isolated H1 workroot. Deliver:
- isolated distributable Hermes plugin/source package and QUANT facade with versioned schema and tests;
- H1_QUANT_FACADE_IMPLEMENTATION.md, H1_OUTBOX_AND_RENDERING.md, H1_RUNBOOK.md;
- H1_QA_REPORT.md, H1_WORKER_RESULT.md, CONTROLLER_HANDOFF.md;
- synthetic source/card/Feishu input fixtures, deterministic notification cards, example conversations, model mock failures and measurement reports;
- repeatable install/demo/check commands, pinned deps/source versions, wheel if appropriate;
- SHA256SUMS sealing every final file, including docs, source, fixtures, tests and proof logs.

Stop and report material mismatch if Hermes local implementation cannot be integrated without core modification, if genuine network or credentials are needed, B5/source evidence would be mislabeled, a shared V1 contract change is required, private B3 data becomes reachable, or a competing writer exists.

Integrate/test/fix within one package, then submit READY_FOR_CONTROLLER_REVIEW; do not self-accept, start other workers, request per-module approvals or activate external abilities.

Controller maximum outcome: SCOPED_ACCEPTED_OFFLINE_HERMES_QUANT_FEISHU_H1_ONLY. Real Feishu sending/inbound, credentials, real model logins, recurring polling, private Futures data and TRADE remain separately unauthorized.

Worker Chinese handoff: task ID, actual model/effort, Hermes exact version/commit, implementation/workroot, all V1 tool schemas, one-shot-versus-gateway verification, outbox and model fallback behavior, QA commands/results, wheel/seal hashes, permissions/no-network proof, remaining activation gates, status READY_FOR_CONTROLLER_REVIEW.

End H1 task.