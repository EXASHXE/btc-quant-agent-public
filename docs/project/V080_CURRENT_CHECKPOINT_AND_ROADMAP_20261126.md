# QUANT — Current checkpoint and roadmap (2026-11-26 UTC+8)

**Current accepted local software baseline: QUANT v1.0-rc1.** Product: Personal Trading Intelligence and Market Structure Radar, not an economically validated trading strategy or automatic execution system.

## Source and evidence authority
- Local code root: /root/workspace/project/quant-0.8.0. Local v0.8.0 at 2a404719a9875acba2706b2cd9f292343ff263b0; local annotated v1.0-rc1 tag observed. Local docs root: /root/workspace/project/quant-docs-engineering; dual-Controller acceptance recorded in local docs commit 3c536f4e9e24a42e03c3094ad10e1ca0c35f637c (2026-11-25 HKT).
- origin/v0.8.0 observed at c35445a, 22 commits behind local; remote code/tag publication NOT verified or performed. Local and GitHub documentation histories differ; reconcile by non-destructive merge, not reset/force push.
- [RC1 acceptance record](../v1.0-rc1-release-acceptance-20261125.md). Evidence labels distinguish SOURCE_VERIFIED, REPRODUCED_OFFLINE, INDEPENDENT_QA, WORKER_REPORTED, DOCUMENTED_ONLY, CONTROLLER_ACCEPTED, OWNER_ATTESTED, UNKNOWN, BLOCKED.

| Milestone | State / evidence |
|---|---|
| Phase 0+1 / S3 | Genuine Scan 4 COMPLETE, 39/39 HTTP 200, 0 recorded retries, BTC/ETH/SOL NO_SETUP, raw/card hash integrity and Neon 3/3 replay; previous 3 failed scans preserved. Runtime a39576d, local debit 54 vs closing header 33, exact funding weight UNKNOWN, d=5. |
| Phase 2 / S4 / S5 | Bridge 894fc9a, S5 816a95d; Hermes/Feishu card UX, tools and feedback work delivered. Earlier S4 3 genuine deliveries reported; scoped live field evidence only, not reverified here. |
| Stage 2 P1 | 7c89b0c offline PIT, simulator and frozen B2 baseline foundation. |
| Stage 2 P2 | 71d8265 real-history diagnostic; 4,155 archive files per QA; 36 months 2023-11-01 to 2026-11-01 UTC, first 30 months development, final six months untouched. 122 signals, closed 100 fills/-8.671 R, next-open 114 fills/-2.493 R. No positive edge established. |
| Stage 2 P3 | P3A 7c23569, P3B 1b676ea, P3C ad8866236cc07ca3fea66c649a117365bd4ce513. 9/24 primary slots used (6 A + 3 B); 171+56+87=314 tests per combined report. NO_CANDIDATE_BEATS_B2_V1. TA-04/TB-02 unpromoted; conditional and robustness slots skipped as prescribed. |
| Stage 2 P4 | NOT_RUN: no eligible candidate. Final holdout 2026-05-01 to 2026-11-01 UTC physically separated, 0444, unevaluated. |
| Stage 3 | CONTROLLER_ACCEPTED per local release record: four canonical packages quant_transport, quant_core, quant_agent_bridge, quant_research; 314 test identity parity across pre-removal/editable/wheel reports, four-wheel offline installation/pip check/CLI smoke, genuine replay, frozen kernel and operator-state invariance per recorded acceptance. Preservation ref backup/v0.8.0-pre-stage3-20261125, restricted recovery archive. |
| RC1 operator deployment | PENDING; local accepted source/tag is not active operator installation. Hosted CI UNVERIFIED. |
| S6 recurrence | NOT_AUTHORIZED. |

P3 WF: TA-04 +0.0336/+0.1312 R per trade (15/18 fills), TB-02 72h +0.053376/+0.033099 R per trade (27/28 fills); both failed locked gates. Do not loosen gates or use unused trial slots for rescue search. Current research horizon ~4h–5d per preregistration; frozen B2 V1 6h default/2–12h policy unchanged. EXECUTABLE = market-side eligibility only; account UNAVAILABLE. Layer 1 public read-only under separate bounded authority; Layer 2 USER_DATA unauthorized; Layer 3 TRADE disabled.

## Next priorities — proposals, not dispatches
1. P0: reconcile source/tag publication and operator release readiness, offline wheel installation/rollback plan, independent clean-environment validation. Remote code/tag publication and active operator install need explicit Owner scope; no automatic deployment.
2. P1: human-use radar validation using existing evidence/cards, fresh-vs-historical labeling, authenticated inbound, single sender, manual feedback lifecycle and useful market structure interpretation. Separate live scan and Feishu grants. No recommendation that a negative-expectancy strategy is validated.
3. P2: propose next research methodology based on P3 evidence, not parameter rescue. New signal architecture/frequency, regime and execution robustness, equal-risk OOS design. Preserve P3 evidence and untouched holdout; no P4 without frozen eligible finalist and separate approval. No new trial cycle is granted.
4. P3: S6 bounded recurring radar only after operator readiness, actual-use feedback, explicit cadence/budget and separate Owner authorization; preserve zero retry, 429 cooldown, 403/418/451 stops, single sender and zero TRADE. Pi P2 remains deferred unless Owner explicitly changes priority. QI1/QL1/QB1/QR1 are historical labels to reconcile with delivered packages, not duplicate dispatches.

## Governance
Both web Controllers coequal 1-A/0-C; one reconciled queue, one accountable Controller and independent reviewer per consequential package, no Worker self-acceptance. Local Codex Sol complex engineering, AGY Neon complex peer engineering/QA, Hydrogen routine work, Astra architecture/methodology. [Owner-confirmed T3 dispatch protocol](V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md) is controlling; default read-only, no automatic remote launch. Owner-direct bounded offline forwarding remains valid.
Evidence note: direct 2026-11-26 inspection verified branch positions, tag existence, local acceptance text, and P3 report. Earlier test/replay/hash claims retain original attribution, not rerun in this documentation update. No final holdout observations accessed. No task newly dispatched.
