# v0.7.0 Roles, Decision Rights and Task Routing

> **Canonical:** GitHub `docs/engineering`. [Documentation Branch Policy](../project/V070_DOCUMENTATION_BRANCH_POLICY.md). Matching `v0.7.0` documents are historical copies.
Status: active product-planning guidance, 2026-10-28. Supersedes previous role routing for NEW advisory engineering only; legacy experiment authority remains intact.

## 2026-11-02 role routing and current delivery gate

**Only Controller 0-C** owns the active engineering roadmap, substantial Codex task grouping/dispatch, conflict checks and evidence-based milestone acceptance. The Strategic Advisor performs independent concentrated review on Owner request, not a second queue or routine micro-approval gate; Astra/Opus/Gemini remain optional mechanism/architecture reviewers.

The current engineering snapshot is `Session04 + LONG READY_OFFLINE_HANDOFF`, **not** live-ready: consumed historical Session03 `PARTIAL/BACKPRESSURE_BLOCKED` (Source/Shadow false); Source runtime profiling PARTIAL, native stall cause UNKNOWN; local Dashboard READY_OFFLINE; <=48h native grant absent. See [dated closure](../project/V070_SOURCE_TO_ADVISORY_CLOSURE_STATUS_20261102.md).

A new diagnostic-only Session04 <=180s native test requires an explicit Owner amendment acknowledging unresolved runtime reliability, unique session/output, separately approved key, final after-trust hash and exact signed UTC grant; do not reuse Session03. Independent LONG Owner/capture-auditor trust/approval and fresh native clock qualification remain separate. No docs-only update or passing offline test grants source access, deployment, notifications, accounts, orders, PRIMARY or protected-data access.

Codex should reuse tested L23/Source/LONG/dashboard paths, preserve original sealed evidence and the queue-128/clock-50ms hard stops, and avoid concurrent writers or reentrant lock acquisition. Deliver meaningful long-phase receipts rather than serial micro-fixes.

## Owner — product principal and approval authority
- Defines product goals, acceptable notification/operational trade-offs and risk limits.
- Explicitly approves scope for code integration, runtime deployment, data access, historical trial execution, protected holdouts, and ANY account/trading operation.
- Maintains final judgment on trading; no agent has discretionary order authority.

## Owner cadence override — 2026-10-29

Controller 0-C **alone** owns the subsequent v0.7.0 phase roadmap and delivery queue. Codex is delegated autonomous implementation, targeted/fault tests and engineering repairs within the Owner-authorized isolated/offline scope; one coherent L1+L2 or similarly grouped mandate replaces serial one-fix/micro-review chains. Owner involvement is reserved for exceptional safety questions, explicit new permissions and milestone acceptance. A single concentrated independent strategic or technical audit may be requested after substantial milestone delivery; Astra/Opus/Gemini are optional specialists, not standing gates. Never automatically integrate/deploy or open restricted datasets. Earlier [L1+L2 task card](../project/V070_L12_OFFLINE_MULTISTRATEGY_ADVISORY_MANDATE_20261029.md) is historical; current Source-to-Advisory closure decisions take precedence.

## Controller 0-C — accountable delivery coordinator
- Checks actual local state and already completed work before starting a task.
- Chooses one canonical integration baseline across R research, M market-watch feature branch and Q operating collector. Does NOT discard dirty changes.
- Produces scoped Codex cards with file boundaries, tests, stop conditions, output artifacts and Owner authorization.
- Coordinates a small product vertical slice and takes acceptance decisions based on evidence.
- Does not allocate PRIMARY budget, read prohibited source values, integrate patches, deploy or start workers without the relevant Owner approval.

## ChatGPT Strategic Advisor — independent Owner-level review
- Reviews current engineering/scientific priorities, Controller deliverables and causal/economic claims; is not a second execution controller or a mandatory approval gate.
- Uses [dedicated role contract](V070_CHATGPT_STRATEGIC_ADVISOR.md) and [new conversation handoff](../project/V070_CHATGPT_NEW_CHAT_START.md) for separate strategic/quality-assurance sessions.
- May prepare scoped 0-C task prompts at Owner request, but does not simultaneously launch or override active Controller implementation queues.
- When presenting full prompts in a chat that supports interactive controls, include a working **Copy Full Prompt** button that copies the entire prompt; otherwise provide one complete fenced copyable block. See the [dedicated role contract](V070_CHATGPT_STRATEGIC_ADVISOR.md).

## Codex — primary implementation and verification
- Implements narrow authorized change in isolated checkout/worktree, with synthetic tests and concise diff/receipt.
- Current priority: evidence-based Source Runtime stability, distinct Session04 diagnostic admission and separately granted <=48h LONG Source + local Shadow; historical Foundation work remains a preserved baseline.
- Later: plan lifecycle, user-reported fill ledger, management action compiler, risk/alert integration, and prospective evaluation.
- Never runs historical backtests, downloads new market values, modifies registered studies or operates collectors unless specifically authorized.

## Independent reviewers: Astra Argon / Opus / Gemini
- Optional critical reviews for novel economic mechanisms, statistical power/estimands, source/PIT semantics, high-risk execution changes and architecture inflection points.
- Not a standing approval committee for ordinary unit-tested engineering work.
- Reviewer recommendations are not evidence of code deployment or Alpha.
- Independent reviewer reports may disagree; Controller resolves claims against authoritative code and receipts.

## Deterministic runtime and LLM separation
- Market inputs, timestamps, price levels, plan actions, risk caps, state transitions and notifications are program-controlled.
- LLM use: interpretation of trustworthy evidence and future verified news classification. LLM not a risk-critical dependency.
- Notification sent != delivered/read; proposed plan != executed position; USER_REPORTED != EXCHANGE_VERIFIED.

## Authorization matrix (no implicit permission)
| Activity | Requirement |
|---|---|
| Read code and accepted aggregate reports | Ordinary scoped inspection |
| Modify documented project files | Explicit user doc-edit request |
| Change code in isolated checkout | Explicit engineering authorization |
| Integrate into R/M/Q tracked code or deploy | Explicit scope including affected target and rollback |
| Open historical outcome or 2026-08+ protected forward payload | Explicit dataset, period, fields and purpose |
| Run new historical economics/confirmatory trial | Exact protocol authorization; PRIMARY budget if applicable |
| Connect private exchange account or place any order | Separate explicit user grant; currently NOT AUTHORIZED |
| Start/stop running collector or scheduler | Separate operational grant; currently NOT AUTHORIZED |

## Prioritization
Prioritize working advisory lifecycle, correct clocks, recoverability, and independent economic evaluation. Avoid recurring meta-review/task chains and repeated T0/T1/F0 paperwork.
