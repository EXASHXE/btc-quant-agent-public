# G2 R1 research report

**Decision: G2_R1_METHOD_OR_SOURCE_BLOCKED.** Twelve long-only spot candidates
were preregistered; zero candidates, trades or historical price outcomes were
empirically evaluated. Economic viability is unknown. There is no shortlist,
NO_GO finding, strategy-quality PASS or fresh independent evidence.

The first method commit, `a46b0537c592f5d90a166aebe94737363f1706c0`, was pushed
and independently queried before implementation/source audit. Its parent is
`d6500140f3141d179181f2360ad815b5bfe9c954`. The implementation is
`4fc923b18330cde8873a93eb5fbb594531b5fcf5`, with that method commit as parent.
Final evidence follows separately to avoid circular commit-SHA references.
The frozen method and design note have not changed.

## Source finding and scientific interpretation

All 12 registered Binance BTC/ETH/SOL monthly spot archive objects for May–August
2026 returned HTTP 200 to HEAD requests. Their Last-Modified timestamps occur
after their source months. No response body or market price was opened. Header
digests identify the metadata responses only: they are not archive or market-data
digests. Official checksums, authentic minute coverage and actual historical online
publication/receipt latency were not established.

The strict frozen rule requires contemporaneous receipt proof for historical signal
inputs. A present-day archive receipt cannot establish that an input was received
before a June/July/August decision. No authorized contemporaneous local fixture
manifest exists for this task. The method forbids substituting hypothetical lag
for that proof. This source gate stops the campaign before outcome replay.
The source is accessible, but its decision-time eligibility is unproven.

This finding does not establish whether the candidate formulas make or lose money.
The preregistration's strict source gate is intentionally stronger than an event-time
reconstruction assuming immediate publication. Such a reconstruction would require
a new Controller-approved campaign and clearly qualified evidence, rather than
changing the already pushed R1 method.

Historical BTC/ETH/SOL remains PRIOR_EXPOSED_OR_DEVELOPMENT. The required Controller
RC1 summary was read and retains its valid hard-FAIL status. RC2 limited engineering
acceptance provides no policy-quality verdict. No protected target archives,
partitions, cache, outcome manifest, runner execution or A-line outcomes were read.
The supplied legacy evaluation-contract link has an extra `docs/` component; its
canonical tracked `reviews/v0.5/tactical-policy/...` document was read instead.

## Implementation, checks and limitations

The sidecar includes typed UTC minute normalization, allowlisted source identities,
source/cache hashes, completed-hour aggregation without interpolation, the twelve
frozen signal configurations, next-minute spot accounting and bounded exits. It
rejects unknown markets, derivative/short inputs, late availability, duplicate bars,
missing minutes, overlapping positions and partition boundary crossings. Ambiguous
stop/target bars resolve to the stop; stop gaps worsen execution and target gaps
receive no favorable extra profit. Costs remain disclosed scenarios, not measured
historical execution. No leverage, grid inventory or funding-income inference exists.

Empirical replay is deliberately denied. The available accounting kernel executes
synthetic unit tests only. Self-declared source digests and arbitrary decision input
identities do not establish original source authenticity or feature linkage. A future
empirical runner must verify those links, constrain the frozen notional/frictions,
and implement complete decision tables, comparative metrics, clustered uncertainty
and ranking before any scientific result. Those tasks were not completed after the
source stop. No synthetic test PnL appears in the exploratory result table.

Final local L1: **43 passed, 0 failed, 0 skipped**; Ruff, compilation and targeted
mypy also passed. The full test-command wall time is recorded in TEST_RECEIPT.json.
Independent read-only review found and checked repairs to zero-range WAIT handling
and decimal-context-dependent stop/volume calculations. Four focused independent
regressions passed. This is engineering evidence for the blocked kernel, not a
valid historical strategy evaluation. No MarketWatch runtime behavior is imported;
its existing APIs were inspected as immutable design references. Shared CI and
G1 code were unchanged. Remote CI status is recorded separately; local checks do
not imply remote CI success or accepted Python 3.12 release certification.

All twelve candidate statuses and eleven benchmark statuses are published without
survivor filtering. Uncomputed metrics/intervals are null, not fictitious zeros.
The frozen Tactical diagnostic needs unavailable derivative/reference-universe
inputs and was not approximated. Grid and derivative funding tests are inapplicable
because neither was registered; deferred empirical checks are explicitly listed.

## Competing explanations and next experiment proposal

There are no empirical observations from which to distinguish signal edge from
long-market exposure, favorable regimes, correlated asset shocks, turnover or
selection bias. Breakouts could fail through churn and false continuation;
pullbacks could enter a deteriorating trend; range reversion could repeatedly buy
falling markets. Fees and spread could exhaust small short-horizon advantages.
Long-only results could not support a claim about short strategies or grids.

Recommended Controller action: L2 source/provenance review, then a separate prospective
R2 decision. Do not authorize protected retry, modify a production policy or promote
G1 execution based on R1. R1 provides no basis for choosing its two best candidates.

A possible **new, separately authorized** experiment would freeze at most two formulas
before observing its new cohort, using 180 consecutive forward UTC days starting only
after Controller dispatch. Require verifiably unexposed BTC/ETH/SOL spot observations
with original event/receipt/available timestamps, authenticated source identities,
measured or conservatively bounded costs and complete 1m outcomes. Use three fixed
60-day partitions, a 24h boundary embargo, no overlapping same-symbol positions,
and no outcome-dependent extension. Require at least 100 trades in each partition,
99.9% minute coverage with 100% feature/trade-window coverage, at least 12 independent
7-day time blocks and no asset contributing over 60% of risk exposure. Failure of
support yields diagnostic-only, without threshold changes or subgroup rescue.

Precommitted prospective nulls would be (1) expected higher-cost net R is <=0 and
(2) incremental matched-exposure net R versus the corresponding naïve long control
is <=0. Use common UTC blocks across assets and fixed-seed 2,000-replicate block
resampling, requiring both one-sided 97.5% lower bounds >0 (two-candidate correction),
pooled stress mean >=+0.05R, stress median >=-0.05R, nonnegative stress means in at
least two partitions and stop-before-target <=0.65. These are proposed thresholds
for Controller review, not newly granted policy PASS criteria. No data collection
or forward experiment is authorized or performed by this R1 report.

Executor profile: SOL_HIGH. Completed: bootstrap/authority verification, immutable
method push, metadata-only audit, bounded synthetic kernel, tests, independent
read-only engineering review and public evidence publication. Not completed:
empirical evaluation, economic ranking, historical PIT proof or independent alpha
validation. Independent Controller scientific and provenance review remains required.

Protected reads=0; exchange writes=0; TESTNET not authorized; real-funds authority
NONE; G1/shared source changes ZERO. Original entry branch, HEAD and dirty/untracked
counts are unchanged.
