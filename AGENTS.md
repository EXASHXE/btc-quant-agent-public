# Quant docs/engineering — Active Documentation Agent Overlay
This independent docs-only branch is the **sole canonical documentation source** for v0.7.0 product mission, roles, architecture/roadmap, task cards, handoff, and new-chat startup prompts.

Read [Documentation Branch Policy](docs/project/V070_DOCUMENTATION_BRANCH_POLICY.md) before changing documents.

## Mandatory routing
- ALL future documentation writes and reads target GitHub `docs/engineering` with verified HEAD.
- Do NOT use `v0.7.0`, `v0.6.5` or R-local Markdown as an alternate writable or authoritative doc source. Those may contain legacy copies.
- Actual code and service state belong to R=/root/workspace/project/quant-0.7.0/research-loop-bootstrap, M=/root/workspace/project/Quant-agent-market-watch, Q=/root/workspace/project/Quant-agent. Verify them separately; docs changes do not deploy.
- The branch is documentation only: no runtime code, tests, protected market data, account credentials, registry changes or service operations.

## Active entrypoints
- [Mission](docs/project/V070_ADVISORY_MISSION_AND_SCOPE.md)
- [Roles](docs/roles/V070_ADVISORY_AGENT_ROLES.md)
- [ChatGPT independent advisor](docs/roles/V070_CHATGPT_STRATEGIC_ADVISOR.md)
- [Roadmap](docs/project/V070_ADVISORY_ROADMAP.md)
- [Handoff](docs/project/V070_CURRENT_STATE_AND_HANDOFF.md)
- [Foundation task](docs/project/V070_ADVISORY_FOUNDATION_TASK.md)
- [ChatGPT new chat](docs/project/V070_CHATGPT_NEW_CHAT_START.md)
- [Controller new chat](prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C.md)

## Prompt presentation
When user requests Controller/Codex/Astra/Opus/Gemini/new-chat prompt, provide a working **Copy Full Prompt** button copying every character when the host chat UI supports it. Never a fake copy button or excerpt-only copy. Otherwise put full prompt into one complete fenced block.

## Product role
Read-only crypto opportunity & position management advisory, actionable structure-driven entry/stop/target or open-ended trailing, user-confirmed positions, timely deterministic risk events. Do not assert 2R/time-based exits are mandatory or claim verified Alpha without evidence.
Owner decides permissions. Controller 0-C coordinates Codex engineering; ChatGPT independent advisor critically reviews rather than runs parallel dispatch.
