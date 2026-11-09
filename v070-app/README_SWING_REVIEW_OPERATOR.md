# Quant manual swing review V2

This is an offline tested release candidate for Controller 0-C review. It has not made a genuine market request. Applicable South Korea operator public-REST use and one-day caching eligibility remain UNVERIFIED. Do not run a real scan until that evidence and a separate bounded scan instruction exist.

V1 remains the default. STRICT_RESEARCH is unchanged. V2 is opt-in and requires a fresh output directory; existing V1 episodes cannot migrate. V2 retains `J_PUBLIC_MARKET_ADVISORY_V1`; local fabricated TLS fixtures retain `J_LOCAL_HTTP_QA_V1`. Neither is Strict Source or economic evidence.

A review is permitted at least 120 seconds after the latest completed 4H exclusive close, up to a configured ceiling of 5–120 minutes after that same close (default 120). The entire venue-time uncertainty interval must fit. The ceiling does not slide with receipt time. A missed horizon returns SOURCE_BLOCKED. No waiter, polling, or automatic retry exists. The window is permission to re-evaluate, not a claim that a setup survives.

Two new HTTPS venue-time samples bracket three current-cycle trade-price 4H observations. Every observation must be no more than 30 seconds old at actual review, using monotonic timing and exchange-time bounds. This is acquisition freshness; the endpoint provides no last-trade or publication timestamp, and these are not independently qualified UTC probes. Current partial OHLC is not a completed candle and never enters S1 indicators. It is used only to reject a price outside the frozen entry region, a post-close structural-pivot/stop violation, or an already reached first target. The full unchanged S1 calculations and after-cost geometry must also pass. No synthetic fallback exists.

Actual local wall/monotonic review timestamps and venue UTC bounds are frozen. A review at 30 minutes is issued at its actual review time, never at candle close. Existing plans are immutable. Repeating a review for the same cycle returns the frozen decision after current source/window admission; it does not create a later entry or rewrite history. A later manual review also checks the frozen plan against fresh current observations. A new no-chase/invalidation appends lifecycle and re-review records; a terminal episode cannot reactivate if price returns. Its original decision remains byte-for-byte unchanged. Actual re-review bounds are displayed separately. A displayed frozen card is not a fresh recommendation. Check current source and window status.

V2 requests only mandatory 80x1D and 100x4H bars per symbol. Optional 1H is absent in this release, so positive S1 normally returns WATCH without hourly confirmation, not ARMED by default. Normal acquisition is 14 requests/17 weight; one existing clock reconciliation is 22 requests/28 weight. The unchanged ceilings are 24 requests, weight 40 and 120 seconds. Existing candle revision, gap, access denial, clock hold, exclusion and TLS gates remain active. No account, order or private endpoint is enabled.

## Offline installation and verification

Run from this extracted release directory on supported Linux x86_64/Python 3.13:

```bash
python3 -m venv /tmp/quant-l-env
/tmp/quant-l-env/bin/python -m pip install --no-index --find-links release/wheelhouse --require-hashes -r release/toolchain-lock.txt
/tmp/quant-l-env/bin/python -m pip check
/tmp/quant-l-env/bin/quant live doctor --review-policy J_SWING_MANUAL_REVIEW_V2
python3 tools/verify_release.py
```

The doctor makes zero requests. Without an independently verified access record it reports the access blocker even when V2 is selected. Native Windows and other Python/CPU combinations are not qualified by this Linux build.

## Only after genuine eligibility and a separate scan instruction

Use an ordinary operator directory outside all accepted/project research workspaces. The existing path guard rejects Program L as a runtime output path. Retain the original J access schema and original policy hash; provide actual independently applicable eligibility/cache evidence, not fabricated reviewers. V2's immutable product policy and configured window are separately recorded in the new output journal.

```bash
quant live doctor --access /tmp/quant-operator/operator/access.json --review-policy J_SWING_MANUAL_REVIEW_V2
quant live scan --access /tmp/quant-operator/operator/access.json --output /tmp/quant-operator/work/swing-v2 --review-policy J_SWING_MANUAL_REVIEW_V2 --review-window-minutes 120 --grace-seconds 120 --holding-hours 24
quant live status --output /tmp/quant-operator/work/swing-v2
quant live opportunities --output /tmp/quant-operator/work/swing-v2
quant live episodes --output /tmp/quant-operator/work/swing-v2
quant live dashboard --output /tmp/quant-operator/work/swing-v2
quant live evaluate --output /tmp/quant-operator/work/swing-v2 --report-output /tmp/quant-operator/work/C-review
```

Status/opportunities/episodes/dashboard/evaluate make no exchange requests. A later `observe` invocation does make a new bounded acquisition and needs separate authority. It retains J's full completed 1H forward-observation path (12 requests normally, 23 after one reconciliation). Its snapshot is observation-only and cannot create new V2 candidates; a fresh V2 scan with current-price revalidation is required. No later prices were invented in this release. Without completed hourly forward coverage, Shadow outcomes remain insufficient/unknown. Frozen C continues rejecting this evidence class as SOURCE_CLASS_INVALID and reports INSUFFICIENT_SUPPORT; no scientific protocol or source label is changed.

The exclusion interval remains `[1769904000000,1785542400000)` / `[2026-02-01T00:00:00Z,2026-08-01T00:00:00Z)`. Every bounded warmup and current-observation request is checked for intersection before GET. No protected historical payload is read. Operational data must not be used for PRIMARY or OOS claims.

## Rebuild and local QA

```bash
/tmp/quant-l-env/bin/python -B tools/build_swing_review.py
PYTHONPATH=. /tmp/quant-l-env/bin/python -B tools/package_swing_review.py
/tmp/quant-l-env/bin/python -B tools/run_review_tests.py
/tmp/quant-l-env/bin/python -B tools/demonstrate_swing_review.py
```

The test runner uses four disjoint suites to retain every path guard: C CLI fixtures run inside their working directory; MVP and D-to-C tests run in ordinary temporary working directories with confined outputs; public runtime tests use ordinary external temporary outputs. No evaluator or runtime path protection is changed. Offline socket QA requires permission to bind loopback ports. It uses fabricated CA keys in isolated temporary directories, never genuine Owner/auditor identities. The demonstration refuses an existing artifact directory. Inspect bundled `artifacts/SYNTHETIC_OFFLINE_QA/*/dashboard/latest.html`, SQLite, raw fabricated responses, CLI snapshots and Program C gate reports. For CLI replay, copy a demonstration store to a fresh ordinary `/tmp` operator path; do not point application runtime commands into this Program L evidence workspace. Synthetic clock domains intentionally cannot qualify real current source time.

All cards are hypothetical market-side observations, ACCOUNT_UNKNOWN/ACCOUNT_VETO. Planned R is not a probability, fill or realized profit. S1 only; S2/S3 remain RESEARCH_ONLY_DISABLED.
