# Multi-Model Research Governance

Purpose: reduce single-model anchoring, implementation bias, and research-direction drift while preserving deterministic ownership and clear Git lineage.

## Roles

### ChatGPT
- quant/research architect
- acceptance reviewer
- research-methodology and safety gate owner
- consolidates final stage recommendation after independent reviews

### Gemini-3.8-Flash
- independent research challenger and co-reviewer
- reviews hypotheses/protocols before freeze
- performs blind post-implementation review of exact commit SHA
- seeks counterexamples, leakage, multiple-testing, data-provenance, execution and operational defects

### Implementation agent
May be Gemini, Codex, or another coding agent. Responsibilities:
- code/tests/data tooling/backtests/collectors/systemd
- run preregistered research exactly
- commit/push all code and deliverables
- never self-approve promotion

## Stage workflow

### A. Pre-freeze dual critique
1. Draft a proposed research/engineering objective.
2. ChatGPT critiques independently.
3. Gemini-3.8-Flash critiques independently.
4. Reconcile only after both initial critiques exist.
5. Freeze protocol/prompt/acceptance criteria in Git before result inspection.

No model may modify the frozen hypothesis merely because early results look weak.

### B. Single-writer implementation
Only one implementation agent edits the active implementation branch at a time. Reviewers remain read-only until the implementation agent reports a commit SHA.

### C. Blind dual review
For the exact same implementation SHA:
- Gemini-3.8-Flash writes an independent review before reading ChatGPT's verdict.
- ChatGPT independently reviews before reading Gemini's verdict where practical.

Both reviews must verify the repository, not merely the implementer's summary.

### D. Reconciliation
Create a disagreement matrix with:
- issue
- ChatGPT view
- Gemini view
- evidence/commit/file
- severity
- resolution

Severity classes:
- BLOCKER: research integrity, look-ahead, Holdout breach, live/execution safety, evidence tampering, invalid preregistration, material correctness bug
- HIGH: changes result validity or Forward eligibility
- MEDIUM: engineering reliability/coverage/documentation that does not change primary inference yet
- LOW: style/maintainability/non-material documentation

Any unresolved BLOCKER/HIGH issue blocks promotion.

## Required reviewer checks

### Lineage / Git
- exact branch and SHA
- correct parent/base
- protocol commit precedes formal result commit
- no hidden result-driven commits before preregistration
- CI associated with exact reviewed SHA

### Quant / statistics
- causal features only
- chronological splits / purge / embargo where required
- no random-mask OOS claims
- multiple-testing universe complete
- no best-backtest-wins selection
- adequate sample size and direction balance
- fold/year/regime stability
- cost/funding/slippage treatment
- bootstrap/block units correct
- candidate gate implementation matches preregistered gate

### Data provenance
- archive/vendor/forward roles correct
- checksums/manifests verified
- no gap fill presented as real events
- no receive-time fiction
- true Forward gaps remain gaps
- no synthetic L2/OFI from OHLCV

### Runtime / execution
- deterministic decision path
- Agent cannot override deterministic QuantCore
- no future price embedded in decision object
- actual execution entry semantics correct in replay
- execution remains disabled unless separately authorized
- no credentials/order path accidentally enabled

### Forward evidence
- campaign IDs/start boundaries immutable
- elapsed wall-clock denominator correct
- missed slots count honestly
- data-quality terminal gates enforced
- successor preregistered only on future fixed boundary
- no stitching/restarting terminal campaign under same ID

### Engineering
- ruff/mypy/pytest/coverage/compileall
- Python matrix CI
- direct tests for new critical code
- systemd/restart behavior where relevant
- network/storage/resource contention
- observability and fail-closed behavior

## Promotion decisions

Allowed consolidated decisions:
- PASS
- PASS_WITH_NONBLOCKING_FOLLOWUPS
- REPAIR_REQUIRED
- RESEARCH_FAMILY_STOP
- FORWARD_DATA_INSUFFICIENT
- REJECT_CANDIDATE

A candidate/strategy cannot be promoted because one model is optimistic. Promotion requires both independent reviews to have no unresolved BLOCKER/HIGH findings and the frozen quantitative gates to pass.

## Artifact convention

For stage `vX.Y.Z`:

```text
reviews/vX.Y.Z/chatgpt/REVIEW.md
reviews/vX.Y.Z/gemini-3.8-flash/REVIEW.md
reviews/vX.Y.Z/RECONCILIATION.md
```

Where possible also create machine-readable JSON with verdict, findings, severity and reviewed SHA.

Review artifacts are evidence only; they may not rewrite formal research outputs.
