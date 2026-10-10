# Quant v0.6 — P2 S2 Gemini Source Contract × Sol PIT Science Controller Joint L2 R1

**DATE:** 2026-10-10. **CONTROLLER VERDICT:** `ACCEPT_SOL_S2_SYNTHETIC_PIT_SCIENCE_BLUEPRINT__ACCEPT_GEMINI_S2_SYNTHETIC_GATE_ONLY_WITH_MATERIAL_SOURCE_MATRIX_ERRATUM__STOP_REAL_READ_PENDING_S3_RIGHTS_AND_INDEPENDENT_READER`.

This document records **independent GitHub exact-SHA/parent/files, CI log and artifact/source audit**. It is NOT a data-read dispatch, production security acceptance, strategy/Alpha result, future prereg activation or real trading permit.

## 1. Independent exact-GitHub identity and CI
| Gate | Gemini | Sol |
|---|---|---|
| Remote branch | `feature/v06-bline-p2-s2-gemini-source-contract-r1` | `feature/v06-bline-p2-s2-sol61-pit-science-r1` |
| Exact remote HEAD | `01af4fcef012e28fd85eaa2550d9539bd23fcf3a` | `e6bcaf62a69cde32149db3cd4997f7f2dad526ef` |
| Exact direct parent | `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` | `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` |
| Changed files | 16 **added only** under `scripts/strategy_research/p2_s2_source_contract/**`, `tests/test_v06_p2_s2_source_contract_*.py`, `docs/strategy_research/g2_r3/p2_s2_source_contract_r1/**`, `evidence/v0.6/b_line/p2_s2_source_contract_r1/**` | 12 **added only** under `scripts/strategy_research/p2_s2_pit_oracle/**`, `tests/test_v06_p2_s2_pit_oracle_*.py`, `docs/strategy_research/g2_r3/p2_s2_pit_science_r1/**`, `evidence/v0.6/b_line/p2_s2_pit_science_r1/**` |
| Ruff, mypy, compile/JSON | PASS | PASS |
| Actual exact-head CI | [38025010704](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38025010704) **FAIL**: full pytest **2822 PASS /1 FAIL /2 SKIP /9 warnings**, only unchanged `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph` frozen hash assertion `d5a962...` versus `ee185f...`; this is inherited H40 golden instability, **not** S2 failing new tests | [38025176018](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38025176018) **SUCCESS**: **2854 PASS /0 FAIL /2 SKIP /9 warnings** |
| Scoped results | Gemini execution receipt reports **38/38 synthetic security tests**, comprising 15 unit,23 adversarial; 3 deliberate mutants caught. CI full test results consistent with no new test failures, but do NOT say whole Gemini CI passed | Sol execution receipt reports Python3.12 **69 PASS**, Python3.13 **69 PASS**; exact-head GitHub CI success independently corroborates tests, not financial validity |

Both tasks honor prospective Controller dispatch `b176f4361cd97d1d89c3e25173b2c72a6af93ec4`. No frozen original hypothesis, P1 engine, protected H39/H40/H41 or A-line files modified. **A-line, Performance and G1/G3 untouched.**

## 2. Gemini — bounded design accepted, uncorrected metadata lineage is material

Reference artifacts: [Gemini synthetic policy execution receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/01af4fcef012e28fd85eaa2550d9539bd23fcf3a/evidence/v0.6/b_line/p2_s2_source_contract_r1/GEMINI_P2_S2_EXECUTION_RECEIPT.json), [Gemini source matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/01af4fcef012e28fd85eaa2550d9539bd23fcf3a/evidence/v0.6/b_line/p2_s2_source_contract_r1/SOURCE_SCOPE_AND_AUTHORITY_MATRIX.json), [future reader *proposal*](https://github.com/EXASHXE/btc-quant-agent-public/blob/01af4fcef012e28fd85eaa2550d9539bd23fcf3a/docs/strategy_research/g2_r3/p2_s2_source_contract_r1/NEXT_STAGE_MINIMAL_SOURCE_READER_SECURITY_CONTRACT.md).

**Accept**: the synthetic-only default-deny capability boundary, documented L0/L1/L2/L3/L4 separation, owner root/case, exact six selected nonprotected monthly paths, no actual WSL path scan/body read in S2, path/counter/permission negative-test exemplars, nonuse of terminated locator, and proposed future independently verified FD-based security.

**F01 — MATERIAL SOURCE DATA COPY ERROR IN GEMINI FROZEN S2 CONSTANTS/MATRIX/DOCS:**
Gemini `scripts/strategy_research/p2_s2_source_contract/constants.py` says `RECORDED_METADATA_FILE_SIZES` are from `c6823dbc...` but **four values do not match the immutable original lstat execution receipt**:
| Exact relative path | Immutable original receipt bytes `c6823...` | Gemini S2 constant / doc bytes `01af4...` |
|---|---:|---:|
| `research/cross_asset_1h/ETHUSDT.parquet` | **2,907,000** | **3,391,374** |
| `research/cross_asset_1h/basket_manifest.json` | **56,012** | **3,674** |
| `research/v0.3.19_official_derivatives/hourly_inputs.parquet` | **3,101,084** | **2,058,958** |
| `research/v0.3.19_official_derivatives/raw_data_manifest.json` | **420,725** | **4,402** |

Source of truth is the immutable exact original [raw stat-only receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/c6823dbc46249cac43aa10400aacbbe9f4542410/evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json). The six actual BTC 1m file sizes and `BTCUSDT/data_manifest.json`/`funding_events.csv` values ARE consistent; the four above are NOT. **No real file change or new lstat is inferred; this is a documented transcription/lineage mismatch in newly generated evidence.** Any S2 constant-based file-size validation or future source-capability claim referencing these four files is **NOT ACCEPTED**. A Controller erratum is authoritative over those S2 fields; workers MUST NOT silently change original evidence or assert the four bytes as physically verified. If a future code execution actually depends on these constants, the future new-SHA prospective task must explicitly correct and retest them before any permission.

**F02 — NEGATIVE CERTAINTY OVERSTATEMENT:** Gemini prose calls ETH/SOL missing 1m source `ABSENT` (and matrix `ABSENT_OR_UNPROVEN`). The actual bounded P2 check established **UNKNOWN / NOT VERIFIED / NOT ADMITTED**, not whole-host absence; preserve that status. ETH cross-asset `1h` is **not** ETH perp `1m` or SOL source.

**F03 — DESIGN IS NOT A REAL DESCRIPTOR READER:** `scripts/.../component_walker.py` uses string-composed paths + simulated `hook.lstat`; its optional simulated TOCTOU branch calls `hook.open(leaf_path, os.O_RDONLY)`, **not** live `dirfd/openat` with `O_NOFOLLOW|O_DIRECTORY`. The production `SyntheticSourceContractKernel` is intentionally disabled for physical data use; that is the correct no-read boundary for this dispatch. The document's proposed *future* descriptor-level `openat` contract is valid as a **future requirement**, not an implemented/independently audited FD-based reader or a real-data grant. Never use this synthetic walker against actual WSL `Quant-agent/data`.

**F04 — CONFLICTING PROPOSED STAGE A BUDGETS:** Gemini's future L2 design states `64KiB total for six Parquet footers`; Sol proposes bounded `6×(8+65,536) = 393,264 bytes` worst case, with exact per-file and total caps. Neither is an active budget; do not merge, inherit or use the more liberal figure without a NEW Controller prospective grant. Select **one nonprotected file first**, hard cap `8+65,536=65,544 bytes` *if separately authorized and independently safe reader proven*. Footer may include statistics of price/returns; parsing/reading it is an actual **file-content** read requiring owner and Controller consent.

**Gemini adjudication:** `GEMINI_S2_SYNTHETIC_SOURCE_CONTRACT_ACCEPTED_DESIGN_ONLY_WITH_F01_F04_ERRATA__SOURCE_MACHINE_MATRIX_NOT_FULLY_ACCEPTED__NOT_READER_SECURITY_ACCEPTED`. No new repeat G2/P2 locator repair campaign. No automatic broad fix task: the Controller errata suffice to preserve truth while designing the next finite source gate. CI remains flagged RED due inherited H40.

## 3. Sol — science design accepted as executed synthetic oracle only

Reference artifacts: [Sol PIT/Funding/Mark test receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/e6bcaf62a69cde32149db3cd4997f7f2dad526ef/evidence/v0.6/b_line/p2_s2_pit_science_r1/SOL_P2_S2_SCIENCE_EXECUTION_RECEIPT.json), [executed synthetic oracle cases](https://github.com/EXASHXE/btc-quant-agent-public/blob/e6bcaf62a69cde32149db3cd4997f7f2dad526ef/evidence/v0.6/b_line/p2_s2_pit_science_r1/SYNTHETIC_MARK_FUNDING_CLOCK_ORACLE_RESULTS.json), [prospective finite BTC diagnostic method blueprint](https://github.com/EXASHXE/btc-quant-agent-public/blob/e6bcaf62a69cde32149db3cd4997f7f2dad526ef/docs/strategy_research/g2_r3/p2_s2_pit_science_r1/BTC_ONLY_DIAGNOSTIC_VERSUS_ORIGINAL_THREE_ASSET_PREREG_BLUEPRINT.md).

**Verified machine results:** 52 actual deterministic invented scalar/clock PIT-Funding cases, 39 hostile witnesses, 13 metamorphic invariants; 65 assertion **groups** with expected codes (NOT 65 different trades), 69 distinct focused pytest items per Python version. Frozen input hash `a3b53bcf...`, output hash `91ee7fb0...`. No owner path opens, real candles/prices/Funding contents, market API, H39/forward/protected output or trading. S2 exactly **52 cases and 13 metamorphic checks**, not empirical strategy-sample N. Source/rights/real cadence remain UNKNOWN.

**Science accepted**: separate immutable event/close/publish/available/corrected-at/settlement/ACK clocks; genuine continuous 1m Mark identity vs Kline/daily reconstruction; same-source same-close conflicting Mark FAIL; final Funding cashflow cannot be used before proof; sign/reserve/owed terminal fee; temporal amendments R1.1 and prospective R1.2 are not equivalent; 12h hourly STRESS may exceed stop-cap but known proven8h schedule hypothetically feasible; unknown funding cadence is NOT 8h by assumption. Original 8 method IDs unchanged, 3 R4 new proposals not newly frozen, no protected era outcomes. The BTC-only positive portfolio would be 100% BTC vs original <=60% single-asset ceiling, so future BTC-only **new finite non-Alpha diagnostic** must carry distinct method/protocol identity and no original multiaset positive claim.

**Scientific limits:** 2021/2023/2025 March=warmup/April=scored windows are proposed, not effective prereg. Power weeks 13/52/205 are illustrative hypothetical variances, not observed real market results. 52 case synthetic validity does not certify source semantics, variance, actual ROI or any reproducible backtest. The Sol High/effort selection was not observable; no Controller certification of actual model setting.

**Sol adjudication:** `SOL_S2_SYNTHETIC_MARK_FUNDING_PIT_ADMISSION_BLUEPRINT_ACCEPTED_WITH_CLOCK_PROVENANCE_SOURCE_UNKNOWN__NO_ALPHA_PREREG`.

## 4. Joint constraints and next real scientific bottleneck

Joint state: **S1 METADATA ROOT LOCATED** six BTC 1m selected nonprotected monthly files via original executor lstat receipt; **S2 source rights/clock/PIT/safe-reader interface designed only**; **S3 actual independent reader and source/schema audit NOT AUTHORIZED**. There is no proof that BTC Mark data genuinely form an independent continuous 1m source, nor Funding published known-at/corrected-at and settlement, historical instrument filters/fees, source licence, actual body file identity, or ETH/SOL 1m.

**Do not initiate another general synthetic-only design campaign** merely to reach more green tests. Highest information-gain next action is a *new, one-file, finite, independently gated nonprotected Parquet footer/schema inspection* to determine actual Kline schema, after both:
1. Owner explicitly approves this specific limited source-content read under actual source rights; and
2. a separately audited **genuine** descriptor-based no-symlink/non-TOCTOU, attempted-syscall+byte-bounded read interface exists with exact immutable root and file allowlist. Do not import or repair terminated old locator; do not re-use Gemini synthetic walker as production.
   
Recommend first pilot: `research/BTCUSDT/1m/year=2021/month=03/data.parquet` (a **warmup** candidate), **at most 65,544 actual bytes (8-byte trailer + <=65,536-byte footer)**, cap 100 attempted filesystem calls, no actual row-group/page read, no Mark/funding/raw folder access, no old H39/forward/protected or 2026 data. Runtime, memory and output (schema only, no min/max statistics or price-derived column stats) must be separately frozen. If footer declares larger length/cross cap, stop/UNKNOWN; do not increase budget. The original six-month location receipt and sample sizes remain non-Alpha.
  
Future Mark/Funding next decision is a **nonoutcome source manifest exact alias** (not a folder listing or reading mixed-era `funding_events.csv` blindly). Before extra source QA, identify 1m actual Mark type/continuity/PIT/correction; funding actual publication/settlement, effective fee/filter schedule, and one permissible nonprotected file path at a time. Any semantic absence UNKNOWN, never inference from parent dir.
   
**P1 old+new custom engines TERMINATED** (`fd3c13645df9ad2506293b109d3891cf57936208`); Sol R4 conditional science only; no effective P3 prereg, no P4 source/empirical campaign, no TESTNET/LIVE/real funds. A-line and Performance not modified.

**Controller terminal:** `P2_S2_BOUNDED_SYNTHETIC_DESIGN_ADJUDICATED_WITH_GEMINI_ERRATUM__S3_REAL_SOURCE_BODY_READ_DENIED_PENDING_EXPLICIT_NEW_OWNER_AND_CONTROLLER_AUTHORITY`.
