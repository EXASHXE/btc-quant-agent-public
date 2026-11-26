# QUANT v0.8.0 — Owner-Facing Prompt Copy Card Standard (2026-11-18)

## Independent QA ownership — 2026-11-26

**WEB_CONTROLLER_DIRECT_QA — controlling Owner decision (2026-11-26).** All independent QA, cross-family review, source audit, adversarial verification and scoped acceptance are performed directly by the two WEB Controllers, not dispatched as standalone local Agent tasks. For OpenAI-family implementation (Codex Sol/Astra), Gemini 4 Neon WEB is the cross-family reviewer; for Gemini-family implementation (AGY Neon/Hydrogen), ChatGPT GPT-6.2 Sol WEB is the cross-family reviewer. Both may inspect evidence; one accountable 0-C records the disposition. For mixed-family implementation, disclose authorship and actual independent coverage; never claim full cross-family independence without evidence. Use authorized Desktop Commander/GitHub MCP to inspect exact source and independently run targeted offline tests/replays in isolated scratch environments where needed; this is direct Controller verification, not T3 Worker dispatch. Local Workers implement, run their own regression/adversarial tests, produce evidence, and fix findings when separately authorized; their self-tests are WORKER_REPORTED until independently verified. Do not create or reuse a local Independent QA lane, or dispatch review-only/QA-only work to Codex/AGY. If direct access or verification is unavailable, disclose the gap and retain UNKNOWN/HOLD_UNPROVEN as appropriate; do not invent a pass or route QA to a local Agent by default. Existing evidence requirements, separation from authorship, Owner-gated T3 engineering dispatch, REUSE_THREAD_PREFERRED for implementation, and no self-acceptance remain unchanged. This decision supersedes any older local-QA routing guidance; historical evidence and authorship remain immutable.

## Thread continuity and cache-aware routing (Owner-approved, 2026-11-26)

**T3 dispatch routing: REUSE_THREAD_PREFERRED (Owner-approved 2026-11-26).** Before an Owner-confirmed launch/send, discover existing threads and prefer a settled compatible thread for related tasks only after checking provider instance/model/effort, project, pinned Git base/worktree, scope, context quality, permissions, active/pending state and write-set collisions. Use t3_thread_send with mode="queue", freshContext=false for normal continuation; never default to auto/steer/restart or queue unrelated work onto a busy thread. Use a fresh context on the same authorized worktree only when justified; create independent threads for unrelated implementation tasks, incompatible worktrees or stale/conflicting context; perform blind/independent QA directly in a WEB Controller context. Record reuse/new/reset and rationale in the controlled queue. Same model/thread does not guarantee prefix-cache hits or quota savings. Owner confirmation, complete copy-button prompts, non-overlapping write sets and independent acceptance remain mandatory.

See the [controlling T3 protocol](V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md#5-thread-continuity-and-cache-aware-routing-owner-approved-2026-11-26).

## Controlling 2026-11-26 update — RC1 and Owner-confirmed T3
The current accepted local source baseline is v1.0-rc1 at 2a40471; P3 closed NO_CANDIDATE_BEATS_B2_V1 (9/24 trials), P4 not run, final OOS sealed; Stage 3 scoped acceptance recorded locally. Operator upgrade pending, remote code/tag publication and hosted CI unverified, S6 unauthorized. Current product is personal trading intelligence / market structure radar; no validated trading strategy. Current research horizon ~4h–5d; frozen B2 V1 remains unchanged.
Both web ChatGPT GPT-6.2 Sol and Gemini 4 Neon remain coequal combined 1-A + Controller 0-C, mutual audit and planning, one queue, one accountable Controller, no Worker self-acceptance. Both may use T3 MCP to inspect local tasks read-only, and launch/send an exact bounded task to Codex or AGY **only after Owner explicitly confirms T3 dispatch in a prompt identifying that task/prompt and executor**. No automatic dispatch, steering, restart, recurring tasks, permission escalation or live operations. Existing Owner-direct bounded offline forwarding (2026-11-24) remains valid without extra EXECUTE. T3 capability is not authorization; a draft/card/peer report does not grant launch authority. Record actual task/thread/run status, use exact provider options, pinned local base and non-overlapping write sets; no public sensitive identifiers. Keep full English copy-button cards and Chinese Owner communication.
See the canonical current checkpoint and T3 dispatch protocol linked below. **All older status, routing and execution restrictions below are historical where inconsistent with this controlling update; historical evidence and restrictions on real operations remain intact.**

- [Current checkpoint and roadmap](V080_CURRENT_CHECKPOINT_AND_ROADMAP_20261126.md)
- [Owner-confirmed T3 remote dispatch](V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md)

---


**Owner 2026-11-24 role update:** Both web ChatGPT GPT-6.2 Sol and Gemini 4 Neon are coequal combined 1-A/0-C roles. Both generate complete next-task prompts and audit each other; local execution is unchanged. This presentation standard applies equally; a card is not execution or live authority.

- **Status:** ACTIVE
- **Canonical branch:** docs/engineering
- **Applies to:** ChatGPT GPT-6.2 Sol WEB and Gemini 4 Neon WEB (each combined 1-A + Controller 0-C), local agents and all Owner-facing prompt authors
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

## 2026-11-24 — Explicit visible copy-button requirement

Every prompt delivered to the Owner for forwarding, including short peer-controller supplements, review handoffs, new-chat bootstraps, engineering tasks, QA instructions and revisions, MUST be presented in its own card with a clearly visible, functional **复制完整 Prompt / Copy Full Prompt** button bound to the complete exact prompt. On ChatGPT surfaces that support a dedicated clipboard action, use that action explicitly; do not default to a plain WritingBlock, ordinary Markdown or a fenced block merely for convenience. Keep explanatory Chinese text outside the English copy payload. Only if a dedicated clipboard action is genuinely unavailable, use a complete native-copy block and identify the fallback honestly. Never fake a button, truncate the payload or substitute a link. This is a hard delivery requirement regardless of prompt length; it does not authorize task execution or live access.
