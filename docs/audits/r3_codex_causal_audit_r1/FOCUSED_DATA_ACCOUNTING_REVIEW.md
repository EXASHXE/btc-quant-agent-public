# Focused Python data and simulated accounting review

**All three reviewed areas require correction at the frozen baseline.**
Twenty deterministic probes ran locally under Python 3.12.3. Thirteen reproduce
unsafe behavior; seven verify their stated invariants. All 20 observation tests
pass because they assert the precise frozen behavior, including the defects.
There are no skipped tests or xfails. These results do not establish a green
application engineering gate, strategy profitability or trading readiness.

Baseline: `632d2e37f28b8c3efbd2b818ecdb74783f0df238`.
Baseline parent: `b86843bb11a10e0a3a293d4d918671c6c41d08fa`.
Test implementation commit: `0e5f1b2d3d6682ea69de90e8693d705a5872d655`,
whose parent is the baseline. Audit branch:
`feature/v06-bline-codex-r3-independent-causal-audit-r1`.
B reference: `51cdd4e17503fbd18ad22aaeeaba3580f5efacf8`.
C reference: `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`.

The latest request narrows the earlier audit goal to these accounting and import
questions. Gemini's branch was not changed or reviewed, and was not awaited.
Only audit files were added. No production logic, existing test, CI configuration,
research policy or protected data was edited. All input records are generated
synthetic fixtures. No market, proxy process, account, broker or order endpoint
was contacted. GitHub publication is separate from the offline tests.

## Transaction timestamp findings

**F01 — HIGH: C receives a backdated envelope and admits earlier knowledge.**
R2 `scripts/integration/market_event_bridge_r2/bridge_engine.py:333` and `:335`
set ingress and availability to settlement time. B's corresponding `:307` and
`:309` preserve actual receipt. The ledger itself correctly records receipt in
`scripts/integration/market_event_bridge_r2/funding_adapter.py:163` and `:164`.
Thus a single event exposes inconsistent known-at times across consumers.

| Synthetic settlement T | Actual receipt | B ingress / callback time | C ingress / known-at | C decision validator at receipt−1 |
|---:|---:|---:|---:|---|
| 180000 | 180200 | 180200 | 180000 | admits |
| 180000 | 210000 | 210000 | 180000 | admits |
| 180000 | 10980000 | 10980000 | 180000 | admits |

Each C envelope is accepted by the actual pinned MarketPitPort, with its pinned
synthetic stream and manifest. No preceding C event is needed. This demonstrates
validation admitting earlier knowledge, not a real strategy decision or trade.
`BUG_REPRODUCED=true`; `INVARIANT_PASSED=false` for all three cases.

**F02 — HIGH: correcting the wrapper alone breaks the pinned C contract.**
C `scripts/g1g3_offline_ports_r1/market_pit_port.py:362` requires
`avail_ms == settlement_at`, and `:370` timestamps the translated event at
settlement. The `correct_c_receipt` probe changes only synthetic envelope ingress
and availability to T+200; the real C validator raises `FUNDING_PIT_INVALID`.
The separate implementation team must change both producer and consumer
contracts. Preserve settlement time in the payload, permit receipt at or after
settlement, and use receipt/known-at for event availability and decision gating.
Historical settlement-position valuation must be distinct from later record
discovery; this review does not test a reducer or historical position ledger.

## Reference price and arithmetic findings

**F03 — HIGH: a scalar last Mark cannot establish settlement valuation.**
R2 `bridge_engine.py:162` retains only a float. `:286` selects it without checking
Mark event time, ingress, source digest or route. `:83` resets only the book when
the route changes. `funding_adapter.py:155` constructs a VERIFIED entry from the
price without a Mark witness; its provenance defaults to route epoch 0 and an
empty parent-event digest list.

| Probe | Expected | Actual baseline result |
|---|---|---|
| `mark_stale` | Explicit incomplete valuation | Mark from T−60000 accepted VERIFIED; 1 BTC expense −6 USDT |
| `mark_after_settlement` | Later observed Mark cannot prove settlement Mark | A 90000 price first observed at T+3h accepted; 1 BTC expense −9 USDT |
| `mark_route_switch` | Invalidate price from earlier route/session | Old 60000 Mark reused; bridge epoch 1, entry epoch 0; −6 USDT |

The −9 USDT figure is an actual Decimal ledger calculation on synthetic input.
No settlement-time price was provided in that probe, so the correct realized
cash value is unknown. No assumption about live API fields is required.
Require a finite positive, settlement-relevant price witness carrying its price
time, ingress, source SHA and route/session identity. Preserve Decimal through
valuation. A receipt-time quote may serve a different estimate, but cannot be
silently classified as the historical settlement cash basis.

**F04 — HIGH: non-finite input raises after partial mutation or escapes status handling.**
`funding_adapter.py:145` and `:146` compare positivity without `is_finite()`.
`mark_infinity` inserts a VERIFIED Infinity entry at `:170`; then the real B
schema's strict JSON serializer (`B .../contract.py:18`) raises ValueError.
The journal has one entry while B has zero accounting callbacks and C receives
zero envelopes. This is a local partial state mutation, not a tested WAL
transaction. `mark_nan` raises uncaught Decimal InvalidOperation before journal
insertion. Validate finite numbers before constructing or storing an entry;
return explicit invalid/incomplete status. Validate dispatch input before
committing journal state, or define recoverable publication semantics.

**F05 — MEDIUM: missing Mark has no explicit incomplete status.**
`funding_adapter.py:140` rejects None correctly. However `bridge_engine.py:111`
initializes `status=INGESTED`, and `:349` returns that unchanged. `mark_missing`
returns no entry and dispatches neither consumer, but gives no financial
incompleteness reason. No zero cash result is fabricated in this case.
Return `NO_REALIZED_CASH_BASIS` or another explicit incomplete status/reason.

**F06 — HIGH: equivalent rate formatting defeats settlement deduplication.**
`funding_adapter.py:150` includes the unnormalized rate string in settlement ID.
For the same BTCUSDT interval, 0.0001 followed by 0.00010000 produces two entries,
zero duplicate detections, and a sample sum of −12 USDT instead of −6 USDT.
This demonstrates duplicate ledger valuation, not a live-account charge.
Deduplicate economic identity by symbol and settlement time; normalize rate
representation and reject conflicting revisions explicitly. The identical
record replay does return the same entry and is verified by a separate test.

**F07 — HIGH: missing rate is silently accepted as accurate zero by the ledger API.**
`funding_adapter.py:129` defaults a missing rate to `0.0`. `missing_rate` calls
that API directly and obtains a VERIFIED entry with cash `-0E-8`. The bridge
currently requires the fundingRate key at `bridge_engine.py:285`, so this
witness is a ledger-API defect, not an assertion that this bridge path forwards
a missing-key record. Require critical fields and return incomplete status.

**Verified arithmetic with valid inputs:** BTC quantity × USDT/BTC price × rate
fraction yields USDT, with cash sign negated. At 1.5 BTC and 60000 USDT/BTC,
positive-rate long pays −9; short receives +9; negative-rate long receives +9;
short pays −9. Opposite quantities sum to zero. The 8-decimal HALF_EVEN test
rounds a −0.000000015 adjustment to −0.00000002. These checks are not proof of
arbitrary precision or full account conservation after conversion to B floats.

## Portable imports

**F08 — HIGH: five existing test import preambles inspect absolute development paths.**

| Existing R2 test module | Absolute-path literal line(s) |
|---|---|
| `tests/test_v06_market_event_bridge_r2_c_composite_g1.py` | 22 |
| `tests/test_v06_market_event_bridge_r2_depth_ladder_l2.py` | 13 |
| `tests/test_v06_market_event_bridge_r2_pit_clock_mark_last.py` | 14 |
| `tests/test_v06_market_event_bridge_r2_settled_funding_ledger.py` | 24, 25 |
| `tests/test_v06_market_event_bridge_r2_stress_and_security.py` | 40, 41 |

`legacy_imports` extracts and executes these actual filesystem import preambles
against a synthetic permission-denying runner. All five raise PermissionError.
It never stats the real development directories. This independently reproduces
the dependency on host path permissions; it does not recreate an entire GitHub
job. The supplied Actions run 38252226915 is user-reported context and was not
fetched or represented as newly verified CI evidence.

A portable architecture can use a configured repository-relative cache or
temporary directory, with explicit full B/C SHAs and file digests. The enclosing
environment must supply those Git objects (or a validated public artifact).
Missing revisions must fail `DEPENDENCY_UNAVAILABLE`, never skip or load an
unrelated copy. This review's harness demonstrates `git show SHA:path` staging
of named blobs, fresh `python -I` workers, then module `__file__`/SHA-256 checks.
The `pinned_import_identity` test actually tampers a staged file and invokes the
same verifier, then supplies a foreign origin; both are rejected. The actual
B adapter and C validator run in the delay and reference-price probes.
No CI pipeline changes are proposed here; the implementation team owns them.

## Reproduce and inspect evidence

```sh
PYTHONDONTWRITEBYTECODE=1 python3.12 -m pytest -q --noconftest tests/test_v06_r3_codex_causal_audit_r1_focused.py --tb=short -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3.12 scripts/audits/r3_codex_causal_audit_r1/review.py
```

Use pytest `-k 'delay_'`, `-k 'correct_c_receipt'`, `-k 'mark_'`,
`-k 'dedupe_equivalent_rate'`, `-k 'missing_rate'` or `-k 'legacy_imports'`
to replay a particular finding. The final recorded run has **20 passed, 0 failed**
observation probes. The report records **13 BUG_REPRODUCED** and
**7 INVARIANT_PASSED**, with actual results, source revisions and file hashes.
The explicit expected-observation assertions detect unexpected drift; exceptions
outside the specific witnessed failure paths fail the probes.

Machine evidence: `evidence/v0.6/b_line/r3_codex_causal_audit_r1/REVIEW_RESULTS.json`.
Its `source_files` covers all 25 staged public Python files with exact SHA and
SHA-256; `harness_files` binds the two executable review files. Its
`harness_commit` is the implementation commit above. The later evidence commit
cannot contain its own commit hash; publication identity is obtained from Git
and reported separately. Replay recomputes core source hashes and case results;
the execution receipt and finding descriptions are publication annotations.
The probes are reproducible offline when the three pinned commits are present;
no source or dependency was unavailable here.

Determinations:

- `FUNDING_TIMESTAMP_CORRECTION_REQUIRED`
- `FUNDING_REFERENCE_PRICE_CORRECTION_REQUIRED`
- `TEST_IMPORTS_REPAIR_REQUIRED`
