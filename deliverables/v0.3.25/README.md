# BTC Quant Agent v0.3.25 Deliverables

This directory contains the deliverables for **v0.3.25: H39 One-Shot Unblind Preregistration & Acceptance Repair**.

## Deliverables Manifest

1. [`H39_UNBLIND_PREREGISTRATION_MANIFEST.json`](H39_UNBLIND_PREREGISTRATION_MANIFEST.json): Formal preregistration of hypothesis family, Holm-Bonferroni FWER control, baseline incremental modeling, stability diagnostics, and candidate decision rule.
2. [`H39_BLIND_OPERATIONAL_STATUS.json`](H39_BLIND_OPERATIONAL_STATUS.json): Current operational and sample maturity status under wall-clock coverage semantics.
3. [`FORWARD_CHAIN_HEALTH.json`](FORWARD_CHAIN_HEALTH.json): Audit of active derivatives, microstructure, and terminal H38 chains.
4. [`V0.3.25_H39_ONE_SHOT_UNBLIND_PREREGISTRATION_REPORT.md`](V0.3.25_H39_ONE_SHOT_UNBLIND_PREREGISTRATION_REPORT.md): Authoritative preregistration and gatekeeper engineering report.
5. [`V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.json`](V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.json): Machine-readable audit and specification of the committed freeze, exactly-once registry, and WAL-safe snapshot repair.
6. [`V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.md`](V0.3.25_COMMITTED_FREEZE_EXACTLY_ONCE_REPAIR.md): Detailed acceptance repair report resolving Findings A through F for ChatGPT final acceptance.

## Governance

- **Accepted Baseline (`main`)**: Commit [`e99964a3ced0c40424a4ace6dd59cc2376a2dea6`](commit://e99964a3ced0c40424a4ace6dd59cc2376a2dea6)
- **Protocol Freeze**: Commit [`0eecd8833675c664c42f5e62d89663d7a10ed5fa`](commit://0eecd8833675c664c42f5e62d89663d7a10ed5fa)
- **Protocol Clarification**: Commit [`2d1ccecc11dc231ffa41cdb1b5a9ea693abccc59`](commit://2d1ccecc11dc231ffa41cdb1b5a9ea693abccc59)
- **Current Stage State**: `FORWARD_DATA_INSUFFICIENT`
- **Unblind Readiness**: `REFUSED_NOT_MATURE`
- **Reviewers**:
  - Gemini-3.8-Flash (One-Pass Post-Implementation Audit: `56d03ad...`)
  - ChatGPT (Final Stage Acceptance)

## Operational Commands

```bash
# Verify readiness status (fails closed while accumulating):
quantctl h39 validation-readiness

# Attempt to freeze cutoff (refused before maturity):
quantctl h39 freeze-cutoff --output-path deliverables/v0.3.25/H39_ONE_SHOT_UNBLIND_FREEZE.json

# Execute one-shot unblind (refused without verified committed freeze manifest):
quantctl h39 one-shot-unblind --freeze-manifest deliverables/v0.3.25/H39_ONE_SHOT_UNBLIND_FREEZE.json
```
