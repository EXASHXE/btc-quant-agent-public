# Multi-Model Research Governance

Purpose: keep a second-model audit for independent challenge without turning every stage into a two-round review ceremony. The default workflow is now: ChatGPT defines the stage, one implementation agent executes it, Gemini performs one independent audit, and ChatGPT makes the final review and writes the next-stage prompt.

## Roles

### ChatGPT
- quant/research architect and stage owner
- defines the next-stage objective, frozen constraints and acceptance criteria
- performs the final review after implementation and Gemini audit
- verifies material Gemini findings directly against repository evidence when needed
- owns the final stage decision and the next-stage/repair prompt
- preserves research-methodology, causality, provenance and execution-safety gates

ChatGPT does not need to create a second independent review artifact by default. Its final review may be delivered in the project conversation and incorporated into the next-stage prompt. A separate `FINAL_REVIEW.md` is optional when useful for formal evidence.

### Gemini-3.8-Flash
- one-pass independent auditor/challenger after implementation
- reviews the exact supplied branch/SHA, not the implementer's summary
- seeks counterexamples, leakage, multiple-testing, data-provenance, execution, Forward-evidence and operational defects
- writes one audit artifact for the stage
- remains read-only with respect to implementation during the audit
- does not perform a second reconciliation round and does not own the final next-stage prompt

### Implementation agent
May be Gemini, Codex, or another coding agent. Responsibilities:
- code/tests/data tooling/backtests/collectors/systemd
- execute the frozen stage prompt/protocol exactly
- commit/push code and deliverables
- report an exact reviewable SHA
- never self-approve promotion

## Default stage workflow

### A. Stage definition and freeze
1. ChatGPT reviews the latest accepted repository state and prior evidence.
2. ChatGPT defines the next research/engineering objective, constraints, stop rules and acceptance criteria.
3. The stage prompt/protocol is committed to Git before outcome-driven implementation or result inspection where preregistration is required.

No model may relax a frozen hypothesis, gate, split, budget or Forward boundary merely because early results look weak.

### B. Single-writer implementation
Only one implementation agent edits the active implementation branch at a time.

The implementation agent:
- implements the frozen prompt/protocol;
- runs required tests/CI/research jobs;
- commits formal deliverables;
- reports the exact branch and SHA to review.

### C. Single Gemini audit
Gemini-3.8-Flash performs exactly one independent post-implementation audit of the review target.

Gemini must:
- inspect the exact branch/SHA;
- verify repository evidence directly;
- not edit implementation code during the audit;
- write its audit to:

```text
reviews/vX.Y.Z/gemini-3.8-flash/REVIEW.md
```

A machine-readable companion is optional:

```text
reviews/vX.Y.Z/gemini-3.8-flash/REVIEW.json
```

The Gemini audit should contain a verdict, findings with severity/evidence, quantitative/statistical assessment where relevant, causality/provenance assessment, safety state, and a concise advisory next-stage recommendation.

Gemini does NOT need to:
- perform a separate pre-freeze critique round;
- read or reconcile a ChatGPT review;
- create a disagreement matrix;
- perform a second review after ChatGPT;
- write the authoritative next-stage prompt.

### D. ChatGPT final review and next-stage proposal
After Gemini's audit is available, ChatGPT:
1. reads the exact implementation state and Gemini audit;
2. checks the material findings, especially BLOCKER/HIGH claims, against repository evidence;
3. determines the final consolidated stage verdict;
4. decides whether the correct next action is promotion, repair, stop, more Forward accumulation, or a genuinely new hypothesis/data family;
5. writes the next-stage prompt and commits/uploads it to GitHub.

No formal reconciliation round is required.

Gemini's review is advisory evidence, not an authority that ChatGPT must mechanically accept. However, an unresolved BLOCKER/HIGH finding must block promotion unless ChatGPT can directly disprove it with repository evidence and explicitly state why.

## Required reviewer checks

### Lineage / Git
- exact branch and SHA
- correct parent/base
- protocol/preregistration commit precedes formal result commit where required
- no hidden result-driven changes before freeze
- CI associated with the relevant reviewed SHA

### Quant / statistics
- causal features only
- chronological splits / purge / embargo where required
- no random-mask OOS claims
- multiple-testing universe complete
- no best-backtest-wins selection
- adequate sample size and direction balance where applicable
- fold/year/regime stability
- cost/funding/slippage treatment
- bootstrap/block units correct
- candidate-gate implementation matches frozen protocol

### Data provenance
- archive/vendor/Forward roles correct
- checksums/manifests verified where applicable
- no gap fill presented as real events
- no receive-time fiction
- true Forward gaps remain gaps
- no synthetic historical L2/OFI/microprice/depth from candles

### Runtime / execution
- deterministic decision path
- Agent cannot override deterministic QuantCore
- no future price embedded in decision object
- execution/replay entry semantics are causal
- execution remains disabled unless separately authorized
- no credentials/order path accidentally enabled

### Forward evidence
- campaign IDs/start boundaries immutable
- elapsed wall-clock denominator correct
- missed slots counted honestly
- data-quality terminal gates enforced
- successor preregistered only on a future fixed boundary
- no stitching/restarting terminal campaign under the same ID

### Engineering
- ruff/mypy/pytest/coverage/compileall as applicable
- configured Python CI matrix
- direct tests for new critical code
- systemd/restart behavior where relevant
- network/storage/resource contention
- observability and fail-closed behavior

## Severity

- BLOCKER: research integrity, look-ahead, Holdout breach, live/execution safety, evidence tampering, invalid preregistration, or material correctness defect
- HIGH: changes result validity or Forward eligibility
- MEDIUM: engineering reliability/coverage/documentation issue that does not yet change the primary inference
- LOW: style/maintainability/non-material documentation

## Final decisions

Allowed consolidated decisions include:

```text
PASS
PASS_WITH_NONBLOCKING_FOLLOWUPS
REPAIR_REQUIRED
RESEARCH_FAMILY_STOP
FORWARD_DATA_INSUFFICIENT
REJECT_CANDIDATE
```

The final consolidated decision belongs to ChatGPT after reviewing both repository evidence and Gemini's audit.

Frozen deterministic quantitative gates outrank either model's narrative preference.

## Artifact convention

Default required review artifact for stage `vX.Y.Z`:

```text
reviews/vX.Y.Z/gemini-3.8-flash/REVIEW.md
```

Optional:

```text
reviews/vX.Y.Z/gemini-3.8-flash/REVIEW.json
reviews/vX.Y.Z/chatgpt/FINAL_REVIEW.md
```

The normal handoff after ChatGPT's final review is the next committed prompt, for example:

```text
prompts/vX.Y.(Z+1)/Agent_BTC_Quant_Agent_..._Prompt.md
```

A mandatory `RECONCILIATION.md` is no longer part of the default workflow.

Review artifacts are evidence only; they may not rewrite formal historical research outputs.