# QUANT v0.8.0 — P1 Astra Pi Quant-Agent Architecture ADR

> **Current navigation (2026-11-28):** [Wave D checkpoint](../../project/V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](../../project/V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.

Task ID: V080-ASTRA-PI-QUANT-AGENT-ARCHITECTURE-P1-01
Executor: GPT-6.2 Astra Extra High
Dispatcher and independent architecture acceptance: Controller 0-C
Status: READY_FOR_OWNER_FORWARDING / NOT_DISPATCHED
Scope: ARCHITECTURE_AND_REQUIREMENTS_ONLY; no live providers, Feishu, Binance, credentials or prototype implementation.

## 0. Objective and explicit non-goals

Design a long-term lightweight, QUANT-specific Agent using the Pi SDK, informed by the selected Hermes H1 first-loop experiment. Pi is **not** a second currently active production platform and OpenClaw is deferred. Avoid another general QUANT full-system audit or a broad three-framework evaluation.

Deliver a precise, implementable architecture decision record (ADR), TypeScript SDK contract shape and one bounded future Pi P2 prototype specification. Do not build a second Feishu gateway or run live QUANT/Feishu/model calls in this task.

QUANT Core remains authoritative for source provenance, market regime/setup/trigger, SignalEpisode/version, market status and reasons, entry/SL/TP/net R, expiry, no-chase and immutable reprices. Pi is only the conversation, tools, explanation, provider and channel layer.

## 1. Pin evidence and frozen shared V1 interface

Read from /root/workspace/project/quant-docs-engineering/ branch docs/engineering:
- docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md — immutable, Controller-frozen V1, do NOT edit it.
- docs/project/V080_PROJECT_HOME_20261118.md
- docs/project/V080_ROADMAP_AND_GATES_20261118.md
- docs/project/V080_MODEL_ROUTING_POLICY_20261119.md
- docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md
- H1 prompt: docs/prompts/v0.8/V080_HERMES_QUANT_FEISHU_H1_20261120.md

Read accepted B2/B4/B5 market public evidence schemas, B3 only to mark forbidden private data. Verify B5 Phase A Controller acceptance; Phase B still unapproved. Do not edit accepted upstream source or canonical docs.

Pi source of interest: https://github.com/earendil-works/pi and https://docs.pi.dev/latest/sdk . Determine exact current SDK package names, version/commit, module boundaries, event/session APIs and provider interfaces from official source and docs, not guessed examples. If no local pinned Pi clone is available, use a documented remote pinned source reference and label it as unexecuted architecture evidence; never invent local installation results.

Astra P1 writes only to its isolated workspace:
workspaces/lt-v080-astra-pi-quant-agent-architecture-p1-01/
No shared writes to Hermes H1, QUANT Core, B1–B5 or Controller-frozen Contract V1. Architecture and independent review only.

## 2. Required Pi SDK / Harness architecture

Map in a precise TypeScript diagram and pseudotypes:
- Pi coding-agent SDK session creation, lifecycle, provider/model selection, context and history, event stream, cancellation, context compaction and recovery.
- Pi agent-core tool-call loop, deterministic tool registry/discovery, retry/error budget, structured outputs and checkpoint/session persistence.
- Tool adapter for exactly the Quant-Agent Contract V1 methods: list_active_signals, get_signal_detail, get_market_context, get_latest_reprice, get_signal_history, get_strategy_summary; request_reprice disabled unless separately activated.
- QUANT-owned local API process with authenticated socket/OS isolation and schema validation. No Pi direct DB or B3 private access. No generic terminal, shell, browser, filesystem mutation or API client in the QUANT model capability set.
- Inbound Feishu private-chat channel adapter only for a future approved mode; authenticated OpenID/chat/recipient mapping and session isolation; strict outgoing recipient checks.
- A model-free deterministic notification path that can reuse H1's outbox and renderer semantics rather than requiring Pi or an LLM for a fast market alert.
- Optional model explanation, schema post-validation, numerical/status/reason fidelity and fallback to deterministic core explanation.
- Local latency/tokens/quota/retry/notification/error telemetry with no extraneous private data or cloud upload.

Specify one recommended runtime topology: the QUANT Core/facade, event outbox, minimal Pi agent process, optional Feishu channel and independent OS privileges. Document interface and data-flow diagrams, ownership of each durable state, backpressure and service crash recovery.

## 3. Providers and credentials — exact separation

Evaluate actual Pi provider APIs and OAuth support against **documented** behavior, especially:
- ChatGPT/Codex OAuth support and its applicable usage/terms; do not assert ChatGPT subscription provides general third-party paid API quota.
- Gemini model-provider support through a separate Gemini API key, model catalog and cost/quotas. Do not equate Google AI Pro consumer subscription with Google AI Studio API credits.
- A provider-agnostic interface and fallback routing with explicit token/cost logging, no hidden model change, and inability to upgrade QUANT status.

DO NOT read, request, print, import, connect or generate real OAuth tokens, refresh tokens, API keys or Feishu app credentials. Use FAKE values in diagrams and a separate Owner-configured future secret-store interface.

SDK capabilities and provider assumptions must be categorized VERIFIED_IN_SOURCE, VERSION_DEPENDENT, UNVERIFIED, or REQUIRES_OWNER_AUTH. No live billing/login experiments.

## 4. Hermes-to-Pi migration plan

H1 will be built independently by Gemini Neon, same frozen V1 contract. Pi must be able to consume QUANT V1 without changing any B1–B5 strategy source, public ledger, status or market math.

Provide a stepwise migration plan:
- Reuse H1 V1 conformance fixtures, mock facade, deterministic notification rendering, outbox event identity and Feishu test transcripts.
- Implement a Pi-specific strictly limited TypeScript client.
- Compare H1 and Pi on the **same** snapshots and clocks: factual/status fidelity, p50/p95 tool latency, queue-to-send delay, explanation consistency, provider failure handling, tokens, quota, operator complexity, crash recovery and authorization.
- Never run concurrent notifications to the same real recipient from Hermes and Pi. Shadow/read-only or mock-only comparison first; explicit Owner cutover and safe rollback are future gates.
- Retain immutable Core and event identities. If a future change requires new fields, version the contract and document migration without mutating V1.
- OpenClaw remains a deferred optional fallback, not an actively researched competitor.

## 5. ADR decisions and proof requirements

Write a concrete ADR evaluating:
1. Minimal Pi SDK embedding versus Pi RPC/CLI versus custom agent-core loop, under current available APIs.
2. In-process versus out-of-process QUANT tool transport and host privilege boundary.
3. Feishu session and channel design, human recipient/identity handling and delivery uncertainty.
4. Provider support and OAuth/API separation, realistic quotas/cost evidence.
5. Memory/context hygiene, tool-use injection defense, retry/cancellation and checkpoint format.
6. What Pi gains and costs compared to Hermes in this QUANT-specific workload; decision thresholds that justify or reject migration.

Do not select Pi as superior just because it is lightweight. Present measurable acceptance benchmarks and a stop/go checklist. Avoid imaginary live performance SLOs; label targets as proposed targets and actual numbers as unavailable until H1 real use.

## 6. Exact deliverables

Only in isolated P1 root deliver:
- P1_PI_QUANT_AGENT_ARCHITECTURE_ADR.md with source/commit/version links.
- P1_TYPESCRIPT_V1_TOOL_TYPES.md with explicit TypeScript interface definitions and schema validation strategy. No runnable production agent required.
- P1_SESSION_PROVIDER_FEISHU_SECURITY.md with permission, identity, failure and recovery model.
- P1_HERMES_TO_PI_MIGRATION_AND_BENCHMARK.md with measurable thresholds and test comparison.
- P1_BOUNDED_P2_OFFLINE_PROTOTYPE_TASK.md — a draft ONLY, not dispatch.
- P1_FINDINGS_AND_GAPS.md, CONTROLLER_HANDOFF.md, checked SHA256SUMS.

One architecture delivery, one Controller acceptance; no microtasks or edits outside this isolated workspace. Flag material V1 incompatibility rather than silently changing H1's shared contract.

Return READY_FOR_CONTROLLER_REVIEW / ARCHITECTURE_ONLY. No automatic Pi prototype, Feishu, model OAuth, genuine public Binance scan, private USER_DATA or TRADE activation.

Final Chinese handoff must give exact model/effort, Pi source version and citations, ADR recommendation, interfaces, Hermes migration dependencies, benchmark design, artifact hashes and unresolved risks. End P1 task.