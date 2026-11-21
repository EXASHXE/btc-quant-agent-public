# QUANT v0.8.0 — Owner-Facing Prompt Copy Card Standard (2026-11-18)

- **Status:** ACTIVE
- **Canonical branch:** docs/engineering
- **Applies to:** ChatGPT 1-A, Controller 0-C and all Owner-facing prompt authors
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

A task prompt is not a dispatch. Only Controller 0-C can formally dispatch and accept engineering work.

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

Must use this standard whenever preparing a prompt for Sol, Sol Max, Gemini Neon, Astra, Hydrogen, Controller 0-C or a new QUANT chat. 1-A may advise and draft but does not dispatch.

### Controller 0-C

Must use this standard for Owner-facing task cards and forwarded worker prompts. 0-C remains the sole dispatcher and scoped acceptance authority.

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
