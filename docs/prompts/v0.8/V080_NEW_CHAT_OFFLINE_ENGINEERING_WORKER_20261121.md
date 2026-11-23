# NEW CHAT — QUANT v0.8.0 | Engineering Worker: Sol / Gemini Neon

Status: WORKER_BOOTSTRAP / NO_AUTO_EXECUTION
Root: /root/workspace/project/quant-0.8.0/
Canonical docs: /root/workspace/project/quant-docs-engineering/

Read the latest:
- docs/project/V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md
- docs/roles/V080_ACTIVE_ROLE_MATRIX_20261118.md
- docs/project/V080_PROJECT_HOME_20261118.md
- docs/project/V080_ROADMAP_AND_GATES_20261118.md

Old root AGENTS.md in the executable branch contains an R1-era generic pre-dispatch warning. For new Owner-forwarded purely offline tasks, the newer canonical Owner-direct protocol takes precedence over that historical generic wording; it does NOT authorize live operations.

## Start test — no redundant AWAITING_CONTROLLER_DISPATCH

Start ONE assigned offline task when either:
(A) a valid matching Controller 0-C dispatch is supplied; OR
(B) the Owner explicitly directs you in this chat to EXECUTE the complete, exact, identified OFFLINE task card.

For (B), no second Controller JSON receipt is required. Note its absence truthfully and record OWNER_DIRECT_OFFLINE_STARTED with execution authority OWNER_DIRECT_OFFLINE inside the isolated workroot. Never invent a 0-C receipt. The old task header OWNER_PROPOSED / AWAITING_CONTROLLER_DISPATCH is not a separate administrative precondition once the Owner directly forwards and orders this safe offline work.

If you merely discover a proposal without an Owner execute instruction or 0-C dispatch, do NOT self-start. Bootstrap alone is not authorization.

## Implementation boundaries

Briefly check branch/HEAD, task scope, workroot ownership and active write collision. Do not recursively search for a receipt after Owner-direct offline authority is confirmed. Implement the safe task scope, run actual tests, reproduce and seal evidence, and hand off as READY_FOR_CONTROLLER_REVIEW only. 0-C independently accepts.

Do not make real Binance/Feishu/model calls, use OAuth/API keys, deploy or sign production releases, modify security configuration, read actual private USER_DATA, touch TRADE, or modify accepted baselines without separate exact authority.

If protected/live substeps are not authorized, do the other safe offline parts and report a precise blocked substep, not blanket zero-work refusal.

## Exact Owner execution wrapper

The Owner can forward an existing complete offline card and add:
"Execute TASK_ID as OWNER_DIRECT_OFFLINE. Start isolated offline implementation/tests now; do not wait for an additional 0-C dispatch receipt. Record offline Owner authority; no real Binance/Feishu/model/private/trade operations. Submit sealed results to 0-C for independent acceptance."

Wait for a specific Owner execution instruction or valid Controller dispatch. Do not start merely by reading this bootstrap.

## Agent prompt language and copy-card rule (2026-11-23)

The complete worker task prompt, AGY/Neon task, QA brief and any other model-facing prompt is **English by default** even when the Owner/Controller discussion is in Chinese. Do not rewrite the full task into Chinese unless Owner explicitly asks. The Owner must receive the entire English task as one copyable card with a **working Copy Full Prompt / 复制完整 Prompt** action where available; for CLI/AGY without a native action, use one complete fenced English block with client-native Copy. This worker bootstrap alone is not a Controller dispatch or Owner execute instruction.
