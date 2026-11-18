# V065-DATA-P0 — Complete usable historical data coverage and existing forward-store migration

**Controller → Codex Sol Max / Antigravity High**  
Task ID: V065-DATA-P0-HISTORICAL-EXPANSION-AND-ACTIVE-CUTOVER-01  
Priority: P0, alongside (but disjoint from) the P0 offline research pipeline.  
Owner purpose: personal noncommercial, private nonproduction research.  
Repository: EXASHXE/btc-quant-agent-public, engineering branch v0.6.5, current known SHA 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77; refresh before editing.  
Host: hyz-laptop. Approved data root: /root/workspace/project/crypto-data.

## Deliver actual data and working workflows, not another audit loop

This task has **two separable workstreams**, H (historical backfill) and F (cutover of pre-existing forward collectors). H can complete while F is held for consequential production authorization. Never turn a F STOP into failure of H. **Produce files, QC results, manifests, a working resumable downloader if allowed, and observable coverage.** Report achieved and missing ranges, not only plans.

P0 offline pipeline is assigned to another coding agent. Coordinate: **DO NOT edit scripts/research/r11_d2/** or tests/research/r11_d2/; that agent owns those paths. You may add independent data tooling to scripts/data or tools/data and tests/data only if needed. Do not create a branch/worktree by default. Never stash/reset/reformat/stage/commit/push or overwrite Owner's 14 existing uncommitted R4 documentation/prompt changes. Do not install CI, enable a cron job, change research/economic gates, or run protected data.

### H. Complete inventory, preserve prior migrations, extend actual research data

**Known completed moves — verify, do not redo or delete**
- Historical R10 data: /root/workspace/project/crypto-data/historical/r10-binance-vision/data, 42 files, with original pilot data symlink still present.
- Historical R11-D2 data: /root/workspace/project/crypto-data/historical/r11-binance-core-pilot/data, 430 files, with original pilot data symlink still present.
- Original immutable move receipt: /root/workspace/project/crypto-data/_control/HISTORICAL_RELOCATION_RECEIPT_R1.json; SHA256 e9b79ceb115712d88bcd0b2deeffc8bcd90b28ca174d58833be5e6000e7a8404.
- R11 prior offline QC: /root/workspace/project/r11-d2-binance-core-pilot/reports/offline-qc.json, showing 215 evaluated planned objects and accepted-with-limits terminal. This report is NOT itself a receiver-PIT proof.
- Physical data root is ext4 /dev/sdd; at last sample approximately 721 GiB free. Recheck before allocating.
- Only separately approved allowlisted nonprotected locations are eligible. **Never** scan or copy private /root/workspace/project/Quant-agent/data outside the exact named forward cutover graph below, Quant-agent-sanitized, history, private credentials or protected research samples.

**H1 — finite data inventory (not a broad audit):**
Produce a source/symbol/family/time-range/interval/bytes/QC matrix for existing named R10/R11 files and evidence reports. Preserve the origin source terms, ZIP checksums, exact symbol (BTCUSDT and ETHUSDT), millisecond/microsecond field units, UTC time, traded market (USD-M perp vs spot, never conflate), gaps, missing data and incomplete archive. Include bytes already present and what will be added; do not mislabel D2's fixed 215-object manifest as complete for newly added periods.

**H2 — acquire new historical bytes when applicable dataset licence/access are confirmed:**
Owner approved private noncommercial historical research and downloads, NOT trading or proxy/geofence circumvention. For Binance Vision historical archive, verify current official repository README and official Vision Dataset Terms version (latest observed v1.0 / updated 2026-08-26), entity/regional terms applicability and effective rate limits BEFORE a request. Official dataset terms permit purely personal nonproduction algorithmic historical backtesting within their scope, but do not automatically grant Binance.com live REST/WS access. If a specific access/retention condition remains genuinely uncertain or legally barred for Owner's mainland China/Singapore residence, mark that source RIGHTS_HOLD and do not circumvent by VPN/proxy/foreign accounts. Proceed with any other independently eligible bounded source. Do NOT turn an ambiguous permission into fabricated authorization.

Initial high-value **contiguous twelve-month** research target: BTCUSDT and ETHUSDT Binance USD-M perpetual historical interval **2025-10-01 00:00 UTC through 2026-10-01 00:00 UTC exclusive**, supplementing the existing January 2024 pilot. Target priority:
(a) native 1m klines;
(b) 1m mark-price klines;
(c) actual funding-rate history (correct funding timestamp and interval);
(d) available 5m/daily market metrics including historical OI snapshots and long/short ratio with exact data-source field semantics.
Only select archive objects that officially exist and match a pinned schema; missing files are MISSING_SOURCE, not silently synthesized. Use 1-month immutable archive ZIPs where appropriate and bounded daily ZIPs only for families actually daily. Confirm whether index-price klines are required, but do not increase scope until (a)-(d) yields a contiguous analysis-ready dataset. Funding is event-based, not 1m fabricated funding data. OI metrics are publisher-side historical samples, not a user receiver's first-known PIT.

Stage the **first three monthly periods** (2026-07 through 2026-09) to prove fetch → checksum → QC → restart; continue backward to 2025-10 once PASS within budgets. Hard per-task initial budgets: at most **4 GiB cumulative compressed new bytes**, **16 GiB expanded**, **10,000 requests or objects combined** (prefer far fewer), **12 hours bounded active execution** and **>=100 GiB free-space floor**. No unbounded retries, no redirected HTTP to unknown host, no missing checksum bypass, no API keys/accounts, no continuous background daemon; low-rate/backoff respecting official limits. Before exceeding a budget, STOP_BUDGET with an exact resumable coverage manifest and smallest extension request. Never write into the original R10/R11 folders or their symlinks; new dataset root:
  /root/workspace/project/crypto-data/historical/binance-usdm-2025q4-2026q3/
Use .part staged atomic download, server-defined checksum validation, streaming SHA256 and bounded ZIP expansion/row QC before final publish. On interruption, preserve a resumable state without claiming incomplete objects PASS.

Optional OKX secondary enrichment (only after Binance tranche is usable): establish official BTC-USDT-SWAP and ETH-USDT-SWAP historical candle/funding source identity and noncommercial storage rights, then ingest a **bounded representative 7-day 5m sample**, if authorized and technically available, with true period limits and no invented historical book/OI. Keep OKX data physically segregated and source-labelled. Never claim OKX futures data equals Binance USD-M. If rights are unclear, deliver a confirmed schema/coverage status and STOP_ONLY_OKX while preserving completed Binance output.

**H3 — actual reproducibility gate:** write a versioned research inventory/manifest separate from D2's fixed original 215-object manifest. For each expected object record planned identity, obtained/missing, source URL/product, immutable original checksum, local SHA256, publisher checksum, native time unit, row count, UTC min/max, duplicate/gap/conflict counts and QC terminal. Fail closed for missing checksum or mismatched symbol/bar intervals. Write a concise machine-readable historical coverage.json and QC report under an owner-approved NEW report path alongside this new dataset. Test idempotent rerun on a few already-present objects (no redownload/overwrite). Show an actual executable command and actual file counts/bytes/coverage rather than design text only. Historical source archives are permitted for offline QC but DO NOT upgrade causal first-receipt/ACK/PIT or Alpha.

### F. Finish existing active forward data migration, only after specific production safety acceptance

Known active source graph (metadata from verified R2):
OLD=/root/workspace/project/Quant-agent/data/forward/BTCUSDT
NEW=/root/workspace/project/crypto-data/active/forward/BTCUSDT
Includes derivatives.sqlite3, opportunity_shadow.sqlite3, microstructure/, associated SQLite WAL/SHM, manifests/sidecars. Previously ~102.1 GB, changes with ongoing collection. Four existing periodic systemd user timers + persistent microstructure-forward service, currently still writing OLD. Do not move/delete/symlink original protected bytes. After approved cutover, NEW is authoritative for newly collected bytes; original OLD stays immutable evidence/rollback.

R3 synthetic graceful-stop qualification report:
 /root/workspace/project/crypto-data/_control/MICROSTRUCTURE_GRACEFUL_STOP_QUALIFICATION_R3.md
 SHA256 183853bb262c6934c295a1372171621ce5ecb36564ba60d7f30e2d064dc79444
Independent 1-A conclusion:
 /root/workspace/project-review-output/v065-microstructure-nonkill-r3-1/INDEPENDENT_REVIEW.md
 SHA256 53fccec495662d11963a9532d192e12141cb673cff3d09b0202b5f7631329a6e
 Verdict ACCEPT_SYNTHETIC_NONKILL_POLICY_WITH_LIMITS.
This approves ONLY a nonproduction stop policy, NOT an actual production shutdown or dataset cutover.
Real unit currently TimeoutStopSec=20s and SendSIGKILL=yes. Proposed NOT INSTALLED reversible two-line override:
 [Service]
 TimeoutStopSec=infinity
 SendSIGKILL=no
Real finalizer may audit/checkpoint/hash >60GB and may stay deactivating indefinitely. Thirty minutes is ONLY a Controller decision deadline, not a finalizer maximum or kill timer.

**F1 — without owner downtime-tolerance acceptance:** perform only safe read-only preflight, exact proposed systemd drop-in/effective route syntax proof using nonproduction fixtures, backup+rollback commands and exact plan. DO NOT change real units, signal, stop, reload, snapshot/move an active SQLite/WAL, or create a second writer. Return F_AWAIT_OWNER_DOWNTIME_ACCEPTANCE without blocking H.

**F2 — only after separately recorded Owner acceptance of potentially indefinite microstructure downtime, unbounded pending stop, missed timer origins and no forced kill, PLUS Controller start authorization:** perform the already authorized migration as one finite, supervised maintenance operation. Before any action, check active users/API consumers and routes again; if any API/dashboard is actually running, STOP. Optional dormant API /health hardcodes old derivative SQLite; final status must label API_HEALTH_NOT_MIGRATED; future API enablement requires repair. Quiesce all known timers and microstructure, install ONLY reviewed reversible stop guard, single no-block SIGINT stop with monotonic 30m decision watchdog. At deadline with active PID, leave process stopping/timers paused, no additional signal, no snapshot/cutover; report STOP_PENDING_GRACEFUL_EXIT. If clean shutdown with affirmative finalization/integrity proof, use crash-consistent frozen snapshot, full hash/SQLite integrity, copy to NEW, apply scoped systemd service drop-in routing (derivatives, opportunity, resolver, health, microstructure), verify effective commands, strict no-duplicate-writer policy, recoverable rollback, then resume previously active tasks at existing cadence and confirm >=2 scheduled origins on NEW. Any anomaly fail closed; do not invent continuity/PIT or delete OLD.

**In this dispatch, Owner still has NOT specifically accepted the indefinite downtime risk. Therefore F2 is CONDITIONALLY NOT DISPATCHED.** Do not reinterpret this job prompt as a stop command.

### Deliverables and outcome

Primary execution report ONLY after actual work:
- H outcome H_COMPLETE_COVERAGE_QC or H_PARTIAL_COVERAGE or H_RIGHTS_HOLD, with actual on-disk object counts, final bytes, missing spans, checksums, exact reproducible command and tests;
- F outcome F_AWAIT_OWNER_DOWNTIME_ACCEPTANCE or F_CUTOVER_VERIFIED or F_STOP, with exact production unit status and rollback evidence. Do not report F_CUTOVER_VERIFIED from synthetic fixtures.
- Original R4 dirty Owner docs not touched; no commit/push by default; GitHub public branch stores ONLY controller task prompt, no actual raw data or personal credentials.
- No need for repeated 1-A/2-R/2-C chain. Escalate independent verification only for actual licensed source/PIT admission, consequential *live* data cutover or money-sensitive operation, not routine archive QC.

Hard invariants: SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE.

**Definition of done for this stage:** source-eligible new BTC/ETH historical files physically present in crypto-data, verified ZIP/checksum/QC and measurable contiguous coverage; all existing R10/R11 directories intact. A proved active-store cutover is a separate gated milestone, not a reason to withhold useful H data.
