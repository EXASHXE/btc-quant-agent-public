# Quant Agent — Active v0.7.0 Project Overlay (2026-10-28)

This file guides agents operating in this worktree. It is not an authorization to execute any task. Explicit Owner scope and the exact requested task control actions and data access.

## Active mission and document order
1. [Advisory Mission](docs/project/V070_ADVISORY_MISSION_AND_SCOPE.md)
2. [Roles and authority](docs/roles/V070_ADVISORY_AGENT_ROLES.md)
3. [Delivery roadmap](docs/project/V070_ADVISORY_ROADMAP.md)
4. [Verified handoff](docs/project/V070_CURRENT_STATE_AND_HANDOFF.md)
5. [Next bounded task](docs/project/V070_ADVISORY_FOUNDATION_TASK.md)
6. [ChatGPT independent advisor role](docs/roles/V070_CHATGPT_STRATEGIC_ADVISOR.md)
7. [New ChatGPT conversation](docs/project/V070_CHATGPT_NEW_CHAT_START.md)

These are the current product-planning references. Historical v0.6/v0.6.5 research, frozen experiment protocols, immutable registry and research decisions remain authoritative for their own evidence; do not retroactively change them. A new roadmap does not authorize a new trial, a data read, a repository mutation or a deployment.

## Working trees and preservation
- Research worktree R: /root/workspace/project/quant-0.7.0/research-loop-bootstrap.
- Operating collector Q: /root/workspace/project/Quant-agent.
- Product feature tree M: /root/workspace/project/Quant-agent-market-watch.
- Do not assume these trees are synchronized. Identify source revisions and inspect all dirty changes before selecting an integration base.
- Preserve the original 12 added paths in R, the pending M edits, live Q services and all PRIMARY registry events. Do not reset, clean, stash, force checkout, overwrite or merge owner work.
- Prefer an isolated worktree for code changes and a small reviewable patch. Do not commit, push or deploy unless explicitly authorized.

## Product invariants
- Product is a read-only advisory system: market scanning, evidence-backed candidate plans, user-confirmed positions, deterministic risk/management guidance, and reliable notifications. No autonomous orders.
- Candidate, suggested entry, actual user report, simulated fill, account-confirmed fill, and CLOSED are separate states.
- Structure-derived stop/target, volatility projection and open-ended trailing are different explicitly typed policies. Do not manufacture a 2R target or invent support/resistance.
- Initial stop/risk limits never silently loosen; risk-critical notifications do not wait for LLM review.
- Timestamp correctness: source event, receive, available, decision, commit, notification and fill clocks must be distinguished. No lookahead.
- Persist before notifying. False notification-success flags, silent backfill and fabricated fills are prohibited.
- Refuse action on stale/insufficient data. A numeric rule ranking is not calibrated probability or Alpha.
- All modeled costs, slippage, funding and terminal-state accounting remain explicit; missing full-net evidence is not zero.

## Research and execution boundaries
- Historical fixed-horizon results remain valid for their exact protocols, including failures and NULLs. Dynamic lifecycle research is a new exploratory hypothesis, not a rescue.
- 2021–2023 may be explored ONLY under explicitly authorized scope with exposure logging. Sealed 2024+ and the 2026-02-01–2026-08-01 FINAL_HOLDOUT remain protected.
- PRIMARY 3/6 used, 3 unassigned as last verified; inspect current registry before any planning. Do not create PRIMARY-04 implicitly.
- Forward market payload, broker accounts, tests needing real-network exchange calls, service restarts, live writes, historical outcome computations and paper/testnet/live orders each require separately granted scope.
- Pure documentation maintenance does not imply code deployment; synthetic test success does not imply source or production readiness.

## Efficient agent workflow
Controller 0-C translates Owner direction into ONE bounded task and accepts a demonstrated patch; Codex implements scoped code and tests. Astra, Opus or Gemini are optional for genuinely novel economic, causal or architectural questions, not mandatory for every engineering change.
Prefer working product evidence over governance expansion. Report actual files changed, tests run, exclusions and blockers; never claim tests, forward evidence or profitability not independently verified.
