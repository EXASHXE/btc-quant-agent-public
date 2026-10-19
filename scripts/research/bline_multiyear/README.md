# BLINE R1

Run from repository root. Final output directories must be new children of
`/root/workspace/project/crypto-data/lakehouse/research-bline-r1`.

```bash
python3 -m scripts.research.bline_multiyear.pipeline preregister --output-dir /root/workspace/project/crypto-data/lakehouse/research-bline-r1/preregister
python3 -m scripts.research.bline_multiyear.pipeline feature-coverage --output-dir /root/workspace/project/crypto-data/lakehouse/research-bline-r1/features-final
python3 -m scripts.research.bline_multiyear.pipeline synthetic-p1 --output-dir /root/workspace/project/crypto-data/lakehouse/research-bline-r1/synthetic
python3 -m scripts.research.bline_multiyear.pipeline evaluate-authorized --output-dir /root/workspace/project/crypto-data/lakehouse/research-bline-r1/gate
PYTHONPATH=src:. python3 -m pytest -q tests/research/bline_multiyear tests/research/strategy_eval tests/data/catalog/test_forward_clock_c3.py
```

`feature-coverage` accepts month-aligned UTC `--start`/`--end` and `--lake-root`.
It consumes the existing C1/C2 query engines and SHA-pinned materialization
receipts. It does not open original ZIPs, Forward SQLite or calculate forward
returns. Known H40 and dates from H39 onward receive metadata coverage only;
unresolved older private exclusions still prevent real outcome evaluation.
Outputs contain all scheduled origins, gaps, native source IDs, a separate exact
SHA lineage manifest, examples, monthly asset/venue eligibility and integrity.
Original source immutability is checked by file signatures and existing receipt
SHA lineage; consumed canonical partitions are independently rehashed.

Ten baseline controls are declared in `contracts.X_NAMES`. C1 has no native
taker-buy field, so the baseline uses observed prices, volatility, volume and
range. It never invents taker imbalance or historical OI. Basis is incremental
Z. Native C2 signed flow is optional descriptive context only, and is never
imputed from candles. Native premium-index level is retained separately from
the mark/index premium used in the frozen signal. OI is sampled 5–10 minutes
before cutoff with an exact four-hour predecessor. Canonical exclusive bar
ends are strictly before cutoff; completed flow may end at cutoff. Funding is
strictly earlier than cutoff and at most nine hours old. Archive clocks remain
PIT_UNKNOWN and every real feature origin has live action NO_ACTION.
Funding scans filter the settlement event time, not the accrual interval start.
Warmup after H40 is truncated at its boundary; missing history stays unavailable.

Two fixed short-only mechanisms are registered before features are inspected:
joint premium/basis release after a rally, and price/OI contraction with
long-heavy positions. Their price-only controls are evaluated on the same Z
eligible origins. No parameter sweep is implemented. Old failures are mapped
to the existing frozen research ledger; neither candidate is a validated edge.

`synthetic-p1` sends independent synthetic native streams through this same
feature adapter, the P1 normalized-panel parser and frozen evaluator. It also
applies both exact candidate policies with P1 economics. P1's fitted increasing
OI overhang model is an engineering compatibility check, distinct from these
fixed policies. Synthetic figures have no historical investment interpretation.

`evaluate-authorized` without permits exits 2 and writes
`EVAL_BLOCKED_SCOPE_UNRESOLVED`. An authorized call requires `--scope`,
`--allowlist`, `--panel`, `--features`, `--registration`, all preexisting.
The scope must pass existing P3 Owner v2 validation and private attestations;
the P3 panel must already have a derived P1 allowlist bound to that scope.
The original Owner document must additionally contain `bline_r1_binding` with
`task=V065-BLINE-R1`, `decision=AUTHORIZE_FIXED_CANDIDATE_EVALUATION`,
`feature_panel_path`, `feature_panel_sha256`, `registration_sha256` matching
the actual frozen files. This is a binding contract, not an authorization
template or proof of a human signer's identity. The program never creates an
Owner decision or a real allowlist. Missing attestations, bindings or protected
date overlap fail before the real outcome parser. P3's existing two-phase
materialization remains the source of any future real outcome panel.

All results retain SOURCE_NOT_ADMITTED, PIT_UNKNOWN, NO_ALPHA_ESTABLISHED,
G2_ALPHA_NO_GO, G4_TESTNET_NO_GO, LIVE_NO_GO and REAL_FUNDS_WRITE_NONE.

The delivered artifact index uses `features-release/`, `synthetic-release/`,
`preregister/`, `authorization/`, and `completion-final/` under the output root.
Earlier feature/summary directories are superseded development runs.
