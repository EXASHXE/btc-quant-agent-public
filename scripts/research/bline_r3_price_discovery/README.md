# BLINE R3: native minute-price discovery feasibility

One frozen, feature-only experiment. Native Binance BTCUSDT spot and USD-M
perpetual Last closes must show spot crossing down first, delayed perpetual
crossing, persistent spot displacement and incomplete perpetual catchup, all
strictly before the hourly decision cutoff. No funding, premium, index, Mark,
OI, taker-flow proxy, breakout/retest, returns labels or execution model is used.

## Run from the repository root

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:.
python3 -m scripts.research.bline_r3_price_discovery.pipeline preregister --output-root /root/workspace/project/crypto-data/lakehouse/research-bline-r3-price-discovery
python3 -m scripts.research.bline_r3_price_discovery.pipeline build --output-root /root/workspace/project/crypto-data/lakehouse/research-bline-r3-price-discovery
python3 -m scripts.research.bline_r3_price_discovery.pipeline verify --output-root /root/workspace/project/crypto-data/lakehouse/research-bline-r3-price-discovery
python3 -m pytest -q tests/research/bline_r3_price_discovery/ -p no:cacheprovider --tb=short --basetemp=tests/research/bline_r3_price_discovery/.pytest-tmp
python3 -m ruff check --no-cache scripts/research/bline_r3_price_discovery tests/research/bline_r3_price_discovery
```

`preregister` checks the delivered immutable preflight/input binding and freezes
the same mathematical definition. These input pins and remote authority snapshots
were prepared before candidate features/counts were read. It does not fetch new
data or invent new authority. The task authorizes only the exact output root.
An existing manifest makes `build` run verification only. `verify` rehashes inputs,
code and outputs, recalculates panels, missingness, episodes and decisions in
memory, and compares the results without writing. Do not delete/re-register an
unsuccessful experiment to change thresholds.

The registration records formulas and fixed rationales for 10bp displacement,
5bp lag/drift, first-five-minute leadership, fifteen-minute observation, and
25–75% remaining initial displacement. This is not a claim that these values
are optimal or profitable. The 8h episode rate must be in [0.5,2] per 48 paired
eligible hourly origins, with at least 30 trigger hours, 30 nonoverlap episodes,
12 episode-start weeks, three years, at most 70% of triggers in one year and
80% paired coverage. No search is allowed after seeing counts.

## Contracts and evidence

- The observable is a sequence, not static basis: a tested prefix-order
  counterexample preserves terminal spot/perpetual basis and X but reverses Z.
- Canonical native open is preserved; end=open+1m; all sixteen consecutive
  close endpoints in both markets are strictly before cutoff. No intraminute
  ordering, historical exchange publication or receiver PIT is inferred.
- Read only exact receipt-pinned C1 `bars` month files for Binance BTC in
  2021–2024. Arrow column projection follows the existing canonical scanner
  pattern; it avoids discovering protected-year datasets. Original raw source
  paths recorded in receipts are never opened or stat-ed. A raw SHA in this
  report is a C1 receipt pin, not a fresh raw-file rehash.
- Full canonical file SHA/row counts are verified. Some rows retain legacy
  `SAMPLED_PREFIX` flags despite full-materialization receipts. This is disclosed
  in the source/month report, not silently rewritten or treated as PIT admission.
- Reuse unchanged frozen R1 X readiness and comparator `log_return_4h<=-0.01`.
  Both arms share exactly the same complete native-minute/X mask; all scheduled
  origins, including missing data and NO_ACTION, remain in coverage tables.
- Preserve [2025-02-01,2026-02-01), warmup overlap and 2026-09 onward exclusions.
  Older years are exposed descriptive development only. No protected outcome,
  private account, Forward/Final/OOS or SQLite payload is opened.
- `source_month_coverage.json`, `monthly_counts.csv`, `yearly_counts.csv`, the
  per-origin panel and `episode_tables.json` provide source missingness,
  eligibility, NO_ACTION, actual triggers, nonoverlap episodes and ISO weeks.
- `comparison_with_frozen_priors.json` gives the exact paired price comparator
  and hash-bound R1/R2 density references. Their different dates/source masks
  prevent treating reference differences as incremental economic evidence.
- Nonoverlapping episodes and calendar blocks are counts, not proof of
  statistical independence, power, 4–24h utility or structural price causality.

All source/PIT/cost/utility/Alpha/TESTNET/LIVE/funds holds remain. A failed
feature-feasibility gate ends this candidate; it does not authorize outcome
evaluation or threshold/exit repair.
