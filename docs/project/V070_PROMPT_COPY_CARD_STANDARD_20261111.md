# Quant v0.7.0 — Project-Wide Prompt Copy Card Standard (2026-11-11)

**Status:** ACTIVE for all Owner-facing ChatGPT roles and task planners. **Authority:** Owner's explicit request for every generated prompt to have a functional copy-button card. [MVP Home](V070_MVP_CLOSURE_HOME_20261111.md) · [Role Matrix](../roles/V070_ACTIVE_ROLE_MATRIX_20261111.md).

This v0.7.0 rule updates/supersedes older conflicting 0.6.5 presentation and fallback language. It is a **presentation rule only**, not an authorization to execute tasks, use private data, trade or send external messages.

## Mandatory behavior for every role

This applies to **1-A Strategic Advisor, 0-C Controller, any future ChatGPT role, Codex/Claude/Gemini/Astra/Opus worker task author**, and agents generating Owner-facing prompts for other agents. The role creating the prompt is responsible for how it is presented to the Owner.

Whenever generating, revising, or proposing a **new-chat bootstrap prompt, Codex/Gemini/other-agent assignment, independent audit prompt, engineering/research task card or multi-part execution prompt**:

1. Render **one compact card per distinct complete prompt** with a clear task name/ID, intended executor, state (e.g. READY / DRAFT / NOT DISPATCHED / RUNNING), short purpose, and a visibly labeled **“复制完整 Prompt / Copy Full Prompt”** control.
2. In ChatGPT interfaces supporting UI actions, wire a real **clipboard-copy action** (e.g. `GenUI.copy(fullPromptText)`) to the control. Store the **full exact untruncated prompt** as the copy payload, including constraints, commands, paths and acceptance criteria. Never copy only the heading, card preview, summary, partial text, or URL.
3. Keep cards concise: show a 1–3 sentence description and link to the canonical GitHub prompt when it exists. The complete prompt **need not be rendered visibly** as an enormous code fence; the button payload must still contain it in full.
4. The button cannot be decorative or inert. Never say “copied” before the host handles the click. If the interface genuinely lacks an interactive clipboard control (e.g. plain Markdown, terminal or text-only agent), **state the limitation and give the full prompt in one copyable fenced block** or a native one-click-copy writing/code block; do not fabricate an interactive control. Do not ask for an extra Owner confirmation merely to supply a copyable fallback.
5. Multiple prompts must have **separate correctly bound controls**, not one button copying the first prompt for every card. Do not silently omit prompts merely to meet an arbitrary two-card display limit; group or present a concise index when many are requested.
6. **Task status must be truthful**: a card or linked prompt never implies a worker was dispatched, a test passed, a source was qualified, a grant exists or an external message was delivered.
7. For **new chat prompts**, always include the full startup prompt (not only a GitHub URL) in the copy action and provide the canonical published URL. For edits of existing prompts, regenerate the complete current version in the payload.

## Recommended card content

- **Title:** `V070-MVP-M1 | 3-symbol offline E2E`
- **Executor:** `Codex GPT Sol`
- **Status:** `READY — NOT DISPATCHED`
- **Purpose:** source mock → canonical engine → one Outbox → mock Feishu → Shadow/HTML.
- **Controls:** `复制完整 Prompt` (real action copying all text) and a plain link to its canonical GitHub source when published.

**Priority:** prompt integrity and functional copying are mandatory; visual decorations are optional. Repository Markdown instructs the ChatGPT role; Codex/Gemini outputs in a terminal cannot themselves produce ChatGPT UI widgets.

## Project-wide inheritance

- `AGENTS.md`, `README.md`, 0-C/1-A role docs and both 2026-11-11 new-chat prompts reference this standard.
- Historical copies and older prompts remain navigable, but this active rule is controlling for new Owner-facing outputs.
- Detailed engineering artifacts (SHA256 manifests, logs) stay in files, not the card body unless specifically requested.
