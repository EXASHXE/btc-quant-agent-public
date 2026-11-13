# Quant v0.7.0 — Active Role Matrix (Owner revision 2026-11-13)

**Controlling model assignment:** [Hydrogen simple / Sol moderate / Astra architecture](../project/V070_ENGINEERING_MODEL_TASK_ROUTING_20261113.md). This supersedes the 2026-11-12 temporary Flash-first allocation and the 2026-11-13 conditional Hydrogen-all-L0-primary proposal **for future assignment only**. Historical stage decisions and evidence do not change.

**Mandatory prompt presentation:** [Full-text Copy Prompt Card Standard](../project/V070_PROMPT_COPY_CARD_STANDARD_20261111.md) — working "复制完整 Prompt" control for every Owner-facing new-chat/task/audit prompt, never truncated. [MVP Home](../project/V070_MVP_CLOSURE_HOME_20261111.md) · [Execution Delegation](../project/V070_EXECUTION_DELEGATION_POLICY_20261111.md) · [0-C](V070_CONTROLLER_0C_ROLE_20261111.md) · [Latest new 0-C chat](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261113_MODEL_ROUTING.md).

| Role/model | Primary responsibility | Restrictions / fallback |
|---|---|---|
| **Owner** | Product goal, external L1 and privileged L2 decisions, human trading | No repeated Owner approval for routine L0 SHA/tests/docs |
| **ChatGPT 0-C (Controller)** | Single engineering queue; classify complexity; assign, integrate, independently scrutinize and accept | Sole final Controller decision authority; no false live/source/Alpha claims |
| **Gemini 4 Hydrogen — SIMPLE engineering** | Narrow mechanical fixes, docs, deterministic tests and fixtures, low-risk isolated modules | Requires actual local model/tool verification; never independently redesign trust, time, ledger or dispatch |
| **Codex GPT Sol — MODERATELY COMPLEX engineering** | Multi-file code, Source/Outbox/SQLite/restart contracts, cross-OS and E2E integration | Use when quota available; on quota block mark PENDING_CAPACITY or delegate genuinely simple independent pieces to Hydrogen |
| **Codex GPT Astra — COMPLEX architecture analysis** | Source trust, causality, high-risk state-machine and system architecture, difficult root-cause/decision tradeoffs | Design and scientific/architecture critique; 0-C chooses, Sol implements and reviewer scrutinizes; no self-acceptance |
| **Gemini 3.8 Flash** | Backup only for SIMPLE scoped tasks if Hydrogen unavailable | No automatic promotion to Sol/Astra risk class |
| **Gemini 4 Argon** | Non-author adversarial review when available | Nov13 triage records the Q0A4 review opportunity as used; do not assume new quota |
| **Claude Opus 5.5** | Independent cross-module M2 review when explicitly available | Nov13 triage records M2 review opportunity as used; treat reports as findings, not acceptance |
| **ChatGPT 1-A** | Independent strategic/product/quant-research assessment and Owner-facing recommendations | No competing worker dispatch or Controller sign-off |
| **Q0BC V2** | Sole episode/plan/transition/eligibility/durable Outbox authority | No second Q0C V1 Dispatcher / queue |
| **Q0F** | Card/transport/response classification; reuse Q0BC authority | Real channel disabled until separate L1 approval; provider ACK is not human read |
| **Q0A / Source** | Time, provenance, retention, venue-rights, response admission and fail-closed Source status | No Source qualification from synthetic tests |
| **Human recipient** | Independent manual trading decision | No orders or account operations by the Quant system |

## Current engineering evidence and accountable work

The [Q0A5 G2/G3 FIX-01 progress report](../project/V070_Q0A5_G2G3_FIX01_PROGRESS_20261113.md) supersedes older planning snapshots for this narrow delivery. M0/M1/Q0F remain Controller `ACCEPT_OFFLINE_SCOPED`, Q0A3 `ACCEPT_FIXED_OFFLINE_SUBSET`; Q0A4 FIX03 is Controller `ACCEPT_OFFLINE_SCOPED_FIX03`. Q0A5's **C01/C02/C03 implementation is complete as a worker deliverable** but remains `PASS_G2G3_FIX_PENDING_CONTROLLER_ACCEPTANCE` (fail-first 10 FAIL/1 PASS, post-fix 12/12, WSL 28/28, Windows 6 PASS/22 SKIP). G1 Windows native dependency/WAL parity remains BLOCKED; full Q0A5/M2 offline Controller acceptance and real M2 Source/Feishu qualifications are NOT established.

**Accountability:** 0-C reviews the Q0A5 `e2e/shadow.py`, `win_capture/e1_five_tf_bridge.py`, `q0bc_v2/producer.py`, `q0f_adapter/scheduler.py` fix and original evidence before issuing a new decision. The FIX-01 worker self-reported **Gemini 4 Hydrogen (High)**, exact model slug UNKNOWN. That historical delivery does **not** reassign future moderately complex Source/Producer work away from **Sol** under the Owner routing. **Hydrogen** continues for simple bounded work; **Astra** for complex architecture analysis.

## Work allocation rule

**Hydrogen = simple, Sol = moderately complex implementation, Astra = complex architecture analysis.** A one-line change to Source trust, retry/UNKNOWN, finance/economic gate, transaction or permission code is NOT simple by line count. 0-C checks blast radius, state-machine authority, causal safety and external dependencies before task routing. Reserve one main P0 critical path; give workers full engineering prompts with measured acceptance and non-author review on high-risk paths.

L0 normal offline delegated engineering remains authorized under the Owner's 2026-11-11 policy. L1 public Binance data and live Feishu setup each require their own bounded Owner decision; L2 protected/privileged/private/account/trading actions remain disabled absent separate explicit authority.

Source and science flags stay fail-closed: SOURCE_BLOCKED=true, SOURCE_QUALIFIED=false, SHADOW_QUALIFIED=false, ECONOMICALLY_VALIDATED=false, ALPHA_CLAIMED=false, execution_authority=false, REAL_FEISHU_SEND=false. Product remains Binance USDT-M read-only, 2–12h, 1D/4H/1H/15m/5m+quote, 3→>=10 symbols; no automatic orders.