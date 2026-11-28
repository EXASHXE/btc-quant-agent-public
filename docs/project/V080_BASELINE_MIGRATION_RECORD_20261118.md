[Reading 35 lines from start (total: 35 lines, 0 remaining)]

> **Current navigation (2026-11-28):** [Wave D checkpoint](V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.


# QUANT v0.8.0 — Baseline Migration Record (2026-11-18)

## GitHub
- Repository: EXASHXE/btc-quant-agent-public
- Executable code/runtime branch: v0.8.0
- Branch ancestry: executable v0.7.0 branch plus the inherited repository history.
- The branch is the active v0.8.0 code/runtime baseline. The sole canonical documentation branch is docs/engineering; project documents, roles, architecture, roadmaps, task cards, handoffs and new-chat prompts must be updated there. Matching documentation files on v0.8.0 are historical/non-authoritative mirrors.

## Local
- New local root: /root/workspace/project/quant-0.8.0/
- Program J input: /root/workspace/project/quant-0.7.0/lt-program-j-realtime-advisory-01/
- Copied snapshot: /root/workspace/project/quant-0.8.0/baseline/program-j/
- Manifest: baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json
- Manifest records 323 copied files and 4,369,232 bytes. Build caches, build outputs, audit logs, disposable virtual environments, wheelhouse and packaged zip files were excluded.
- The copied Program J baseline is read-only. New code belongs in a task-specific workspace under workspaces/.

## Owner authorization source
- Source: /root/workspace/project/quant-0.7.0/OWNER_STANDING_M2_AUTHORIZATION_20261024.md
- Destination: /root/workspace/project/quant-0.8.0/OWNER_STANDING_M2_AUTHORIZATION_20261024.md
- SHA256 on both source and destination: 094780240fb440fc550326fbb3797ee60d26cb9e776374fcbc2c0645818830c6
- Provenance remains CURRENT_USER_DIRECT_MESSAGE / OWNER_ATTESTED.
- No content was edited and no third-party legal certification is claimed.

## Historical v0.7.0 task state
The v0.7.0 Controller dispatch for V070-SOL62-PERSONAL-MVP-LAYER1-PUBLIC-01 recorded worker_execution_status=NOT_STARTED and work_root_created=false. The v0.8.0 R1 task uses a new task ID and new isolated workspace. The old dispatch and Controller acceptance remain immutable historical records.

## No live effects
During baseline setup:
- no Binance public/private API request;
- no API key or secret read/created/configured;
- no Feishu send;
- no order/trade/withdrawal/transfer;
- no host clock/time-service change.

This record is a migration receipt, not a Controller acceptance. Controller 0-C must independently verify the baseline and issue the R1 dispatch.