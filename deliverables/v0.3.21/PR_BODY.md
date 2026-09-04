## Summary

Version 0.3.21 executes the comprehensive forward runtime recovery following the post-activation HTTP 451 geo-blocking failure observed in v0.3.20. Under strict non-alpha and research governance policies, this release permanently reconciles the compromised v0.3.20 Derivatives and Opportunity chains into terminal archives, hardens systemd services to fail closed against stale or terminal configs, resolves a structural collector/resolver configuration mismatch, provides robust local Windows/WSL power and storage resilience tooling, enhances the Forward Doctor with a typed 10-state health model, and preregisters clean successors on a future UTC boundary after authoritative preflight verification.

Following successor activation at `2026-09-03T18:00:00Z`, 45 continuous 15m slots of empirical forward evidence have accumulated with zero failed derivatives slots and a 97.8% opportunity scan ratio, satisfying all frozen quality gates.

## Lineage & Traceability
- **Base Version**: `0.3.20` (`ec08024588e6a766e061ed25ceb62ec24751fa61`)
- **Review Lineage**: Includes Gemini 3.8 Flash Independent Co-Review (`reviews/v0.3.20/gemini-3.8-flash/REVIEW.md`, `REVIEW.json`) and One-Pass Acceptance Audit (`reviews/v0.3.21/gemini-3.8-flash/REVIEW.md`, `REVIEW.json`)
- **Execution Target**: `agent/v0.3.21-forward-recovery-cutover` -> `main`

## Core Changes
1. **Phase A (Canonical Terminal State Reconciliation)**:
   - `DERIVATIVES_PIT_EPOCH_V0320_001`: Permanently marked `FAILED_GAP_GATE_TERMINAL` (`FORMAL_TERMINAL`, `terminal_at_ms: 1788420600000`).
   - `OPPORTUNITY_FORWARD_V0320_20260903T063000Z` (H37): Permanently marked `DATA_QUALITY_TERMINAL_ARCHIVE`.
   - Independent microstructure capture (`MICROSTRUCTURE_CAPTURE_V0315_001`) remains active and healthy.
2. **Phase B (Fail-Closed Service Execution)**:
   - Collectors dynamically resolve active non-terminal campaigns from registries.
   - Refuses execution cleanly (`REFUSED_NO_ACTIVE_EPOCH`, `REFUSED_NO_ACTIVE_CAMPAIGN`) when all registered chains are terminal.
   - Refuses execution cleanly (`REFUSED_PREREGISTERED_PENDING`) before frozen start boundary.
3. **Phase C (Collector/Resolver Parity Repair)**:
   - Eliminated hardcoded campaign version disparity in systemd service templates.
   - Both collector and resolver target `--registry configs/forward/opportunity_forward_campaigns.json`.
4. **Phase D (Windows/WSL Local Resilience & Resource Protection)**:
   - User linger verified active (`Linger=yes`).
   - Created `scripts/windows/recover_forward_wsl.ps1` for logon recovery and Modern Standby (S0) power suspend risk warnings.
   - Resource protection verified: 833 GB free disk space, SQLite `quick_check` passing `ok`, microstructure heartbeat age < 2.5s.
5. **Phase E (Forward Doctor Authoritative Preflight & Typed 10-State Model)**:
   - Implemented 10-state typed health model.
   - Enhanced doctor with optional deterministic `now_ms` timestamp injection for fully hermetic testing.
6. **Phase F (Conditional Fresh Successor Preregistration)**:
   - Network egress verified healthy via Tokyo, Japan endpoint (`150.249.219.212`), returning HTTP 200 with zero HTTP 451.
   - Clean successors preregistered for future UTC 15m boundary `2026-09-03T18:00:00Z` (`1788458400000` ms, 48-minute buffer):
     - Derivatives: `DERIVATIVES_PIT_EPOCH_V0321_001`
     - Opportunity: `OPPORTUNITY_FORWARD_V0321_20260903T180000Z` (`H38_OPPORTUNITY_FORWARD_REPLICATION_LOCAL_RECOVERY`)
7. **Phase G & Acceptance Repair (Verification & Deliverables)**:
   - Added `tests/test_v0321_resilience.py` with 6 deterministic tests covering both pre-start (`PREREGISTERED_NOT_STARTED`) and post-start (`HEALTHY_ACCUMULATING`) states.
   - Full test suite: 435 tests passing.
   - Added natural post-start evidence audit: `deliverables/v0.3.21/POST_START_SUCCESSOR_HEALTH.json`.
   - 100% clean ruff, mypy, and compileall.

## Preserved Safety Invariants
- Execution: DISABLED (zero orders, zero trading endpoints)
- Final Holdout: SEALED (unaccessed)
- Direction Engine: NONE (opportunity-only)
- Immutability: Zero backfill, zero row deletion, zero moving historical start times
