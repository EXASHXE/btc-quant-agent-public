# RC2 Parallel Sol Downstream Readiness — Outcome-Blind

Terminal: `RC2_PARALLEL_SOL_DOWNSTREAM_READINESS_COMPLETE`

Prepared from pre-result source and accepted work-package evidence. This report grants no execution, release, or real-money authority.

## Frozen analysis identities

| Identity | Value |
|---|---|
| Tactical candidate | `10be512f2cf4d7eccdc8a9849c925b5f73c568fd` |
| Policy | `TACTICAL_POLICY_R2_B1` |
| Final runner | `d51abdcfa982be132a6fae6c84776f343fae893c` |
| Runner SHA256 | `ab7a5795a1f002f93e5ffff658c4be2dd9708b8b23a11801ec122f32e5f05ebd` |
| Execution dispatch | `ffceccbb1ee28f190d4a8b3340248c753e22d374` |
| Accepted WP-A | `606f286dbb5d7af46776043d1287d9b3e7b1e679` |
| Accepted WP-C | `72b39de71024b3051357c17eee7922e657dcb81f` |
| Accepted WP-D | `3a83ccd9dbf7b627c98f70a9ad7ee4b0e19eeaea` |

The committed runner hash was independently recomputed and matched. Protected market/archive/outcome access during analysis was **0**; no `HOLDOUT_FINAL` artifacts were read. No runner, target seal, strategy semantics, or configuration was changed. Only generic exchange documentation was consulted externally, without market API calls.

## A. PASS-path TESTNET integration readiness

The work packages are reusable, but integration and certification remain necessary. WP-A/C/D share base `08e81bec003d645a0a0582db183a1b6916887eff`; none is already an ancestor of the final runner. WP-D deliberately leaves release identity unbound, and WP-C records external notification smoke as pending.

The mechanical sequence after Controller accepts an authoritative PASS is:

1. Create a separate RC2 integration branch from frozen candidate `10be512f...`. Record the accepted holdout runner, dispatch, evidence hashes, policy and config identity.
2. Merge accepted **WP-A → WP-C → WP-D**, in that order. Preserve frozen Tactical semantics and distinguish the integrated application SHA from the holdout runner SHA.
3. Resolve operational interfaces, then bind the release manifest to the final integrated source SHA, accepted WP-A certification and RC2 holdout authority. Preserve the RC1 evidence as historical provenance.
4. Validate in **DRY_RUN**, then obtain a separate Controller TESTNET authorization.

| Package | Main integration surfaces |
|---|---|
| WP-A | `live_db.py`, `live_runtime.py`, supervisor initialization, migration, reconciliation and restart |
| WP-C | General config, decision backends/fusion/service, Feishu proposal delivery and callbacks |
| WP-D | API lifespan/readiness, release manifest and operational runbook |

Direct file overlap is limited; consequential conflicts are interface and identity conflicts: initialization order, configuration defaults, account context, proposal freshness, runtime authority and manifest certification.

Minimum authority-critical validation:

- Exact integrated source/manifest identity; frozen strategy/config identity preserved.
- WP-A serialized initialization, migrations, eight database guards, startup/restart reconciliation and failure closure on its certified **Python 3.12.3**.
- Verified Tactical evidence → immutable case → constrained analysis → deterministic sizing → authenticated manual approval → fresh execution revalidation.
- TESTNET credential/account/endpoint binding; blocked LIVE/mainnet paths.
- Duplicate callback/intent rejection, partial-fill handling, uncertain submission recovery, protective-order ownership, reconciliation and kill switch.
- One project-required final validation gate on the stable integration commit, using authorized hermetic fixtures.
- External provider/Feishu smoke before relying on that notification channel for approvals.

Repeated historical replay, repeated unchanged manifest checks, and repeated full suites during iteration add no execution authority. Diagnostic subgroup results cannot substitute for PASS.

Before PASS, prepare the integration checklist, manifest schema, synthetic integration/fault fixtures, attribution specification, telemetry dashboard and operator runbook. Keep execution disabled and use a separate workspace. Do not rerun the holdout.

Source anchors: accepted WP-A `live_db.py:SerializedInitializer` and `live_runtime.py:LiveV1Runtime`; accepted WP-C `decision/service.py:TacticalLiveService`, `decision/fusion.py:DecisionFusion`, and `approval/feishu.py`; accepted WP-D `api.py:verify_rc1_release_manifest` and `docs/LIVE_V1_RC1_OPERATIONAL_RUNBOOK.md`. Consult these at the exact package SHAs above; RC1 certification is not automatically RC2 certification.

## B. FAIL / DIAGNOSTIC_ONLY attribution framework

First establish integrity, then attribute performance. Identity, chronology, coverage, determinism or publication defects are not evidence of directional failure.

Freeze the analysis specification before reading results:

- Join decision evidence, evaluation and trend-shadow records by immutable IDs; deduplicate signals using existing contract identities.
- Preserve separate denominators: decision snapshots, actionable signals, fills, no-fills, timeouts and target/stop-resolved trades.
- Reproduce the frozen aggregate calculations before adding diagnostics. Record missing funding and every fallback to net R excluding funding.
- Use fixed cohorts and explicit missing-value buckets; do not choose cutoffs after seeing outcomes.

| Required decomposition | Deterministic output |
|---|---|
| Aggregate and direction | Actionable count; LONG/SHORT counts; fill/no-fill/timeout counts; gross and net mean/median R |
| Costs | Per-trade reconciliation: `net R = gross R − execution cost R + signed funding R`; separate fees, slippage and funding |
| Ordering | STOP before TP1, TP1 before STOP, timeout, ambiguity/path-resolution counts; MFE/MAE |
| Stability | Same metrics for P1/P2/P3, each symbol and LONG/SHORT |
| Regime and decisions | Frozen 1h/4h regime, benchmark/derivative context, entry quality, signal and veto reason distributions |
| Entry and trend | Time to fill, bars since breakout, trend age/persistence and structure transition |
| Derivatives | OI acceleration, price/OI divergence, funding/basis levels and deltas/crowding |
| Execution diagnostic | Maker-preferred sensitivity, explicitly **NON_AUTHORITY** |

The existing fee/slippage decomposition is model-derived, not observed exchange commissions. Compare gross/net and cost components on identical complete trade cohorts; medians are not additively decomposable.

Use these attribution rules without changing the terminal:

- **Directional edge failure:** adequately supported gross results are nonpositive, with adverse target/stop ordering across supported partitions. Report this as evidence against the edge, not proof of causation.
- **Execution/friction failure:** gross edge is positive but net is negative, and matched-trade accounting explains the difference through fees/slippage/funding.
- **Insufficient support:** preserve the frozen requirements—100 aggregate actionable signals, 20 per enabled direction, three partitions and at least two supported partitions of 20 signals. Smaller exploratory cohorts remain descriptive.
- **Partition instability:** aggregate performance depends on one period, or supported partitions repeatedly deteriorate. Preserve the frozen stability gates.
- **LONG/SHORT weakness:** compare supported directions within the same partitions/regimes. A stronger direction cannot rescue aggregate FAIL.
- **Regime weakness:** identify concentration within predefined regime categories; treat it as a successor hypothesis, not permission to remove losing cohorts.
- **Likely timing failure:** later breakout-age cohorts show worse gross R, ordering or excursions across supported partitions. Label the association; do not infer an optimal entry delay.

Frozen PASS thresholds remain mean net R ≥ `0.05`, median ≥ `−0.05`, stop-before-target ≤ `0.65`, and the required nonnegative supported-partition ratio. Reuse `FrozenReleaseThresholds`; do not redefine gates.

Maker sensitivity may show a fee-only counterfactual on unchanged fills. It must also disclose that realistic maker execution changes fill probability, delay and adverse selection. Neither version promotes the candidate.

For a valid FAIL, permit at most four successor research families:

1. Entry confirmation/pullback timing.
2. Trend persistence and structure-transition selection.
3. OI confirmation and crowding controls.
4. Friction-aware execution/admission.

Develop and freeze successors on authorized development data, then use a new independent evaluation. No protected-result tuning or subgroup rescue.

Attribution blocker: the final runner's source publishes aggregate and rolling tables, but does not visibly export the complete decision/evaluation/trend ledger. After publication, the Controller should establish whether those records already exist in retained execution evidence. Missing fields must be marked unavailable; do not modify or rerun the sealed runner to reconstruct them.

Source anchors at the frozen candidate: `market_watch/decision_quality.py:compute_subset_metrics`, `evaluate_decision_quality_gates`, and `FrozenReleaseThresholds`; `market_watch/shadow_evidence.py:TacticalShadowEvaluationV2`; `market_watch/trend_shadow.py:TrendEvidenceV2Shadow` and `compute_trend_evidence_v2_shadow`. Final runner publication was inspected in source only.

## C. TESTNET/manual-live canary framework

The conditional path is:

**accepted PASS → RC2 integration → manually approved TESTNET → forward shadow observation → semantic/risk audit → separately authorized small manual live canary**

Current `src/btc_quant_agent/execution/policy.py:ExecutionCapabilityPolicyV1` explicitly blocks LIVE. A live canary therefore requires a separate capability implementation, security review and Controller authorization. It cannot be enabled by a flag or by holdout PASS.

The following are proposed operational ceilings, not current authorization or Tactical threshold changes:

| Control | Proposed canary bound |
|---|---|
| Approval | Human approval of every entry, exact immutable proposal, account, quantity, prices and expiry; no automatic ADD/reversal |
| Trade risk | Planned stop loss plus adverse costs ≤ **min(0.10% of dedicated canary equity, USDT 5)** |
| Positions | One position; one explicitly configured symbol |
| Leverage | Fixed **1×**, isolated margin; no automatic leverage increase |
| Exposure | Notional ≤25% of canary equity; skip if exchange minimums breach limits |
| Daily stop | Loss including fees, funding and unrealized loss ≥ **min(0.30% of start-of-day equity, USDT 15)** |
| Consecutive losses | Three completed losing trades; human review before resumption |
| Protection | Exchange-native stop for actual filled quantity, verified ownership/status; TP and exit orders cannot reverse exposure |
| Entry execution | Preserve the validated order policy. Maker preference requires separate approval; no automatic taker fallback |
| Timeout | Entry deadline ≤30 seconds and never beyond proposal expiry; cancel/reconcile remainder, protect partial fills |
| Protection deadline | Proposed ≤5 seconds after fill recognition; otherwise disable new risk and invoke the approved emergency reduction procedure |

These bound intended exposure; gaps and execution failures can exceed planned loss.

An ambiguous submit response must be reconciled by client/order identity before retrying. Binance documents that some timeout/503 responses can represent successful execution and warns against blind resubmission. See [Binance execution-status guidance](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info).

Required telemetry: linked release/evidence/case/proposal/intent hashes; approver and timestamps; submit/ack/reject/cancel events; client/exchange IDs; partial/full fills and actual costs; stop/TP status and quantities; account/position reconciliation differences; stream freshness; restart recovery; kill-switch events and final flatness.

Stop conditions: unknown order/exposure, duplicate execution, missing/rejected protection, reconciliation mismatch, stale account/market/case, failed runtime task, unexpected symbol/account, identity drift or risk-limit breach. Disable new risk immediately while retaining protection and reconciliation. Roll back software only after exposure is reconciled; never restore an older database blindly. Restart requires reconciliation and human resume approval.

Proposed minimum evidence before requesting a live canary: 72 continuous TESTNET hours; at least five valid manually approved round trips; 20 documented lifecycle/fault scenarios covering both directions, partial fills, uncertain submissions, callback replay, protection failure, disconnects and restart; zero unresolved exposure/protection discrepancies; then at least seven days of read-only forward shadow observation and a signed semantic/risk audit. These are operational qualification criteria, not proof of profitability. Do not fabricate signals to meet counts.

Remaining blockers are release/Python certification rebinding, external approval-channel smoke, detailed attribution-record availability, actual TESTNET certification, and the deliberately blocked LIVE capability.

| Controller terminal | Exact next action |
|---|---|
| **PASS** | Accept authority evidence; integrate A/C/D; bind RC2 release; complete validation; authorize manual TESTNET separately |
| **FAIL** | Verify it is an integrity-valid performance FAIL; apply the frozen attribution framework; retain execution lock; research successors |
| **DIAGNOSTIC_ONLY** | Record failed support/pass-band gates and missing evidence; allow authorized observation only; no promotion |
| **INFRA_INCOMPLETE** | Preserve attempt receipt; isolate infrastructure cause and protected-access history; Controller decides further authority; no automatic retry |

**REAL_FUNDS authority remains NONE.**
