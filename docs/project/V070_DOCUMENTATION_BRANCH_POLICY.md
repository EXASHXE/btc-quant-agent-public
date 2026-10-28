# v0.7.0 Canonical Documentation Branch Policy
Owner decision: 2026-10-28. Active canonical remote documentation branch: **docs/engineering**.

## Sole source of documentation
- ALL future changes to project direction, roadmap, architecture notes, role instructions, engineering task cards, research/Controller handoffs and new-conversation prompts MUST be published, updated and read from GitHub `docs/engineering`.
- The `v0.7.0` branch and R/M/Q worktrees are for code, tests, operational evidence and frozen studies, NOT the canonical future advisory documentation. Previous matching Markdown on `v0.7.0` is historical; do not treat it as the latest instructions.
- Do not maintain a second writable documentation authority on `v0.7.0`. Do not force-merge the docs-only branch into code or change the repository default branch.
- If local documentation differs, trust the verified current GitHub docs/engineering HEAD for product/role/task documentation; independently read actual code and state from the relevant R/M/Q worktree. If the canonical branch cannot be reached, report that limitation; do not silently substitute old files.
- When updating docs, create one bounded docs-only commit on docs/engineering; validate links and confirm no source, confidential data, registry, tests or deployment files were changed. Report the exact commit SHA and docs branch links.
- Legacy v0.6.5 and prior v0.7.0 research reports on this branch remain historical evidence; use the dated advisory roadmap below for NEW execution priorities.

## Active documents and handoff
- [Mission](V070_ADVISORY_MISSION_AND_SCOPE.md)
- [Role matrix](../roles/V070_ADVISORY_AGENT_ROLES.md)
- [Independent ChatGPT role](../roles/V070_CHATGPT_STRATEGIC_ADVISOR.md)
- [Roadmap](V070_ADVISORY_ROADMAP.md)
- [Current state](V070_CURRENT_STATE_AND_HANDOFF.md)
- [Foundation task](V070_ADVISORY_FOUNDATION_TASK.md)
- [ChatGPT strategic advisor startup](V070_CHATGPT_NEW_CHAT_START.md)
- [Controller 0-C startup](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C.md)

## Mandatory prompt copy UX
For any full Controller, Codex, Astra, Opus, Gemini or new-chat prompt, when the chat UI supports interactive clipboard actions, provide a **working, visibly labeled Copy Full Prompt button** copying the **complete untruncated exact prompt**. A truncated preview is fine only if copy still gets the full text. No inert/decorative button.
If the UI lacks a real copy action, provide the entire prompt in ONE fenced code block or another complete easy-to-copy fallback; explain the limitation. A repository Markdown file cannot itself render a functional chat button.

## Boundaries
Documentation is not authorization for code integration, restricted historical or forward data access, PRIMARY registration, testnet/live trading, private accounts, or service changes. Preserve the scientific and authority constraints of original evidence.
