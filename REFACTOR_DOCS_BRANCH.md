# Refactor docs branch policy

This branch is the dedicated input/output document branch for the v0.5 refactor line.

- Implementation branch: `v0.5-refactor`
- Document branch: `v0.5-refactor-docs`
- Branch point: C-lite accepted candidate `31521b620292064997384261e90cd09a2e806f98`
- Immutable repaired-kernel semantic baseline: `6710b6302bf224cdc178e6f3d817a95f79277f38`

## What belongs here

- future implementation/review prompts under `prompts/v0.5/`
- independent review/audit reports under `reviews/v0.5/`
- architecture plans and refactor decision records that are inputs/outputs of agent work

## What does not belong here

Do not use this branch for production source, tests, configs, frozen protocols, research evidence, runtime data, or implementation commits. Those changes belong on `v0.5-refactor` (or a child implementation branch) and should reference the relevant prompt/review commit from this branch.

The active refactor branch intentionally omits the historical `prompts/` and `reviews/` trees to reduce irrelevant context during implementation. Historical documents remain available through Git history and this docs branch.
