# BTC Quant Agent — Post-v0.3.17 Forward Evidence Checkpoint

## Purpose

This is a **checkpoint / observation prompt**, not a new strategy version. Do not create v0.3.18 merely because time has passed.

Use this prompt only for 7d/14d/30d checkpoints, or when an operational alarm/gate transition occurs.

## Frozen lineage

Formal v0.3.17 delivery SHA:

`7ffadae819b03fb5d9de57a0c8b85c3ca6acb637`

Branch:

`codex/v0.3.17-opportunity-successor-forward-stabilization`

Do not alter H36, the derivatives successor epoch, microstructure campaign identity/start time, TP/BR definitions, runtime direction eligibility, or Final Holdout.

## Safety

Must remain:

- strategy: EXPERIMENTAL
- qualified_direction_engine: NONE
- runtime maximum: OPPORTUNITY_ONLY
- execution: DISABLED
- candidate_freeze: NONE
- Final Holdout: SEALED

No Alpha scan, no threshold/window search, no LONG/SHORT, no Entry/SL/TP/size, no Paper/Testnet/Live.

## Checkpoint tasks

1. Read current branch and exact HEAD; do not rewrite historical evidence.
2. Inspect real systemd state for:
   - `btc-quant-forward-derivatives.timer`
   - `btc-quant-opportunity-forward.timer`
   - `btc-quant-opportunity-resolve.timer`
   - `btc-quant-microstructure-forward.service`
   - `btc-quant-forward-health.timer`
3. Run the current supported CLI health/status/audit commands and capture structured JSON.
4. Report H36 wall-clock expected slots, successful scans, misses, scan ratio, maximum consecutive misses, opportunities, resolved 4h/8h outcomes, controls, distinct days, and terminal/evaluable state.
5. Report `DERIVATIVES_PIT_EPOCH_V0316_002`: age, expected/recorded/full/partial/failed/missing, every required-field coverage, max gap, terminal/evaluable state.
6. Report microstructure rolling 24h/7d trade/depth/sequence-valid coverage, uptime, heartbeat freshness, gap taxonomy, reconnect/resync/orphans, clock offset/RTT, duplicate/conflict counters, finalized-partition integrity and checksum drift.
7. Verify no raw/backfilled/manual/legacy row improperly improves a formal Forward gate.
8. If the machine was suspended/shut down/network-disconnected, preserve the resulting wall-clock gaps exactly; never retrospectively turn them into successful PIT observations.
9. Do not infer a research result before the frozen minimum sample/calendar gates are met.

## Transition rules

Do **not** start a new strategy version unless one of these triggers occurs:

### Trigger A — operational defect
A new correctness/reliability defect threatens forward evidence. Create a narrowly scoped infrastructure repair version and preserve all existing evidence.

### Trigger B — Derivatives data becomes eligible
Only after the frozen derivatives gate passes, create a preregistered **Derivatives Direction Feature Qualification** round. Test one small, frozen feature family at a time. No threshold/window fishing and no Final Holdout.

### Trigger C — Microstructure data becomes research-ready
Only after the frozen long-run coverage/integrity guideline passes, create a preregistered **Microstructure Direction Qualification** round using a minimal frozen set such as OFI/depth imbalance/aggressive-flow features. No future-return screening before preregistration.

### Trigger D — H36 becomes evaluable
Run the frozen H36 Forward Opportunity analysis exactly as preregistered. Do not change TP/BR definitions or matching after observing outcomes.

## Deliverables

For each checkpoint, create and push to GitHub:

`deliverables/checkpoints/<UTC_DATE>/`

At minimum:

- `README.md`
- `FORWARD_EVIDENCE_STATUS.json`
- `H36_STATUS.json`
- `DERIVATIVES_STATUS.json`
- `MICROSTRUCTURE_STATUS.json`
- `OPERATIONS_HEALTH.json`
- `CHECKPOINT_RECOMMENDATION.md`

The recommendation must be one of:

- `CONTINUE_FORWARD_ACCUMULATION`
- `OPERATIONAL_DEFECT_REQUIRES_REPAIR`
- `DERIVATIVES_RESEARCH_GATE_REACHED`
- `MICROSTRUCTURE_RESEARCH_GATE_REACHED`
- `H36_FORWARD_EVALUATION_GATE_REACHED`

Commit and push all checkpoint deliverables. Raw SQLite/PIT/event data remains outside Git unless repository policy explicitly changes.
