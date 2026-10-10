# quant v0.6 — post-locator BTC minute Kline / true Mark / Funding PIT source admission design R1

**Status: CONTROLLER_DESIGN_ONLY__NOT_SOURCE_ADMISSION__NOT_AN_EXECUTION_DISPATCH.**
**Date:** 2026-10-10. This is a prospective scientific/data methods specification that can be written from existing published source locations and governance. It DOES NOT give an agent permission to read any real market-price, mark, funding, derived return, H39, protected holdout, Forward or live payload. Do not retrofit old one-shot P2 scanner as approved access guard.

## 1. Authoritative lineage and scope

- Owner-reported exact WSL root: /root/workspace/project/Quant-agent/data, BTC perpetual historical root /root/workspace/project/Quant-agent/data/research/BTCUSDT. Original six nonprotected monthly 1m Parquet physical-file metadata evidence: feature/v06-bline-p2-owner-exact-root-metadata-r1@c6823dbc46249cac43aa10400aacbbe9f4542410 (2021-03/04, 2023-03/04, 2025-03/04), 11 additional named source file/directory metadata objects. Preserve the exact immutable receipt; no direct Controller local filesystem remeasurement.
- Latest verifier code SHA 4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8 has CI green (2831 passed) but **NOT approved** for enforcing future data-access limits due to CLI custom-root guard bypass and uncounted direct lstat calls. Controller terminal ca0b6ea62613e6981b6f818f37f45be8c1d74901; patch campaign ended. The data-location proof and semantic quality gate are distinct.
- R4 research report SHA 5032259954e001635c97110c9c50e4a35a2c95b5 contains original eight unchanged plus three proposed-only hypothesis mechanisms; only CONDITIONAL SCIENCE, not Alpha. P1 old VirtualBook/alternate custom engine both terminal NO-GO SHA fd3c13645df9ad2506293b109d3891cf57936208. No P3 effective prereg / P4 empirical bodies / TESTNET / LIVE.
- User data tree includes BTCUSDT 1m Hive Parquet, BTCUSDT raw/{klines,mark_price,funding} monthly archives, funding_events.csv, mark_price_daily (only 9 daily data objects according to owner's tree), BTCUSDT_SPOT 1m separate, cross_asset_1h/ETHUSDT.parquet hourly, v0.3.19 official derivatives hourly inputs and source manifest; no verified ETH/SOL perp 1m, no proven separate contiguous true-minute Mark. Treat directory names as location hints, not data-grade or rights evidence.
- **Protected** BTC [2026-02-01,2026-08-01), including all Feb–Jul 2026 data and any derived outputs; data/forward/**, data/research/h39_validation/**, Quant-agent-sanitized and protected H40/H41/H42 outcomes: zero metadata traversal/file body access under this stage.

## 2. Separate capabilities; keep fail-closed

**Level S0 — OWNER-DECLARED LOCATION (achieved):** Owner supplied WSL exact path and tree. Does not prove physical file or rights.

**Level S1 — POSITIVE METADATA EXISTENCE (achieved for six selected BTC 1m Parquet files only):** Executor bounded lstat receipts show six regular files; no schema, row, content checksum, ordering, funding/mark physics, or PIT. We accept existence evidence only; do not run unsafe verifier again.

**Level S2 — SOURCE-PROVENANCE/RIGHTS AND NO-OUTCOME MANIFEST DESIGN (this document only):** List explicit positive source file paths, exchange/provider/endpoint/symbol/data kind/resolution, UTC availability clock definitions and local custody/hashes *requested* for future independent collection, exact allowed months, protected path exclusions, user rights and read scope, expected gaps/source reliability and deterministic invariant scheme. Record "UNKNOWN" wherever source unsupported. No actual body opens or inspect price values.

**Level S3 — RESTRICTED SOURCE QA (FUTURE explicit dispatch only):** Require Controller-granted NEW exact SHA and a separately independently verified safe reader with explicit file allowlist/maximum bytes/zero-protected/no-symlink/cap enforcement, plus rights. Only then may investigate bounded source content. Start with structural Parquet metadata/schema if explicitly authorized; reading rows/price/mark/funding values requires an additional explicit market-body approval and pre-pushed experimental prereg where required. Read the minimal selected nonprotected development inputs only; do not improvise fallback to protected or other periods.

**Level S4 — EMPIRICAL VALIDITY/P3/P4 (NOT AUTHORIZED):** First-pushed exact-SHA model/method/prereg + accepted full PIT/Mark/Funding/fill/cost semantics and independent measurement tool, then separate finite empirical diagnostic grant; use no old P1 engine. Candidate positive/negative assessment and live/trading authority remain separate gates.

For future actual read grants, make operator capabilities separate: filesystem existence lstat-only; manifest/schema-only; timestamp/proof-clock QA; market body QA; strategy outcomes. A grant for one never implies next.

## 3. Source inventory and explicit proof requirements

| Contract source | Candidate owner path | Current state | Future acceptance evidence |
|---|---|---|---|
| BTC USD-M perp trade-price Kline 1m | research/BTCUSDT/1m/year={2021,2023,2025}/month={03,04}/data.parquet | six lstat metadata present | selected six distinct file hashes, schema, UTC minute open/close, monotonic/unique full-minute partition completeness, exchange lineage and API/source time; no forward fill, duplicates or incorrect futures/spot alias |
| BTC perp raw Kline | research/BTCUSDT/raw/klines/ (parent only) | directory metadata present | match symbol/time to assembled 1m Parquet, independent provenance and known-at constraints |
| BTC true continuous 1m Mark | research/BTCUSDT/raw/mark_price/ (parent only) | unverified; existing monthly filenames do NOT prove 1m source | exact raw frequency, event timestamps and available_at, full 1m coverage aligned to 1m trade data, no daily-derived reconstruction, independent source vs trade price, event identity and conflicting same-close fail-closed |
| BTC Funding events | research/BTCUSDT/funding_events.csv; raw/funding/ (metadata parent) | CSV/file and folder metadata present; content unexamined | distinguish published prediction vs settled actual rate; available_at vs event/settlement clock, exchange UTC cadence, past revision provenance; ±15s boundary proof, signed long/short cashflow and nonnegative liability treatment without hindsight |
| Historical contract, fees and friction | source manifests/official derivative inputs | presence metadata only | symbol lot/tick/min notional over time, maker/taker effective VIP schedule, spread/impact execution assumptions, caps and funding uncertainty; no selection from realized future |
| BTC spot auxiliary | research/BTCUSDT_SPOT/ | not execution source | never silently substitute for USD-M perp or mark/funding |
| ETH / SOL perp true 1m | no verified files (ETH cross_asset_1h only) | UNKNOWN/NOT ADMITTED | exact independent ETH/SOL continuous 1m perp trade Mark/Funding files and rights before three-asset protocol claims; no extrapolation from hourly |

**Core PIT clocks:** each minute m full price bar [m,m+60000), earliest proven available_at per frozen spec; full Mark sampling/correction availability separate; funding settlement S and known-at/corrected-at separate; historical exchange filter fee effective_at and publish time; entry decision H+60000, earliest fill H+120000 in R1.2 prospective method; ACK proof >= max(economic event+60000, required proof, extra declared delay). Any absent proof => UNKNOWN/BLOCK, not zero funding or constructed continuous Mark. Distinguish R1.1 vs prospective R1.2.

## 4. Future safe source QA preconditions, not execution

- Freeze source-purpose first: selected **six** nonprotected BTC months, no 2026 or protected derived metadata; static *path components* and exact regular files, no traversal, no symlinks, no external mount escape, defend CLI option bypass and meter actual syscalls (not counters for unique paths). Independent static audit and synthetic break tests are prerequisites to any new read tool.
- Specify row-content read capability separately from Parquet footer read capability; footer metadata still requires prospective permission and privacy/usage controls. Source licencing/terms or owner read consent must be independently recorded. Never inspect training/protected/holdout to choose source windows.
- File SHA full-data hashing is itself an entire file read and needs separate explicit allowance. A manifest-declared checksum is not observed checksum. For large dataset minimize IO and memory, use fixed selected source file SHA receipts after grant; never treat a missing hash as PASS.
- Genuine 1-minute Mark and funding settlement timing are priority blockers. Mark daily archive with nine daily records must not be used to fill 1m series. Signed funding and multi-event horizons must preserve funding economics; unknown cadence is conservative proxy, not exchange proof.
- A future QA task must state exactly which source/path/time/columns and *whether* reading raw price values is authorized, bytes/rows cap, allowed output aggregates that do not leak protected outcomes, no hidden market API; record actual in-band violations and hard STOP. It must never silently promote raw data to effective prereg/P4.

## 5. Decision about research universe and measurement

- Original protocol uses <=60% **single asset exposure** for a positive development screen, not >=60% assets present; BTC-only positive population is 100% BTC and fails THAT positive multiasset screen. A **BTC-only finite diagnostic** may be proposed separately as source-limited research with NO three-asset positive claim. Prospectively specify what will constitute utility of that diagnostic and stop criteria before outcomes.
- R4's highest conditional *future test-priority* was 4h Structural Continuation and 4h Closed Retest (LONG/SHORT symmetry) under abstract cost+power rubric; all source-blocked. Do not rank actual empirical returns.
- For any next program, select one reference measurement option without resurrecting P1, preferably design of finite independent PIT/accounting trace oracles with external mature data pipeline, after source path and rights proof. Avoid mixing tool acceptance with strategy evidence.
- No inference of any directional BTC trade from this design; user decisions remain separate from project research qualification.

## 6. Prospectively valid next authorization

**NEXT REQUESTED CONTROLLER GATE: P2_NONPROTECTED_SOURCE_MANIFEST_AND_RIGHTS_DESIGN_R2**, **DESIGN ONLY**. It can be performed by a research agent using only the fixed governance documents and user-provided directory tree, producing:
1. one exact source alias/availability/rights/clock matrix with explicit UNKNOWN and unused protected scopes;
2. Mark and Funding legal-PIT acceptance tests and adversarial counterexamples that can later be executed on **synthetic-only** fixtures;
3. a new data-reader security conformance contract with independent verification before any actual row access;
4. a proposed finite staged grant for S3 with test/bytes budget and source purpose, not an immediately executable grant;
5. decision between three-asset original candidate screen and newly scoped BTC-only diagnostic, preserving evidence/multiplicity/holdout fences.

No further patch to old verifier, no user raw-data transfer required, no auto-P3/P4. **Terminal today: P2_SOURCE_ADMISSION_DESIGN_ONLY_PREPARED; SOURCE_ADMITTED=NONE.**
