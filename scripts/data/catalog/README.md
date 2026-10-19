# DATA-C0 catalog

Build from immutable local sources:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" python3 -m scripts.data.catalog.pipeline build \
  --output-dir /root/workspace/project/crypto-data/lakehouse
```

The build refreshes `catalog.sqlite`, `dataset_coverage_matrix.csv`/JSON,
`source_overlap_and_gaps.json`, `canonical_schema.json`, typed sample Parquet
partitions, and `asof_features.jsonl`. `run_receipt.json` records hashes, runtime,
RSS, input manifest hashes, and zero real outcome-label reads. Rerunning is
idempotent at the source-file key level; generated samples remain bounded prefixes,
not complete historical lake partitions. Use `--max-rows-per-source` (1–10,000)
to change the bounded sample. The demo defaults to 3,000 rows per chosen file.

Reproducible SQLite coverage query (standard-library only):

```bash
python3 - <<'PY'
import sqlite3
p = '/root/workspace/project/crypto-data/lakehouse/catalog.sqlite'
c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
for row in c.execute("SELECT calendar_month,product,family,physical_rows_sum,reported_gaps_sum "
                     "FROM dataset_coverage WHERE exchange='binance' AND asset='BTC' "
                     "AND calendar_month BETWEEN '2021-01' AND '2026-12' "
                     "ORDER BY calendar_month,product,family"):
    print(row)
PY
```

Parquet sample query:

```bash
python3 - <<'PY'
import json, pathlib, pyarrow.parquet as pq
p = pathlib.Path('/root/workspace/project/crypto-data/lakehouse')
items = json.loads((p/'sample_partitions.json').read_text())
chosen = next(x for x in items if x['table']=='bars' and x['exchange']=='okx' and x['asset']=='BTC')
print(pq.read_table(chosen['partition_path'], columns=['interval_start_utc','close']).slice(0, 3).to_pylist())
PY
```

`asof_features.jsonl` uses fixed HH:01 UTC origins, C=HH:00, bars with exclusive
end strictly before C, Binance OI sampled C−10m..C−5m with an exact 4h predecessor,
and only funding settlements at or before C. It contains feature readiness and
same-minute Binance/OKX spread, **no future settlement or return labels**. Native
exchange time is retained separately from nullable receiver first-known time.
OKX file-day labels are UTC+8; actual epoch times are kept in UTC. The original
2021 BTC spot Parquet has volume but no OHLC and is cataloged as such.

Growth path: C1 streams all verified historical candle, mark, funding and OI
archives into month/day Parquet partitions with independent gap reports; C2
batches old 85GB-class aggTrades with strict per-file budgets and resumable
receipts; C3 compares historical event clocks with **metadata-only** Forward
chronology after closed-partition and receiver-clock policy review. Do not attach
to an active Forward SQLite file. Catalog access never grants P3 outcome-study
permission: `P3_ACCESS_SCOPE_HOLD`, `SOURCE_NOT_ADMITTED`, `PIT_UNKNOWN`,
`NO_ALPHA_ESTABLISHED`, `G2_ALPHA_NO_GO`, `G4_TESTNET_NO_GO`, `LIVE_NO_GO`,
and `REAL_FUNDS_WRITE_NONE` remain in force.
