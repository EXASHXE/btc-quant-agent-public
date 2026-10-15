# quant v0.6 — Controller R11-L1 Wave-1 A/B/C + R10-D1 Evidence Reconciliation R1

**Date:** 2026-10-16, Asia/Shanghai. **Authority:** ChatGPT-0 B-line Controller. **TERMINAL: `R11_L1_WAVE1_DOCUMENTARY_ACCEPTED_Q1_INDEPENDENT_AUDIT_REQUIRED`.** This is review of frozen published artifacts, NOT source/PIT/admission or a buy/download/experiment release.

## 1. Exact frozen evidence table

| Task | Exact author SHA | Direct parent | Report blob | Author terminal | CI |
| --- | --- | --- | --- | --- | --- |
| A Binance | `561084fe1c1f566138e7c4a2ab4c24fe3625ee94` | `ade4df19872122686432cd955d8f139f16069449` | `03c3d1c10c67c36845f6e2c12bd018b37139feef` | `A_METADATA_READY_WITH_LIMITS` | run 38781376690 FAIL |
| B OKX | `5d394450f447d728e0fc103ea72cab33b40a3a46` | `ade4df19872122686432cd955d8f139f16069449` | `9fa86ca37ad80320bce167ad45f0b9c84f439d94` | `B_DOCUMENTARY_READY_WITH_LIMITS` | run 38782305568 FAIL |
| C schema/storage | `5b9d86209fa71ca2f4732f85b85846434c52af3e` | `ade4df19872122686432cd955d8f139f16069449` | `870c34be446962aeb3b2a7a23591ba75d725b35b` | `C_DESIGN_READY_WITH_LIMITS` | run 38780790820 FAIL |
| R10-D1 local Codex QC | `5630b178bf2f497f67a7e2db2d730f0b2aacabfe` | `4d83123243db8cf5ac4fd7b1c00608cb149f7bdc` | `7e8f126287e428c739d8c65230eb4366cc8c3256` | `R10_D1_LOCAL_DEV_QC_PARTIAL_STOP` | run 38779186106 FAIL |

All author branch heads, sole direct parent relations, individual report blobs, and compare vs respective Controller base have been remotely verified. **A/B/C compare ahead 1/behind 0, one added report each; D1 ahead 1/behind 0 and three added files: `docs/project/V06_R10_D1_CODEX_LOCAL_BINANCE_VISION_DEV_QC_R1.md`, `scripts/research/r10_d1/vision_qc.py`, `tests/research/r10_d1/test_vision_qc.py`.** All hosted run failures stop on inherited 6 Ruff diagnostics in unchanged `evidence/v0.5/h41/h41_synthetic_pit_validation_r1/`; this is a CI FAIL, never PASS and never authorization to patch H41. A/B/C are separate branches, not silently merged into one codebase.

## 2. Factual findings and source-strength boundary

- **R10-D1:** On already-exposed `BTCUSDT USD-M` 2022-09-15..21, author reports 21 ZIP objects and 21 verified SHA256 checksums, 758,218 compressed / 2,343,412 expanded bytes; 1m USD-M last/klines and official markPriceKlines each have **10,080 unique complete bars**. Metrics 7×288=2,016 5m labels with no interior holes; however `count_toptrader_long_short_ratio` AND `sum_toptrader_long_short_ratio` each blank for ALL 2,016 rows, hence full-metrics schema incomplete. `create_time` labels 00:00..23:55, economic content-close/first publication remains unknown. Local author reports 24/24 synthetic tests and 1213 passed full pytest / 9 warnings, scope lint PASS; hosted full Ruff FAIL. No original receiver PIT, complete maker/taker economics or strategy smoke performed. This is real **reported local QC** but not independent data-source admission.
- **A:** Forty bounded official provider object-name/size listings substantiate representative Binance Spot/USD-M BTC/ETH family identities, including USD-M **monthly fundingRate** and **daily metrics**; NOT full date coverage and NOT local historical copy verification. A reports `LOCAL_INVENTORY_UNKNOWN`, no local root scanned, zero new archive payload.
- **B:** Documentary OKX Spot/Swap BTC/ETH coverage and methods from portal and V5, historical portal bulk OI absent, rubik OI history separately limited/unknown. L2 level/era and checksum semantics require independent verification; product-specific start/end/rights are not conclusively granted. Its broad conclusions about USA-person derivatives restrictions or rights for personal live execution are **report claims requiring source-clause applicability audit**, not adjudicated facts about this owner or portal vs API.
- **C:** Versioned venue×product×instrument×family×UTC partition manifest and Tier A/B/C architecture are useful design drafts. **No private disk stat, compression benchmark or new payload was performed.** Claims `~408 GiB permanent ceiling`, Tier A 18.2 GiB, Tier B 320 GiB, Tier C 4,500 GiB and a 60GiB staging budget are **assumption-based illustrative estimates**, not calibrated measured capacities. The historical approx 724 GiB free / 172.33 GiB existing were unverified. Do NOT call Tier A "safely fits" or let scenario precision imply observed data. C's suggested predetermined quiet/typical/stress days must be evaluated outcome-blind, not chosen from already known strategy performance.
- **Cross-product:** Binance monthly/daily duplication, Spot timestamps units and OKX Spot vs USDT swap contract units must stay distinct. Current API snapshot OI != historical exchange-native receiver event. Archived timestamps and checksums do not prove real-time historical known-at or true own-order ACK/fills.

## 3. Consequential Controller ruling and next ready stage

**Documentary workstreams A/B/C CLOSED / ACCEPTED_WITH_LIMITS.** They are not general rights or scientific accepts. **R10-D1 CLOSED / PARTIAL_STOP**: preserve verified 1m and Mark development field utility, exclude two missing top-trader fields; DO NOT repeat D1 ingestion solely to try for generic PASS.

**NEXT READY: `R11-Q1` independent ChatGPT-1 consequential review** of these four frozen outputs, sources/legal scope, D1 local code and synthetic tests (read-only), and C capacity assumptions. A new immutable Controller dispatch prompt is co-committed separately. This is one independent task, not parallel duplicate reviews in same chat.

**D Binance pilot:** still `PREPARED_CONDITIONAL / NOT_AUTHORIZED_TO_EXECUTE`. Need independently accepted D1 QC, owner-selected exact isolated workspace and lawful source + defined actual nonduplicative new file/date/cap purpose; B-line R9 new Alpha pause unaltered. **E OKX pilot:** `PREPARED_CONDITIONAL / NOT_AUTHORIZED_TO_EXECUTE`, need independent OKX rights/provenance ruling, exact file/date and named local workspace. **F/G/H:** conditional no execution. Do not reassign the same 7 D1 days or automatically expand to BTC/ETH multi-year trades/L2 from illustrative C numbers.

**Pending owner/environment evidence for any later byte intake:** an owner-authorized isolated path, current free filesystem stat and real partition-size samples in that path; owner-specific relevant jurisdiction/entity and official provider rights if unclear. No broad `Quant-agent/data`, `Quant-agent-sanitized`, H39/H40/H41, Final/Forward or reserved OOS root reads. No use of protected intervals for fresh Alpha, but already-exposed DEV remains legal/eligible if licensed and later expressly authorized.

No market request/download, strategy outcome, provider signup, paid service, pipeline code edit, new CI repair, protected access, TESTNET/LIVE/funds or branch merges were performed for this Controller adjudication.

**Preserved:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. Budget: $0 spent at this stage; overall owner $20 cap unless changed.
