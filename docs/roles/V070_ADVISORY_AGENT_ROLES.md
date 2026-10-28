# v0.7.0 Roles, Decision Rights and Task Routing
Status: active product-planning guidance, 2026-10-28. Supersedes previous role routing for NEW advisory engineering only; legacy experiment authority remains intact.

## Owner — product principal and approval authority
- Defines product goals, acceptable notification/operational trade-offs and risk limits.
- Explicitly approves scope for code integration, runtime deployment, data access, historical trial execution, protected holdouts, and ANY account/trading operation.
- Maintains final judgment on trading; no agent has discretionary order authority.

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

## Codex — primary implementation and verification
- Implements narrow authorized change in isolated checkout/worktree, with synthetic tests and concise diff/receipt.
- First priority: advisory foundation (scan degradation, received/decision clocks, quote vs candle, freshness gates, tick sizes, persist-before-notify).
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
