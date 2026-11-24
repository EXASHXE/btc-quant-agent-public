# QUANT v0.8.0 — Owner-Facing Prompt Copy Card Standard (2026-11-18)

**Owner 2026-11-24 role update:** Both web ChatGPT GPT-6 Sol and Gemini 4 Neon are coequal combined 1-A/0-C roles. Both generate complete next-task prompts and audit each other; local execution is unchanged. This presentation standard applies equally; a card is not execution or live authority.

- **Status:** ACTIVE
- **Canonical branch:** docs/engineering
- **Applies to:** ChatGPT GPT-6 Sol WEB and Gemini 4 Neon WEB (each combined 1-A + Controller 0-C), local agents and all Owner-facing prompt authors
- **Authority:** Owner instruction; presentation rule only.

This standard governs how complete prompts are presented to the Owner. It does not grant dispatch authority, implementation permission, API access, credential access, acceptance authority or trading permission.

## 1. Mandatory card format

Whenever 1-A, 0-C or another Owner-facing role generates or revises a complete:

- new-chat bootstrap prompt;
- engineering task prompt;
- Gemini/Sol/Astra/other-agent assignment;
- architecture-review prompt;
- independent-audit prompt;
- research/execution prompt;

render one compact prompt card per distinct complete prompt.

Each card must show:

- Task / prompt name or ID;
- Intended executor or recipient;
- Truthful state, such as DRAFT, READY_FOR_0C_REVIEW, READY — NOT DISPATCHED or DISPATCHED;
- One short purpose statement;
- A clearly labeled “复制完整 Prompt / Copy Full Prompt” action.

The card preview never replaces the complete prompt.

## 2. Copy payload integrity

The copy action must contain the entire exact current prompt, including role/task identity, paths, repository references, constraints, prohibitions, commands where applicable, acceptance criteria, deliverables, stop conditions and truthful current status.

Never bind the copy action only to a title, summary, URL or truncated preview.

For multiple prompts, every card must have its own correctly bound full-prompt payload.

## 3. UI capability and fallback

When the current ChatGPT surface supports a real clipboard action, wire the visible copy control to the complete prompt text.

If a dedicated custom clipboard action is not available, do not fabricate one. Instead:

1. Present the prompt as one complete copyable WritingBlock or CodeBlock.
2. Clearly label the fallback “复制完整 Prompt / Copy Full Prompt”.
3. Keep the surrounding card concise; the full prompt may remain inside the copyable block.

A repository Markdown file describes the required UI behavior; it cannot itself create a functional ChatGPT clipboard button.

Never claim that copying succeeded before the host handles the user's action.

## 4. Truthful task state

Prompt presentation must never imply:

- A worker has been dispatched when it has not;
- A test has passed when it has not;
- Controller acceptance when only worker completion exists;
- Live API activity when only offline/mock work exists;
- Credentials or permissions have been granted;
- An external message has been sent.

A task prompt is not a dispatch. Either coequal web model acting as Controller 0-C may formally dispatch and record scoped acceptance for a named task; keep one accountable Controller and avoid duplicates.

## 5. New-chat prompts

For a new-chat bootstrap prompt:

- Include the complete startup prompt in the copy payload;
- Do not provide only a GitHub URL;
- Provide the canonical docs/engineering URL when available;
- Preserve the exact current prompt version;
- Mark the chat's state truthfully.

## 6. Prompt revisions

When an existing prompt is revised, regenerate the complete current prompt in the copy payload. Do not provide a delta-only patch as the operational prompt.

The canonical Markdown prompt and the Owner-facing copy payload must represent the same version.

## 7. Role inheritance

### ChatGPT 1-A

Must use this standard whenever preparing a prompt for Sol, Sol Max, Gemini Neon, Astra, Hydrogen, Controller 0-C or a new QUANT chat. Both combined web 1-A/0-C role holders may advise, draft complete task prompts, and separately act as accountable 0-C under established task-start authority.

### Controller 0-C

Must use this standard for Owner-facing task cards and forwarded worker prompts. Either web 0-C may be accountable for a named dispatch and scoped disposition after required independent review.

### Worker models

Sol, Sol Max, Gemini Neon, Hydrogen and Astra are recipients/executors unless separately instructed otherwise. Their terminal output does not create a ChatGPT copy-card UI action.

## 8. Branch authority

This standard is maintained on docs/engineering. Do not update its canonical copy on v0.8.0. Project documentation changes belong on docs/engineering; executable source and runtime evidence belong on v0.8.0.

## 9. Minimum card template

- **Task:** <ID / name>
- **Executor:** <model / role>
- **Status:** <truthful state>
- **Purpose:** <1–3 sentences>
- **Action:** **复制完整 Prompt / Copy Full Prompt**

A link to the canonical prompt may accompany the card, but never substitutes for the complete copy payload.

## 2026-11-21 — Explicit handoff authority wording for engineering cards

Follow the [Owner Direct Offline Task Execution Protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md). Label every new future task with exactly one start mode: CONTROLLER_DISPATCHED (actual receipt exists), OWNER_DIRECT_OFFLINE_ALLOWED (Owner may execute by forwarding the complete card), or PROPOSAL_ONLY (not executable until later Owner direction/Controller dispatch). Do not generate a card that tells a worker to execute immediately while also demanding an unavailable second Controller receipt for safe offline work.

A complete prompt/card stored in docs is not itself dispatch. Explicit Owner forwarding in the actual worker chat with an instruction to execute a named bounded OFFLINE task is a sufficient Owner-direct offline start. Worker records OWNER_DIRECT_OFFLINE_STARTED, no fabricated Controller receipt and no self-acceptance. Real Binance/Feishu/provider/private/TRADE/production permissions are NEVER inferred.

## 2026-11-23 Owner requirement — copy-button/card display is a hard acceptance rule

This is **mandatory for every occasion** when a full Prompt is given to the Owner, including new Controller chats, 1-A chats, Sol/Neon/Hydrogen/Astra tasks, research reviews, rewrites and corrected versions; it is not limited to prompts initially generated on 2026-11-18.

- Provide **one complete copyable card per distinct Prompt**. Put the current **entire** prompt, not an excerpt, within its own copy payload.
- Provide a visible, functional **复制完整 Prompt / Copy Full Prompt** button/action whenever the chat surface supports a real clipboard control. If the platform does not expose a custom button, use a **complete WritingBlock or CodeBlock with its native Copy feature**. The copyable block itself is the card; do not add a decorative fake "复制" button.
- Link the canonical Markdown file for provenance **in addition** to, never instead of, the full copyable content. A Markdown repository file cannot guarantee a UI control in other clients; the presenting assistant must use the current client's real capability.
- Include recipient, state/start authority, exact task ID, current source baseline and constraints, required QA, deliverables, prohibitions and stop conditions. Multiple versions: latest complete text, no delta-only prompt.
- This UI standard **does not** turn a prompt into a Controller dispatch or authorize live provider access. Accurate `PROPOSAL_ONLY / OWNER_DIRECT_OFFLINE_ALLOWED / CONTROLLER_DISPATCHED` markings remain required.

Reviewers should reject an Owner-facing "prompt delivered" claim when only a path, tiny sample, incomplete preview or nonworking imitation button was provided.

## Mandatory language and usable Copy behavior (controlling 2026-11-23 correction)

**One language split across all roles:** Chinese for Owner-facing narrative, status and explanations; **English for the entire prompt body sent to any other agent/model**, including new 1-A and 0-C chats, Sol/Neon/Hydrogen/Astra work, audit/research task cards and Agent harness instructions. This is the default unless the Owner explicitly requests another prompt language. The historic canonical 0-C bootstrap already stated "Respond to Owner in Chinese; worker task cards are in English"; new-chat prompts are themselves agent-facing and follow the **same English default**. Translate explanations outside the copyable English prompt, never replace the payload with Chinese.

**A functional copy control is a requirement, not a caption:** In ChatGPT, create a compact prompt card with one genuine Copy Full Prompt/复制完整 Prompt button wired to the complete byte-for-byte text where the UI supports a clipboard action (e.g. `GenUI.copy(fullPromptText)`). A complete WritingBlock or CodeBlock with native Copy is the supported fallback. Do not output an inert control in plain Markdown. AGY/terminal cannot be presumed to support ChatGPT clipboard actions: use the complete fenced English prompt with native copy, or a verified interactive MCP App copy component (`ui://`) if supported by that client. Merely writing "Copy" beside a text link does not satisfy this requirement.

**Self-check before delivering a prompt:** (1) exact executor, ID, start status and authority; (2) prompt language English; (3) full nontruncated text, not URL/summary/delta; (4) genuine clickable copy mechanism or honestly described complete fallback; (5) canonical path and chat payload match; (6) no implied live signature/approval; (7) multiple prompts each have independent payload. A prompt failing any item is **NOT_READY_FOR_OWNER_COPY** and must be corrected in the same response.
