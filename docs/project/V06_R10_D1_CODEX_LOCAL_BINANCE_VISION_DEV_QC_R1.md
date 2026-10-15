# R10-D1 — Local Binance Vision EXPOSED_DEV acquisition and deterministic QC R1

**Terminal: `R10_D1_LOCAL_DEV_QC_PARTIAL_STOP`.** Actual bounded acquisition and all publisher integrity checks succeeded. Required trade 1m and optional mark-price 1m archives passed deterministic QC. Optional metrics have incomplete fields and unresolved label semantics; they are not admitted for research features. No strategy smoke, scoring, source admission, or promotion occurred.

Execution observed **2026-10-15 UTC / 2026-10-16 UTC+08**. One local Codex author; no child agents or concurrent authors. Owner explicitly authorized a new isolated workspace, then corrected an unavailable source checkout and expressly authorized an independent public clone. Earlier environment/authority stops were prerequisites, not source-quality evidence. No existing private workspace or protected dataset was inspected. The authorized workspace was absent, ancestors were not symlinks, available disk exceeded 776 GB, and the new checkout was clean before branch creation. Real source data and task implementation outputs were confined to the authorized isolated workspace. Host network access used the existing configured proxy; no restriction bypass, exchange credentials, account, or finance operations.

## Frozen identity and code base

| Identity | Verified result |
| --- | --- |
| Public repository | `https://github.com/EXASHXE/btc-quant-agent-public.git` |
| Clone source branch | `docs/v06-r10-d1-controller-local-agent-first-dispatch-r1` |
| Dispatch / initial detached HEAD / author direct parent | `4d83123243db8cf5ac4fd7b1c00608cb149f7bdc` |
| Dispatch direct parent / R10-D0 author | `980a4b6f79de5ad6dbff8d8b674ce3ca2d056c4b` |
| Full R10-D1 prompt blob | `0e78a8a91205c7c8d531f7a4b101612dcdd83290` |
| Immutable R10-D0 report blob | `14b993d63195b7970a4b1326ffe03b67212a0a47` |
| R10-M0 commit / report blob | `53e0becd3ba47e383b92d399d0b0f92989e23ada` / `b19c01d5103f84642a3af55b544034b9b96fb3d7` |
| R10-L4 commit / report blob | `285149095fc0d9a47ab86248d42fb609555a767d` / `8dfa7c93d2d6ad393df587c8eac7a7948afa14b0` |
| Isolated author branch | `feature/v06-r10-d1-local-binance-vision-dev-qc-r1` |

The full dispatch prompt was read and its Git blob independently hashed before implementation. The frozen public code tree supports the standalone stdlib tool and the existing quality commands; no alternative code branch was merged. R10-D0 remains immutable and still means **zero actual downloads/QC/tests for that earlier task**. Final author commit, its parent, the three resulting blobs, patch digest, and hosted CI receipt are returned with publication; embedding a commit's own hash in its content is not possible.

The only tracked additions are:

- `scripts/research/r10_d1/vision_qc.py`
- `tests/research/r10_d1/test_vision_qc.py`
- `docs/project/V06_R10_D1_CODEX_LOCAL_BINANCE_VISION_DEV_QC_R1.md`

Raw ZIPs and checksum copies remain outside Git in workspace `data/`; documentation snapshots and synthetic temporary fixtures stay in workspace `tmp/`; local aggregate receipts and test logs stay in workspace `reports/`. No raw rows, raw archives, private machine paths, credentials, performance outputs, or proprietary features are included here. No existing original-repository files or metadata were changed by this independent-clone route.

## Rights and source access check before acquisition

Current official publisher `master` resolved to **`f446ce3812bd4e5521f21faecd4ae3c6460e49fc`**. The fetched current [Dataset Terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md) matched frozen blob **`87d04e216f62c86a2c797fbb7637404d6d602687`**, version 1.0, 2026-08-26. No newer dataset prohibition was observed at that check. Section 4.1 covers the owner's declared personal noncommercial nonproduction historical research; live execution and commercial uses remain restricted. Redistribution attribution/share-alike obligations and third-party rights remain applicable. Dataset-derived aggregate evidence here is attributed to Binance Vision and offered under **CC BY-NC-SA 4.0** to the extent those obligations apply; no sponsorship is claimed.

The linked [general terms page](https://www.binance.com/en/about-legal/terms) initially returned an empty shell via the local HTTP client. Its official embedded [current PDF](https://bin.bnbstatic.com/static/cms/cg08ou2ak0tn7mcplvfg/file/bf4879710c904b991848972ec4818ba2cf9e4ce314c09adae84fa2750d3477f7.pdf) was then read through the browser: effective 2026-07-21, eligibility and local-law restrictions remain, and section 25.5 disallows access-restriction circumvention. No owner-specific jurisdiction/entity entitlement is inferred from timezone, proxy, or technical reachability. This check is conditional documentation plus owner purpose/authority, not legal clearance for every jurisdiction or future use. No source endpoint denied access in the actual bounded acquisition.

The [official frozen README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md) describes paired SHA-256 checksums, retrospective publication, and possible archive replacement. A checksum authenticates consistency with the currently published object, not an immutable original 2022 vintage or original receiver timing.

## Actual acquisition receipt

Provider **`https://data.binance.vision` only**; instrument **BTCUSDT USDⓈ-M**, `futures/um/daily`; archive dates **2022-09-15 through 2022-09-21 UTC**, all seven EXPOSED_DEV dates. No source date, family, symbol, venue or origin was widened. Official documentation and repository identity requests are not a second market-data source.

- **21 ZIP GETs + 21 paired CHECKSUM GETs; 21/21 SHA-256 verified.** Every exact object existed; no missing file dates. Each request succeeded on its first attempt; no retries or redirects occurred.
- ZIP bytes **758,218 / 104,857,600 cap**; expanded CSV bytes **2,343,412 / 314,572,800 cap**. Checksum texts total **1,967 bytes**; ZIP plus checksum transport bytes **760,185**, also below 100 MiB. Expanded files were streamed from ZIPs, not separately retained as raw CSVs.
- Checksum/ZIP fetch completion window **2026-10-15T17:30:04.394269+00:00 through 2026-10-15T17:30:37.432121+00:00**. These current fetch observations are separate from the 2022 historical labels. HTTP ETag, Last-Modified, exact URI, completion time and attempt counts are retained in the local acquisition receipt; neither server header is historical first publication.
- Spend **USD 0**. No purchase, paid dependency, account, trial, exchange REST/WS, funding/open-interest invented path, or alternative provider.

| Family | ZIP files | Compressed bytes | Expanded bytes | Rows | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `klines/1m` | 7 | 434,590 | 1,156,127 | 10,080 | PASS: all 1,440/day, unique ordered 1m grid |
| `markPriceKlines/1m` | 7 | 255,851 | 989,628 | 10,080 | PASS: all 1,440/day, unique ordered 1m grid |
| `metrics` | 7 | 67,777 | 197,657 | 2,016 | PARTIAL: 288 labels/day; two fields absent; label contract unresolved |

Each ZIP was checksum-verified before parsing. The tool rejects noncanonical host/date/family/symbol URLs, query/port changes, redirects, exhausted object/byte caps, unsafe member names/symlinks, excess inflation ratios, encrypted/unsupported members, invalid UTF-8/CSV, excessive rows and invalid numeric/time types. It reads no arbitrary source directory listing and performs no archive extraction to filesystem paths. HTTP 403 and other nontransient access failures stop; transient attempts are limited to initial request plus two retries, counting discarded partial ZIP bytes against the compressed budget.

## Deterministic QC, schema and units

Trade and mark-price files share the observed 12-column header:

`open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore`

Timestamps and trade count are integer fields; prices and volume-like fields are finite nonnegative decimal fields, with positive OHLC and consistent high/low ordering. `close_time = open_time + 59,999 ms` passed for all 20,160 bars. Trade prices are USDT per BTC, base volume BTC and quote volume USDT for the USD-M BTCUSDT contract; taker columns follow those base/quote units. Mark OHLC is a mark-price reference; volume/count-shaped placeholder fields are not interpreted as executable trades. `ignore` has no economic use. No schema drift was observed across the seven days within either family.

Both 1m families have **zero missing minutes, duplicates, malformed rows or out-of-day timestamps**. Open labels span **2022-09-15T00:00:00Z through 2022-09-21T23:59:00Z**; the final validated bar close is **2022-09-21T23:59:59.999Z**. No fill, interpolation, deduplication, resampling or feature calculation was used.

Metrics schema was stable across all seven files:

`create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio`

`create_time` is a UTC-parsed second-resolution date-time label; `symbol` is checked as BTCUSDT. OI quantity/value fields are provider aggregate decimals: native quantity/value definitions and contract conversion require their separate official economic contract before downstream use. BTC quantity and USDT notional are interpretations, not independently established by this CSV header alone. Ratios are dimensionless; two top-trader columns have no usable numeric type in this slice because every value is empty. No missing value was coerced to zero.

**Actual metrics findings, identical on each of the seven dates:** 288 timestamped rows; labels **00:00 through 23:55** at 5m spacing; zero duplicate timestamps, zero internal 5m grid holes, and no cross-day duplicate labels. `count_toptrader_long_short_ratio` and `sum_toptrader_long_short_ratio` are each empty on **288/288 rows/day**, hence **2,016 missing values per column**. The other numeric fields passed finite/nonnegative type checks; no price/ratio values are published. All 2,016 rows are incomplete under the full eight-column metric contract.

The predeclared candidate end-labelled daily grid **00:05 through next-day 00:00** therefore has one missing boundary and one unexpected boundary per day: seven each. These are **contract alignment discrepancies**, not evidence of seven lost interior observations. The observed start-grid pattern does not prove that economic contents were available at the labelled start. The tool reports `SHIFTED_START_VS_END_LABEL` and preserves the ambiguity rather than silently translating or accepting labels.

## Stock, flow and causal timing limits

OI quantity/value is classified as **stock snapshot**. Taker buy/sell volume ratio is classified as **interval flow**. `create_time`, true observation-window close, original official publication and original receiver-first-known are distinct clocks. The last three are **UNKNOWN**; archive bytes and current fetch time supply no durable original receiver ACK.

Predeclared timing diagnostics are **assumed observation-period end +5m / +10m / +15m**, never selected by PnL. Both label hypotheses remain explicit:

- End-label hypothesis: stock snapshot at `T`; flow `[T−5m,T)`; assumed close `T`.
- Start-label hypothesis: stock snapshot at `T+5m`; flow `[T,T+5m)`; assumed close `T+5m`.

The local receipt computes all three proxies under both hypotheses. Its conservative envelope uses the later assumed close `T+5m`: earliest source label 2022-09-15 00:00 yields hypothetical availability 00:10 / 00:15 / 00:20 UTC; latest label 2022-09-21 23:55 yields 2022-09-22 00:05 / 00:10 / 00:15 UTC. Those latter dates are derived timing bounds, not additional source acquisition. These are strictly later than each assumed period end **conditional on the hypothesis**, not proofs of actual publication or receiver availability; no proxy was applied to a strategy.

[Issue #491](https://github.com/binance/binance-public-data/issues/491) contains a reporter's alleged 2026-06-25 label change. This fixed 2022 slice predates that allegation. Its observed start-grid labels neither reproduce that transition nor establish earlier content timing. The issue is not a publisher adjudication, and no source values or dates from its reproduction were acquired. `PIT_UNKNOWN` remains.

## Tests, reproduction and final gates

Runtime **CPython 3.13.13**; acquisition/QC and synthetic unittest tooling use **stdlib only**, with no added dependencies. Installed verification versions: pytest 8.4.2, ruff 0.16.9, mypy 1.20.2, numpy 2.4.6, pyarrow 23.0.1, websockets 16.1.1, FastAPI 0.141.1, uvicorn 0.52.4. These record the actual environment, not a new repository dependency lock. Tooling remains Python >=3.11 compatible and repository configuration has no host-specific path change; native Windows behavior was not executed.

**24/24 synthetic unittest cases and 24/24 task pytest cases passed on the stable implementation.** Required negatives were actually executed: wrong publisher digest, truncated ZIP despite a matching digest, traversal member, duplicate 1m bar, missing 5m interval, stock/flow mismatch, shifted label, and source host/date/family/budget refusal. Additional tests cover checksum filename binding, expansion ratio, UTF-8, schema drift/nonfinite or missing fields, extreme timestamps, blank CSV, redirects, bounded retries, and nonretried access denial. Fixtures are entirely synthetic; no source rows are embedded.

The original acquisition receipt is retained verbatim. Its initial metric parser conflated incomplete numeric rows with missing timestamps. Aggregate-only inspection established empty fields; the parser was corrected and a regression test added. Final local re-QC separates row/field quality from timestamp continuity. Repeated offline verification of the same 21 files produced **`OFFLINE_RECEIPT_IDENTICAL`** with zero network requests and exit **2** for the intentional partial-stop result. An early generic gate invocation resolved a pre-existing host editable installation outside the isolated checkout; those results were discarded. All authoritative project checks explicitly bind `PYTHONPATH=src` to this checkout, verified before execution.

Local receipt hashes (metadata only; files stay outside Git):

- `acquisition.json` SHA-256: `027a5776c1ea225048cc13103db093ddefb1e93b7f68e02f86210f102a0d44b0`.
- `offline-qc.json` SHA-256: `0e79e8932da2a8b3f0cebc9dad0e6fd73e7f1208228a2e76d6d8e9e13302bcd3`.

From the published author commit in a newly owner-authorized isolated workspace with `repo/`, empty `data/`, `tmp/`, and `reports/`, fetch and review the current official terms into `tmp/official-terms-current.md`, verify the frozen identities above, then run from `repo/`:

```bash
# task_root is the owner-selected workspace containing this repo; do not reuse private data.
curl -fSs --max-time 30 --max-redirs 0 https://raw.githubusercontent.com/binance/binance-public-data/master/TERMS_AND_CONDITIONS.md -o "$task_root/tmp/official-terms-current.md"
export TMPDIR="$task_root/tmp"
export PYTHONPATH=src
python -m unittest discover -s tests/research/r10_d1 -v
pytest -q tests/research/r10_d1
ruff check scripts/research/r10_d1 tests/research/r10_d1
python scripts/research/r10_d1/vision_qc.py acquire --workspace "$task_root" --owner-authorized
# acquire/verify intentionally exit 2 for this source's PARTIAL_STOP, retaining the receipt.
python scripts/research/r10_d1/vision_qc.py verify --workspace "$task_root" --owner-authorized
python scripts/research/r10_d1/vision_qc.py verify --workspace "$task_root" --owner-authorized
# Second verify prints OFFLINE_RECEIPT_IDENTICAL; it does not acquire again.
ruff check .
mypy
pytest -q
python -m compileall -q src skill-template/scripts
```

Acquisition refuses nonempty `data/` and existing acquisition receipts; verification never downloads. Changed terms require a fresh rights review. Confirm the published author commit's direct parent is the frozen dispatch and compare the three blobs with the final publication receipt; do not rely on a moving branch alone. No task runner changes project CI or any H41 file to force a pass.

| Final local check | Actual result |
| --- | --- |
| Synthetic unittest | 24 passed, 0 failed |
| Task pytest | 24 passed in 0.36s |
| Stable full repository pytest | 1213 passed, 9 warnings in 169.23s (0:02:49) |
| Task-only ruff | PASS |
| Full repository ruff | FAIL, exit 1: 6 pre-existing findings in unchanged H41 synthetic evidence scripts |
| `mypy` | PASS, exit 0 |
| Repository `compileall` command | PASS, exit 0 |
| Repeat offline source QC | Identical receipt; 21 checksums reverified; intentional PARTIAL_STOP exit 2 |
| Hosted GitHub Actions | Not yet observable before this report's commit/push; actual run status/URL returned separately in the final publication receipt |

The full lint failure is confined to four unused-import findings and two multiple-statements-on-one-line findings under `evidence/v0.5/h41/h41_synthetic_pit_validation_r1/`. That tree, `src/`, `pyproject.toml` and `.github/` have zero diff from the dispatch. No unrelated lint or CI repair was attempted. Full pytest warnings are retained in local logs, not suppressed.

`SMOKE_SKIPPED_INPUT_INCOMPLETE`: no full frozen strategy-input/accounting contract, executable BBO sizes/latencies, funding-account membership, maker ACK/fills or full costs. No strategy files, parameter grids, signals, returns or profitability ranking were needed. Archive integrity and limited developmental bar usability were established; historical receiver PIT, executable fills, funding membership, utility and after-cost Alpha were not.

## Official object identity and verified digests

These are filenames, bytes, checksums and fetch observations only, never data rows. All checksums use SHA-256 and matched their paired exact ZIP filename before QC.

| Family | UTC archive date | Official identity | ZIP bytes | Expanded bytes | Verified SHA-256 | ZIP fetched-at UTC |
| --- | --- | --- | ---: | ---: | --- | --- |
| klines | 2022-09-15 | [ZIP](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-15.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-15.zip.CHECKSUM) | 62,421 | 165,550 | `98ae76adbd6be7f6952132460605e307a4b80c4579ed16a963dd5218a93fd30b` | 2026-10-15T17:30:05.313012+00:00 |
| klines | 2022-09-16 | [ZIP](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-16.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-16.zip.CHECKSUM) | 61,502 | 164,660 | `489cb11bbfa9d0b48268b558283de8d428e4f4c6b760393fb61828b74c997049` | 2026-10-15T17:30:06.697685+00:00 |
| klines | 2022-09-17 | [ZIP](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-17.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-17.zip.CHECKSUM) | 60,052 | 163,270 | `89938df6a305df494714bd412c9e22a1bb060f64c15335131a1753110a72d745` | 2026-10-15T17:30:08.057916+00:00 |
| klines | 2022-09-18 | [ZIP](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-18.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-18.zip.CHECKSUM) | 60,844 | 164,036 | `4473c0857e0460561ad51c5c7551ff9b4f6177fa0030715f92bdf9b9adf598cc` | 2026-10-15T17:30:09.546008+00:00 |
| klines | 2022-09-19 | [ZIP](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-19.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-19.zip.CHECKSUM) | 63,419 | 166,453 | `5c1beea60f599a3545fcffe93fb8d9bc34551523834ca211997a49a497cffc08` | 2026-10-15T17:30:10.820087+00:00 |
| klines | 2022-09-20 | [ZIP](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-20.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-20.zip.CHECKSUM) | 62,817 | 165,817 | `dc08063c6981f44160c5e9528f393f375b91fbdc18876d13549781c3a340f61a` | 2026-10-15T17:30:12.240697+00:00 |
| klines | 2022-09-21 | [ZIP](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-21.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2022-09-21.zip.CHECKSUM) | 63,535 | 166,341 | `c105120b2a397870b8af150a8151a676faa841edd56d8f3c7bb868530a8752a8` | 2026-10-15T17:30:14.609909+00:00 |
| markPriceKlines | 2022-09-15 | [ZIP](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-15.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-15.zip.CHECKSUM) | 36,790 | 141,279 | `c95e6d3f283eff53f2e127ccb16af37c416142cec0742e672789feeba98ae3f6` | 2026-10-15T17:30:15.894110+00:00 |
| markPriceKlines | 2022-09-16 | [ZIP](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-16.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-16.zip.CHECKSUM) | 36,487 | 141,432 | `30326553ac305737c151dc12163a74911c96b78c3bd369a2bc4b5f2dda1a4c9b` | 2026-10-15T17:30:17.112295+00:00 |
| markPriceKlines | 2022-09-17 | [ZIP](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-17.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-17.zip.CHECKSUM) | 35,624 | 141,495 | `0b0c846dcf842b4c4ab5857fe855367922632cfdfdceb7f9d619799b895a105f` | 2026-10-15T17:30:18.617817+00:00 |
| markPriceKlines | 2022-09-18 | [ZIP](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-18.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-18.zip.CHECKSUM) | 35,791 | 141,306 | `4cc2f4a94604888fa3c5d080bee524cf64113adb77e124621002bf7b59c50209` | 2026-10-15T17:30:19.936297+00:00 |
| markPriceKlines | 2022-09-19 | [ZIP](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-19.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-19.zip.CHECKSUM) | 37,135 | 141,216 | `7dd4a31884a1c7d8cb30619e9041b6561da0d981374c50d7223705b60cd0ea71` | 2026-10-15T17:30:21.476953+00:00 |
| markPriceKlines | 2022-09-20 | [ZIP](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-20.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-20.zip.CHECKSUM) | 37,125 | 141,369 | `e24d1c1b4e7cf56a40cf7e10fb090a3d2cda93d3d8f027fc1b6239ec911917a0` | 2026-10-15T17:30:23.691617+00:00 |
| markPriceKlines | 2022-09-21 | [ZIP](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-21.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2022-09-21.zip.CHECKSUM) | 36,899 | 141,531 | `492711352241d9b47a22ebad7ee84644198544f207215b968208f542d61f454c` | 2026-10-15T17:30:25.258390+00:00 |
| metrics | 2022-09-15 | [ZIP](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-15.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-15.zip.CHECKSUM) | 10,255 | 29,402 | `06981939c4cffbf72cd2f564b06b5ad68d98e9bfbd091e0e096a24ace139f69e` | 2026-10-15T17:30:26.554447+00:00 |
| metrics | 2022-09-16 | [ZIP](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-16.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-16.zip.CHECKSUM) | 10,352 | 29,408 | `219753b2680b0a82190e376beb2dd858c079b4b9f915dff21434dc1ad6294d59` | 2026-10-15T17:30:27.660872+00:00 |
| metrics | 2022-09-17 | [ZIP](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-17.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-17.zip.CHECKSUM) | 10,271 | 29,408 | `9e8c93160b7b7a25e1ae02555acc9ba654715c8347617e80c3dbda8e5d5216fd` | 2026-10-15T17:30:29.685563+00:00 |
| metrics | 2022-09-18 | [ZIP](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-18.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-18.zip.CHECKSUM) | 10,257 | 29,414 | `6d163234529e8a6bbdeec267f45a4959b06bc464d7041eeffac73c5d6eb31fbf` | 2026-10-15T17:30:33.367240+00:00 |
| metrics | 2022-09-19 | [ZIP](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-19.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-19.zip.CHECKSUM) | 8,909 | 26,675 | `2324b3060a4b2899d5e18c109bc15e03831a873ff95f0732b5085fd3e6c73bb0` | 2026-10-15T17:30:34.826976+00:00 |
| metrics | 2022-09-20 | [ZIP](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-20.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-20.zip.CHECKSUM) | 8,846 | 26,675 | `aa4813e33e79c29a457d9c669ac66683f6a0d5b805c21bea6580dfe59ebc7590` | 2026-10-15T17:30:36.234348+00:00 |
| metrics | 2022-09-21 | [ZIP](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-21.zip) / [SHA256](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2022-09-21.zip.CHECKSUM) | 8,887 | 26,675 | `5942ddd5e291bec9c1e36d868f7f93caef73df8c0d6d794e2e35424bcf7b1e73` | 2026-10-15T17:30:37.432121+00:00 |

## Scope and finite next decision

No scope expansion, automatic successor dispatch, protected-data access, Alpha evaluation or default scoring. Optional metrics were physically available but failed field completeness and remained timing-ambiguous; the terminal is therefore PARTIAL_STOP rather than a blanket PASS. Required 1m success is retained independently. Early synthetic unittest iterations used the operating-system temporary directory; final unittest and pytest runs explicitly set `TMPDIR` to the authorized workspace `tmp/`. Those early fixtures were synthetic, never source data. The initial host editable-install resolution was corrected as recorded above. Earlier workspace and Git-source repair was explicitly authorized by the owner; using an independent public clone instead of a worktree is the recorded implementation-route change.

**Request ChatGPT-1 independent consequential audit** of frozen identity, current rights/access caveats, checksum/budget enforcement, the source field/label findings, and negative-test credibility. Codex authorship and self-verification are not independent audit. The finite next scientific decision is whether only the checksum-verified 1m bars qualify for a separately authorized narrow DEV-QA use, while metrics remain excluded pending an authoritative field/clock contract; Controller must decide after that audit. No broader use is authorized here.

**Preserved gates:** `R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE / SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
