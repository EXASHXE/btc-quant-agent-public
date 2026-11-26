# QUANT — Current checkpoint and roadmap (2026-11-26 UTC+8)

## Controlling checkpoint — 2026-11-26 10:12 UTC+8

Product remains Personal Trading Intelligence & Market Structure Radar. Current engineering workroot is /root/workspace/project/quant-1.0.0 (branch v1.0.0), historical root /root/workspace/project/quant-0.8.0, docs root /root/workspace/project/quant-docs-engineering. Both local v1.0.0 and v0.8.0 still point at the accepted RC1 2a404719a9875acba2706b2cd9f292343ff263b0. Local tag v1.0-rc1 remains the accepted release. Remote v1.0.0 branch and v1.0-rc1 tag not present in the checked origin ls-remote result; no code publication performed. Local docs remains 3c536f4 and diverges from GitHub docs/engineering; reconcile deliberately, never force-reset.

| Work package | Verified current status |
|---|---|
| Stage 3 / RC1 | CONTROLLER_ACCEPTED, 314-test parity per previous acceptance. |
| Stage 4A | bedd2d753b7f64910f551fa70d7f9ad8177daaea, scoped acceptance supported by both web Controllers; not yet merged. Four installed operator packages 1.0.0rc1, backup retained mode 0700, pip check and doctor PASS, 10 new tests and 3/3 genuine card replays independently verified previously; operator DB hashes unchanged during replay. |
| Stage 4B offline hardening | 4b77df2f46d0ca1e37646dd5192f10ea23679aab, feat/stage4b-s6-hardening, parent bedd2d7, 8 files +2474/-63. SOURCE_VERIFIED commit/runbook; implementation includes structured approval, preflight, Hermes runtime checker, sandbox, partial delivery and rollback updates. Independent source/test acceptance and integration PENDING; actual activation NOT_AUTHORIZED by this documentation update. |
| Track C | beb3d572879b3ccd0d2d50f7decd87757970cf61, feat/track-c-microstructure, parent bedd2d7, 13 research files +2698. Report and registry SOURCE_VERIFIED, 10/16 trials TC01..10 completed, M_P3=9/M_Track_C=10/M_global=19. NO_CANDIDATE_PROMOTED; no finalist. Independent code/test/reproducibility acceptance PENDING. No promotion or further search authorized. |
| Workspace reclamation | Read-only POST_RC1_WORKSPACE_RECLAMATION_AUDIT.md draft: 66 entries, potential 4.63 GiB on disk; 1 KEEP_ACTIVE, 55 ARCHIVE_BEFORE_DELETE, 10 SAFE_CANDIDATE_AFTER_OWNER_CONFIRM. No removal/prune authorization; preserve S5 rollback, RC1 wheels and QA, ignored evidence, cross-OS worktree state. |
| S6 / Hermes | Hermes service active; actual RC1 in-memory load NOT independently proven, hardening runbook reports stale pre-RC1 indicators, verify before approved restart. No quant S6 timer listed; approval marker absent; no activation or live delivery performed. |
| Final OOS / Layers | Holdout mode 0444 observed, no observation access. Track C report records unchanged metadata and P3 registry/core integrity. P4 NOT_RUN; Layer2 unauthorized; Layer3 disabled. |

Track C WF diagnostic (development only, not economic validation): TC-01 closed/next-open 17/20 trades, +0.4106/+0.2806 R/trade; TC-03 15/18, +0.4678/+0.3236; TC-05 (CVD ablation) 116/130, +0.0888/-0.0009. Range-edge results are more promising than trend pullback in these samples, but small samples, selection bias and execution sensitivity prevent promotion. No robust candidate cleared all eight gates; robustness/audit slots skipped. P3 and Track C registry budgets remain separate; cumulative DSR accounting 19. No rescue tuning or final OOS evaluation. Radar artifacts are a separate potential deliverable, not live capability. Estimated OHLCV volume profile, potential liquidity levels, aggregated taker flow and sweep-recovery proxy must retain their provenance labels.

### Next sequence (planning only)
1. Reconcile one shared queue and independent acceptance of Track C and Stage 4B hardening. Verify frozen preregistration/TC-F01..06, exact source, report/registry integrity, XML/test evidence, replay and immutability; inspect S6 approval binding, preflight, delivery and sandbox. T3 status is not acceptance: Stage 4A and hardening threads reported completed but unsettled; original Track C T3 thread reported interrupted while commit/report/registry exist. Reconcile outcome before reuse or another dispatch; do not blindly rerun experiments.
2. Integrate accepted branches non-destructively: FF Stage 4A first, then accepted Track C and Stage 4B sibling branches with ancestry/scope checks, combined regression, independent QA and one recorded disposition. Do not claim merged before verified. Keep active venv and frozen Core untouched; source/tag publication separately scoped.
3. S6 field readiness: Owner chooses cadence (4h recommended initially, 1h alternative), destination, budget and bounded authorization window; verify actual Hermes runtime, approved restart if necessary, preflight/systemd and one bounded first field run before recurrence. No marker/unit installation, live scan, Feishu send or gateway restart merely from planning. Preserve zero retry, cooldown and sticky venue stops, partial delivery/outbox discipline.
4. Separately plan additive radar enrichment from Track C modules: independent module acceptance, separate causal rolling history cache, explicit public data budget and Owner approval, unavailable handling and advisory rendering. Existing live 32-bar history cannot supply 7d/14d profile. No B2 kernel/card mutation or strategy promotion.
5. Workspace reclamation only after verified off-repo evidence archive, active dependency review and Windows-side verification, plus explicit Owner approval. No blanket deletion or prune. Pi P2 remains deferred; next strategy research only through new predeclared hypothesis and separately approved budget; preserve untouched OOS.

Both WEB Controllers remain coequal 1-A/0-C. T3 dispatch requires Owner prompt confirmation of exact task and executor, REUSE_THREAD_PREFERRED with compatible settled thread checks; no autonomous action. This update verified local refs/diffs, installed package metadata, service/timer/marker state, report/registry and audit draft. Prior test/replay evidence is attributed to earlier review; no new full test rerun, no data observation in final holdout, no branch merge, dispatch, service activation, cleanup or code push performed.

---

## Historical checkpoint (before Stage 4A; superseded where inconsistent)
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
