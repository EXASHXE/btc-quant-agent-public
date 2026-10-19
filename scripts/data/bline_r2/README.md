# BLINE R2 public archive expansion

This tool writes only a new, isolated `crypto-data/bline-r2-*` root. It does not
change C0/C1/C2/C3, BLINE-R1 code/results, raw originals, services or Forward
databases. It never calculates real forward returns, trades or strategy signals.

From the quant repository root, resume/reproduce the delivered data collection:

```bash
python3 -m scripts.data.bline_r2.pipeline acquire --root /root/workspace/project/crypto-data/bline-r2-20261019 --tier core --direct --workers 4
python3 -m scripts.data.bline_r2.pipeline report --root /root/workspace/project/crypto-data/bline-r2-20261019
PYTHONPATH=src:. python3 -m pytest -q tests/data/bline_r2 tests/data/test_data_acquisition.py tests/data/catalog/test_forward_clock_c3.py
```

`report` creates a new timestamped report directory, never replaces a previous
report. The catalog caches completed SHA-verified objects. Failed partial
downloads can resume; verified original archives are referenced without copying.
`--direct` uses ordinary verified HTTPS after the configured local proxy failed;
it does not rotate proxies, regions, authentication or user agents to evade a
provider restriction. Proxy configuration and system services are never changed.

For a new isolated run with the same reviewed source terms and date window:

```bash
python3 -m scripts.data.bline_r2.pipeline init --root /root/workspace/project/crypto-data/bline-r2-new-run --evidence-dir /root/workspace/project/crypto-data/bline-r2-20261019/evidence
python3 -m scripts.data.bline_r2.pipeline acquire --root /root/workspace/project/crypto-data/bline-r2-new-run --tier pilot --direct
```

Source terms were reviewed at Binance public-data commit
`d571690eb66760763b0bd6e27e8cd35603c7e244`. The initializer checks the content
pins of those snapshots (ignoring terminal newlines). This pins this experiment's
rights evidence; it is not authority for future amended terms, commercial use,
distribution, production trading, or other source families. Recheck applicable
terms before a later collection. `init` captures Owner/R1 file hashes itself;
`--preservation-snapshot` optionally supplies a snapshot taken before execution.

The tiers are `pilot`, `oi`, `monthly`, `core` (OI plus monthly), and `okx`.
Binance daily metrics cover native OI, notional OI, top account and position
ratios, global account ratio and taker ratio. Monthly archives include native
1m perpetual and Spot candles, Mark, Index, Premium and funding events for BTC
and ETH. Actual public availability is tested; a missing CHECKSUM is not
silently treated as an authentic archive or as proof of missing ZIP contents.
Bybit OI bulk-archive retention authority was unresolved in this review and its
hosts were unreachable; no Bybit OI payload was fetched. OKX historical funding,
trades and L2 have a separate personal-use license and separate network checks.
Their data is never relabeled as Binance OI.

Limits: four workers, at most eight request starts per second, HTTP Retry-After,
20-second socket timeout with at most three attempts, 20,000 requests per batch,
64MiB individual archive cap pending a benefit review, 512MiB uncompressed CSV
cap, no on-disk extraction, 2GiB temporary expansion reserve, 256GB additional
storage cap, at least 400GiB free. SHA-256 is checked against Binance's named
publisher sidecar, then full ZIP CRC and schema/clock checks. HTTP ETag and
Last-Modified describe archive vintage; neither proves exchange publication or
receiver knowledge. OKX has local SHA integrity only where no publisher checksum
is available. No provider denial is bypassed.

Native `create_time` is retained verbatim. The reported 2026-06-25 metrics label
change is tracked as an unconfirmed community report and checked against each
retrieved file's actual boundary pattern and SHA/vintage. No blind timestamp
shift repairs history. The feature-readiness diagnostic assumes a conservative
content bounds [label,label+5m], requires the entire range in [cutoff-10m, cutoff-5m] and
an exact 4h native predecessor. Identical native rows can collapse; conflicting
rows sharing a label are excluded. Nonpositive/nonfinite values are unavailable
for the logarithmic state; raw archives remain preserved. Missing position
ratios do not erase valid OI from the separate OI-only coverage count.

Native OI sample-hours, complete 12-sample hours, and OI+position sample coverage
are reported separately by year/venue/exact contract. These are observations in
public archives, not continuous receiver-observed positions. Incremental BTC
origins reuse only frozen R1 X-readiness and apply known H40/H39 exclusions and
warmup boundaries. Unresolved older private dates still prevent real outcome
evaluation. PIT_UNKNOWN, SOURCE_NOT_ADMITTED and every existing NO_GO remain.
