# R11-D2 — Binance Core Historical Data Foundation Pilot

**Executor:** local Codex High, one isolated session.  
**State:** READY / BOUNDED.  
**Source:** official Binance Vision only. Personal/noncommercial/nonproduction offline research. No API/REST/WS market calls.

## Scope

Instrument: **BTCUSDT and ETHUSDT USDⓈ-M perpetual** only.

Reuse the existing R10-D1 BTCUSDT 2022-09-15..21 receipt where it already exists; do not redownload those exact files merely to duplicate them.

Add one bounded calibration interval **2024-01-01 through 2024-01-31 UTC** and acquire only source families that are actually present and documented:

- 1m Klines;
- 1m Mark Price Klines;
- Funding Rate history/archive;
- historical OI/metrics archive where available;
- raw Trades/aggTrades only if the exact official Vision family is verified and the resulting measured size is acceptable.

The interval is for source/storage engineering and schema validation only. It is not a strategy score, OOS result, or Alpha test.

## Required QC

For every acquired object:

- official URL/key and product identity;
- checksum verification when publisher provides one;
- exact compressed and expanded bytes;
- file/member safety;
- row counts, duplicates and time gaps;
- native timestamp unit and event/label semantics;
- daily/monthly duplicate representation;
- instrument/product contract units;
- funding/OI field units;
- provenance manifest and immutable receipt hash.

For OI/metrics, explicitly distinguish economic period end, publisher label, archive publication and receiver first-known. If first-known cannot be established, set `PIT_UNKNOWN`.

Do not impute missing fields. Do not silently substitute current REST data for historical archive data.

## Capacity behavior

Before download, measure available free space in the authorized workspace. If insufficient, STOP and report the additional GiB required; do not delete or resize anything. The owner may expand storage and rerun.

## Hard boundaries

No protected paths, no H39/H40/H41/Final/Forward/OOS, no model training, no Alpha scoring, no historical outcome selection, no trading, no TESTNET/LIVE, no private credentials.

Publish one reproducible report plus only the minimum deterministic intake/manifest code required by the task. No unrelated refactor.

Terminal: `R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS` or `R11_D2_BINANCE_PILOT_STOP`.