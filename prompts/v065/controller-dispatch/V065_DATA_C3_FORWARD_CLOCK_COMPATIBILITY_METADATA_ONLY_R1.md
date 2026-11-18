# quant v0.6.5 — DATA-C3: historical / forward clock compatibility contract, metadata-first

You are the direct local data engineering implementer in the CURRENT agent session. Execute code/tests/artifacts now; no agent/model restart instructions, no delegated review chain, no Git branches or endless governance writeups.

## Baseline

Repo /root/workspace/project/quant-0.6.5 (v0.6.5, prior HEAD 12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77); inspect live HEAD and dirty status. Respect original Owner R4 documents, P0/P1/P2/P3 and C0/C1/C2 code, including current uncommitted changes. No git reset/stash/clean/checkout/commit/push or touching unrelated modules. Code ownership: NEW scripts/data/catalog/forward_clock.py, scripts/data/catalog/forward_compat.py or similarly bounded new files, tests/data/catalog/test_forward_clock_c3.py, plus minimal strictly necessary compatible C0/C1/C2 catalog query changes. Evidence/output only in NEW /root/workspace/project/crypto-data/lakehouse/c3/ and /tmp. No alterations to c0/c1/c2 receipts.

Data context:
- C0 indexed 2,493 source files / 50 datasets, including safe metadata-only 98 Forward files; historical DATA-C1 built 1,881 full canonical Parquet partitions (~16,205,395 normalized rows) with Binance BTC 2021-2026 and Binance/OKX BTC/ETH Q2/Q3. DATA-C2 compiled source-backed BTC perp+spot aggTrades minute flow, originally 2023-08; latest C2 batch updates may be in progress. Reuse schemas and as-of query APIs.
- Original active Forward BTC microstructure lives ONLY at /root/workspace/project/Quant-agent/data/forward/BTCUSDT/microstructure/. ~97GiB daily SQLite and active btc-quant-microstructure-forward.service; NEVER attach/open/query/copy/vacuum those live SQLite databases, touch -wal/-shm, restart service, read protected outcome labels or modify active captures. Metadata access permitted through already-existing C0 catalog and non-sensitive closed/finalized partition manifest JSONs read-only. Do NOT infer closed merely from dated filename; derive CLOSE_VERIFIED only from authoritative finalization metadata with validated linkage. Current C0 labels 86 PAST_DATED_CLOSED_UNVERIFIED, 1 ACTIVE_WRITER_CANDIDATE, 11 UNPARTITIONED_ACTIVE_UNKNOWN.
- Historical Binance and OKX archived market source event UTC times are not measured receiver first-known PIT. Funding/mark/metrics in C1 and signed flow in C2 cannot be called actual tradable real-time observations simply because their event timestamps match an hourly origin. No historical maker ACK/queue/fill proof.
- Protected H39 from Sep 1 2026, historical H40, A-line, Final, Forward outcome reserve remain. Data inventory and feature-clock contract building are allowed; protected Forward market/trading performance outcomes are NOT.

## Mission: produce a practical, testable, low-memory multi-source clock contract

1. Carefully inspect existing C0 Forward metadata inventory (SQLite catalog only, read-only), the two closed-partition SHA/finalization JSON manifests and public clock policy documents. Do not read payload rows or sqlite metadata through DB connect on Forward path. Before any manifest inspection, verify it is a regular bounded JSON file, no symlink escape, and record its SHA and mtime.
2. Define typed common **clock lineage contract** usable by historical and Forward features:
   - instrument/exchange/product/stream, native event_ts UTC, native source timestamp unit, exchange publish timestamp if actually present, receiver_first_known_at if genuinely observed, local_ingested_at / durable commit timestamp if genuinely recorded, source archive/download timestamp separate.
   - Derived intervals: interval_open, interval_close, last contributing event; availability gate is the conservative *latest required* known timestamp, not just event_ts. Missing receiver clock remains UNKNOWN, never synthesize event+constant delays.
   - Causality quality classes ARCHIVE_EVENT_ONLY, RECEIVER_OBSERVED, FORWARD_CLOSED_MANIFEST_ONLY, UNKNOWN or stricter evidence-tagged design. Events with unknown receiver PIT may appear in historical descriptive feature research but not under a false VERIFIED_LIVE_PIT claim.
   - Source provenance, SHA pins, UTC vs OKX UTC+8 archive filenames, gap/dedup flags, documented timing precision.
3. Implement metadata-only Forward catalog compatibility view that joins verified closed-manifest identities with existing C0 Forward metadata by path/date/hash WITHOUT opening any Forward database. Emit a deterministic matrix of partition identity, claimed/verified closed state, first-known receiver-clock *availability of proof*, corresponding C1/C2 coverage by market/family and exact UTC overlap, eligible later read access state (DEFAULT_DENY), and documented unknowns. Do not falsely mark all 2026 Sep–Oct Forward daily files as closed or admitted; do not open even closed Forward DB payloads this task.
4. Add a reusable causal-as-of interoperability library: given HISTORY sourced normalized Parquet and optional **synthetic-only** Forward fixture records with genuinely defined receiver_first_known, enforce HH:01 origin / HH:00 cutoff, OHLC completed bars pre-cutoff, 5m OI sample 5–10min prior with 4h predecessor, flow 1m/5m/1h fully closed at cutoff, historical previous funding settlements; require known first-known when asked for true receiver-PIT-compatible evaluation; uncertain availability should be NO_ACTION/UNKNOWN, not future peek. Parameterized validation for missing known-at, post-origin ingest, off-grid, duplicate source clock, mixed seconds/ms/us, watermark stale and source-gap overlap. Use C1/C2 read-only bounded actual history for examples, but no historical future-return labels.
5. Deliver one SMALL synthetic fixture demonstration with mocked Forward event records (explicitly TEST_ONLY_SYNTHETIC, not originals), plus a historical feature-only BTC example from C1/C2 that demonstrates UNKNOWN receiver PIT. Build two comparison modes: DESCRIPTIVE_EVENT_TIME and RECEIVER_PIT_REQUIRED; the latter must deny archive-only feature evidence for true PIT. If existing C2 lacks 2026 overlapping flow months, show its accurate available window, not fake 2026 crossovers. Instrument/family mismatch must block join.
6. Provide C3 full artifact bundle in new lakehouse/c3:
    forward_metadata_matrix.json/csv;
    clock_contract_schema.json;
    historical_vs_forward_coverage.json;
    receiver_pit_gap_report.json;
    demo_asof_report.json;
    source_manifest_receipt.json with input JSON SHA and no Forward DB opens;
    tests_receipt.json and concise README with explicit next-step limited closed-partition authorization option.
   Non-sensitive metadata path only. No copying massive DBs. No starting historical return backtests or P3.materialize.
7. Focused pytest only for new clock and catalog-related tests, including:
    event ts != receiver first-known, arrival after cutoff, UTC day offsets, archive filename misparse, null receiver PIT, 4h OI predecessor, ambiguous closed metadata/manifest mismatch, incomplete funding, source hash mutated, resource cap and original source immutability. Tests must assert zero Forward SQLite opens and zero historical real outcome labels.
8. Resource: host WSL has 1.9GiB physical RAM and 5GiB swap, plus actively collecting Forward. Keep peak RSS modest and no heavy raw ZIP decompression here; if DATA-C2 ongoing ingestion is in flight, do not compete for memory-intensive tasks.

## Terminal state

DATA_C3_CLOCK_CONTRACT_READY if metadata-only Forward inventory, synthetic PIT gates, historical integration demo, tests and receipts actually produced, with genuine unresolved receiver/rights evidence explicitly marked unknown.
DATA_C3_PARTIAL or DATA_C3_BLOCKED with precise reproducer if lacking required non-sensitive manifest or schema.

This C3 delivers interoperability and known-at semantics. It is NOT actual Forward source admission and NOT live trading or historical strategy Alpha approval. Maintain P3_ACCESS_SCOPE_HOLD / SOURCE_NOT_ADMITTED / PIT_UNKNOWN / NO_ALPHA_ESTABLISHED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE.