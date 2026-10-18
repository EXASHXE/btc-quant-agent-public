# quant v0.6.5 — P3 exposed-development scope and file-hash preflight

Task ID: V065-P3-EXPOSED-DEV-SCOPE-PREFLIGHT-R1
Controller 0 dispatch, MANUAL LOCAL Codex CLI 0.163.0, gpt-6.1-sol reasoning max (xhigh fallback only if max actually rejected).
Status: PREPARE OWNER DECISION ONLY. No historical outcomes evaluation, no unblinding, no trading, no scheduled task, no production migration.
Checkout: /root/workspace/project/quant-0.6.5; REFRESH HEAD but do not checkout/stash/reset/commit/push/modify working tree. GitHub docs/engineering is sole prompt home; do not save task prompt locally.

Owner reports P0/P1/P2 and DATA-R3 complete; current P3 exposed_dev_bridge created and passed 56 focused tests, bridge working, but full historical earnings P3_ACCESS_SCOPE_HOLD because no explicit Owner EXPOSED_DEV authorization. Treat status as reported until checked. Prior P3 Q2+Q3 inspection recorded 8,784 hourly origins / 8,712 native-feature-ready / 4,367 P1 BTC X/X+Z ready, partial source coverage because one OKX BTC 400-level L2 on 2026-04-01 is OBJECT_NOT_FOUND. DO NOT confuse this optional L2 gap with the OI-candidate A requirements.

## Precise known control authority in public v0.6.5 at 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77

- H39: configs/research/v0.3.22_microstructure_h39_protocol.json public blob SHA 31a06b0907577d2986e9b82dfa7918caaf846cf0. Development source cutoff 2026-09-01T00:00:00Z; isolation/buffer 2026-09-01T00:00:00Z up to 2026-09-04T11:15:00Z; validation begins 2026-09-04T11:15:00Z. Its source-specific blindness must not be indirectly breached by new cross-venue outcome probes on protected periods.
- H40: src/btc_quant_agent/h40/split_manifest.py public blob SHA 46979616e1b7b76b7e485fe2f69e3e7ef50ef270; CONFIRMATION_HOLDOUT [2025-02-01T00:00:00Z, 2026-02-01T00:00:00Z), with earlier train/calibration/validation reservations. The overlap semantics must be checked, not assumed source independent.
- Status docs/project/V0.6_B_LINE_STRATEGY_VALIDATION_REGISTER.md blob c7df2bd92f72c55a4eccbc823a0f005334c09047 explicitly retains protected H39/H40/H41/Forward/Final/OOS authority and disallows treating exposed past data as pristine OOS.
- Other private A-line/held-OOS/reserved scientific dates may exist in Owner's actual local evidence or protected private repo; do not assert that the public tree is exhaustive. Read governance **metadata only** (candidate reservation dates and IDs), never protected row contents, model labels, outcomes, irreversible test/unblind logs, or confidential raw datasets. If local provenance cannot be reconciled, mark UNKNOWN_PROTECTED_OVERLAP and fail closed.

## Candidate, not yet authorization

- Original P3 source coverage suggestion [2026-04-03T00:00:00Z, 2026-09-29T00:00:00Z) overlaps H39 September validation. Do not sign it.
- More conservative initial candidate EXPOSED_DEV window:
  [2026-04-03T00:00:00Z, 2026-09-01T00:00:00Z)
  half-open, BTC only for first mechanism A, Binance USD-M primary 1m bars/5m metrics/mark funding and only available actual OKX swap/spot controls.
- This candidate is not guaranteed free of other protected claims or source permissions; do not authorize simply because it appears here. Q2 may have one missing OKX L2 file which is irrelevant to this OI-only A baseline unless the adapter falsely requires it.
- 4/8/12/24h labels and funding attribution must remain within authorized bounds; for a 24h horizon, exclude any HH:01 origin too close to the right-hand boundary to mature before it. Treat feature lookback/warmup at left boundary explicitly.
- The identical data may be previously exposed by strategy exploratory work. New scope is EXPOSED_DEVELOPMENT, never UNUSED_OOS, never source receiver PIT; no claims of clean held-out alpha.

## Read-only task — factual decision packet

1. Inventory P3 actual code and schema:
   scripts/research/exposed_dev_bridge/{pipeline.py,inspection.py,authorization.py}; P1 schema; P2 cross_venue. Verify concrete scope contract fields by reading code, not guessing JSON names.
2. Discover every explicitly documented training/validation/holdout reservation intersecting 2026-04-03..2026-09-29 UTC across local public docs, local private evidence **metadata only** if legitimately available, and any source-specific release/QC ledger. Separate:
   - EXPOSED_DEV_ALLOWED_BY_EXISTING_RECEIPT
   - KNOWN_PROTECTED_EXCLUDE
   - PROVISIONAL_ONLY
   - UNKNOWN_REQUIRE_OWNER_DECISION
   Keep source path and exact supporting commit/blob/hash/line/authority for each. Do not use test outcome data to decide exclusions.
3. From existing immutably published PASS historical archive objects (Binance/OKX Q2/Q3) derive a candidate exact-file inventory ONLY for BTC fixed-origin mechanism A, include venue, market, symbol, native interval/family, archive period (UTC vs UTC+8), actual UTC start/end, source manifest SHA, object SHA256 and status, plus required lookback/label envelope. The P3 lineage_manifest.json is evidence but must be checked against actual hashes at stable file paths; if raw data permissions or owner evidence uncertain, do not read protected sources or fabricate SHA.
4. Produce 3 machine-readable receipts to a NEW isolated output dir under /tmp, not repo/historical:
   protected_scope_matrix.json — all date reservations, conflicts, source authorities and unknown.
   eligible_object_candidate.json — full-file hashes and required event-window slices, fail-closed source status, with candidate scope and no outcome labels.
   OWNER_EXPOSED_DEV_DECISION_TEMPLATE.json — actual schema-consistent UNSIGNED/DENIED owner decision envelope, date range, mechanism A only, permitted data object identity, allowed explicit development outcome use ONLY AFTER OWNER SIGN, protections, no OOS promotion, and final checksum for tamper evidence.
   Plus one <=1-page OWNER_SCOPE_DECISION.md with exact approval choices and a summary of unresolved conflicts. These 4 files are only a proposal, not an allowlist with active execution permission.
5. Source documents or manifest may change during scan: hash at start/end, report INPUT_CHANGED if inconsistent. Keep streaming and memory-bound. Avoid excessive scanning (>1000 archive files) unless data immutability proof requires it. If >100GiB compressed data and slow hashing, bound to relevant allowed object families and record completeness.
6. DO NOT generate or save an authorized EXPOSED_DEV allowlist until explicit Owner sign-off of reviewed scope+SHA list. DO NOT call P1 evaluate-historical or P3 materialize, compute return labels, inspect protected OOS records, or use exchange market APIs.
7. All existing Owner R4 dirty docs and the active P0/P1/P2/data code remain untouched. No git mutation, no downloader, no service restart, no F-R2 forward cutover. All artifacts new /tmp preflight dir and report exact location, SHA256 for decision template, count of candidate objects and protected/unknown conflicts. If remote machine has no evidence of private reservation metadata, explain that in Owner report.

Terminal: OWNER_SCOPE_PACKET_READY when frozen evidence, complete candidate object inventory and UNSIGNED template exist. If undiscoverable metadata, return OWNER_SCOPE_PACKET_PARTIAL with concrete missing categories and no authorization. Not SUCCESSFUL_ALPHA. No scientific trial, source-admission or production authorization.

Keep all gates: HISTORICAL_OFFLINE, SOURCE_NOT_ADMITTED, PIT_UNKNOWN, COST_UNVALIDATED_REAL_FILL, NO_ALPHA_ESTABLISHED, G2_ALPHA_NO_GO, G4_TESTNET_NO_GO, LIVE_NO_GO, REAL_FUNDS_WRITE_NONE.