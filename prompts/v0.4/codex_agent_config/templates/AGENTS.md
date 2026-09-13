# AGENTS.md

## Goal

Complete each task with the smallest sufficient context, the smallest correct patch, and validation proportional to the change.

Token and quota efficiency are important, but never reduce correctness, acceptance coverage, required validation, PIT/causal correctness, trading/economic correctness, or explicitly requested scope merely to save tokens.

## Task authority

When the user supplies an exact task or prompt path, read that file first and treat it as the primary task specification.

Do not recursively inspect historical prompts, reviews, deliverables, artifacts, reports, or changelogs unless the current task requires them.

Prefer current code, current tests, and the exact task specification over historical material.

Do not redesign architecture or expand scope unless the task requires it.

## Context discipline

Use targeted discovery before broad reading.

Preferred sequence:

1. Read the exact task specification.
2. Locate relevant symbols/files with targeted search.
3. Read the directly affected implementation.
4. Read directly related tests.
5. Expand to dependencies only when evidence requires it.

Do not read the whole repository merely to understand the project.

Do not reopen unchanged files unless new evidence makes it necessary.

Treat these as opt-in context unless directly required:

- `artifacts/`
- historical `deliverables/`
- historical `prompts/`
- large research reports
- generated outputs
- large registries
- datasets
- large logs

For large files, inspect selected keys, symbols, matches, or bounded ranges rather than printing the entire file.

Prefer `rg`, bounded `git diff`, selected `jq` fields, `head`, `tail`, and targeted test output over recursive or complete dumps.

Use the principle: signal first, evidence expansion second.

## Tool efficiency

Batch independent, already-known, read-only checks when practical.

Avoid unnecessary model round trips between searches or inspections that were known in advance to be required.

Keep dependent, adaptive, state-changing, write, approval-sensitive, and failure-dependent operations serial.

Do not poll CI or long-running commands aggressively.

Do not repeat a completed check unless code/state changed or a failure creates a reason to repeat it.

Bound commands that may produce large output before their output enters model context.

## Task complexity routing

Classify work by reasoning complexity and correctness risk, not by file count or patch size.

Large does not necessarily mean difficult.

### M0 — mechanical

Examples:
- deterministic rename
- formatting
- repetitive field replacement
- simple config/text synchronization
- straightforward fixture synchronization
- obvious lint fixes
- repetitive edits following an established pattern

Preferred worker:
- `mechanical`
- target model: GPT-5.6 Luna
- target reasoning: low

Do not use high reasoning for clearly mechanical work.

### M1 — lightweight engineering

Examples:
- targeted repository exploration
- locating call sites
- dependency lookup
- bounded log inspection
- straightforward isolated fixes
- simple direct tests
- evidence gathering

Preferred worker:
- `explorer`
- target model: GPT-5.6 Terra
- target reasoning: low

### M2 — normal implementation

Examples:
- ordinary feature implementation
- multi-file implementation with a clear specification
- normal bug fixes
- acceptance repairs
- control-flow changes with established semantics

Preferred execution:
- parent GPT-5.6 Sol
- medium reasoning

If the current parent is stronger than this, do not automatically replace the parent. Delegate clearly independent M0/M1 work where useful.

### M3 — correctness-critical engineering

Examples:
- cross-module invariants
- subtle state transitions
- difficult debugging
- PIT correctness
- causal-time semantics
- execution semantics
- fee/funding/cash-flow semantics
- difficult CI root causes
- public contract changes

Preferred execution:
- GPT-5.6 Sol
- high reasoning

Use `reviewer` for independent consequential review when useful.

### M4 — deep reasoning

Examples:
- architecture-level reasoning
- statistical validity
- research methodology
- alpha validity
- system-wide ambiguous redesign
- extremely difficult cross-module correctness
- problems that remain unresolved after competent Sol High work

Preferred execution:
- GPT-6 Astra or the strongest available model

## Parent-model rule

The model selected for the current root session remains the parent model.

Do not assume this file can dynamically turn an Astra parent into Sol, Terra, or Luna.

Model tiering applies primarily through configured subagents or by starting a separate task/session with a cheaper model.

If the parent is Astra or Sol High, it does not need to personally execute every low-complexity operation.

## Delegation policy

Do not spawn a subagent merely because it is cheaper.

Delegation has its own context and coordination cost.

Delegate when the work is:
- clearly scoped
- substantially independent
- safe to isolate
- suitable for a cheaper model
- large enough that delegation overhead is justified

For mixed tasks, prefer:
- `mechanical` for repetitive deterministic edits
- `explorer` for targeted read-heavy investigation
- `reviewer` for consequential independent correctness review
- parent agent for core semantics and integration decisions

Do not delegate a one-line trivial edit just to use a cheaper model.

Do not create chains of subagents unless the task genuinely benefits from them.

Prefer shallow orchestration.

## Escalation

A lower-cost worker must return control rather than guess when it encounters:
- ambiguous requirements
- unexpected cross-module impact
- tests contradicting expected behavior
- public contract changes
- PIT or causal leakage risk
- trading/economic semantic changes
- significant architecture decisions
- repeated failed fixes
- insufficient evidence to determine intended behavior

Escalate based on reasoning complexity and correctness risk, not task size.

Conceptual escalation path:

Luna → Terra → Sol Medium → Sol High → Astra.

## Editing policy

Make the smallest patch that completely satisfies the task.

Preserve unrelated user changes.

Avoid:
- opportunistic refactoring
- unrelated cleanup
- speculative abstractions
- unnecessary compatibility layers
- documentation rewrites not required by the task
- extra session-memory files
- extra design reports
- broad renaming outside task scope

Prefer existing project patterns over inventing new abstractions.

## Validation

Use progressive validation.

Typical flow:
1. Make the scoped change.
2. Run the narrowest relevant test/check.
3. Fix failures.
4. Rerun affected checks.
5. When implementation stabilizes, run the required final local gate.
6. Use GitHub CI for the final supported-version matrix.

Do not rerun the complete suite after every small edit.

For this repository, unless the task specifies otherwise, the final local quality gate is:

`ruff check . && mypy && pytest -q`

Run local coverage only when the task explicitly requires it, coverage behavior changed, or coverage itself is under investigation.

If project configuration changes these commands, follow the current repository configuration.

## CI

After push, resolve the exact HEAD SHA and track CI for that commit.

On failure:
1. identify the failed job
2. identify the failed step
3. inspect concise relevant failure output
4. expand logs only when necessary

Do not ingest complete logs from successful jobs.

After a repair, rerun validation proportional to the repair.

When required CI is green, stop. Do not add redundant verification cycles.

## Communication

Keep progress communication concise.

Report:
- material discoveries
- blockers
- changed assumptions
- meaningful validation results
- final result

Do not narrate every routine file read, search, or command.

Final responses should emphasize:
- what changed
- validation performed
- CI status when relevant
- commit SHA when relevant
- unresolved issues, if any
