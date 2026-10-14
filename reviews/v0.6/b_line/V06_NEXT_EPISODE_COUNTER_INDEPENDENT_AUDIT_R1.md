# ChatGPT-1 — Independent Synthetic Episode Counter Audit R1

**Terminal verdict: `EPISODE_SYNTHETIC_REVIEW_FAIL`** for the **complete proposed canonical/PIT-qualified episode-accounting contract**. The frozen implementation **does** satisfy a substantial subset of its *invented-input* determinism, deduplication, rearm/cooldown, basic PIT, occupancy, and denominator checks; this is **`POSITIVE_SYNTHETIC_SUBTESTS_PASS`**, not a fully validated canonical opportunity counter. Specific unclosed timestamp/source-gap/identity inputs make a general `EPISODE_SYNTHETIC_REVIEW_PASS_WITH_LIMITS` premature. None of these tests imply empirical BTC opportunities, OI admission, after-cost Alpha or permission to run a historical trial.

**Role:** ChatGPT-1 Independent Supervisory Auditor, 2026-10-14 (Asia/Shanghai), separate from the frozen two-file implementation author. This is a source-and-invented-fixture audit only, with **zero** market observations, execution, protected access, real outcomes, or actual opportunity-frequency estimation.

## 1. Exact-SHA authority, provenance and remote CI

| Object | Immutable proof |
|---|---|
| Independent Controller task authorization | Commit **`8de03d93b53c0c9f6cc40af1045b954300d6f699`**, `prompts/v0.6/b_line/V06_NEXT_EPISODE_INDEPENDENT_AUDIT_R1.md`, blob **`781ad11813039af34048e206fca108692bdd5fd6`** |
| Target frozen implementation | Commit **`a144640acda5340b2b120ad5a451c3d193dea81c`**, verified one direct parent **`13e3a710b137efeec2e21e3002f748834ec0cc22`** |
| Python counter | `scripts/strategy_research/g2_next_episode_identity_r1.py`, Git blob **`bf944dd2bcdb1d844f2ab91834e0c9b1703383fd`** (277 lines) |
| Author synthetic unit suite | `tests/test_v06_g2_next_episode_identity_r1.py`, Git blob **`d2101ef53e5ad07a41177d7758599659d7901071`** (335 lines) |
| Exact remote target | `feature/v06-reset-r1-canonical-episode-counter-synthetic` HEAD independently resolves to **`a144640acda5340b2b120ad5a451c3d193dea81c`**. Git comparison confirms **one commit ahead, zero behind, exactly two newly added files (+277/+335)**, with no other paths modified |
| Actual GitHub Actions | [run `38523430724`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38523430724), exact target commit, push, **overall FAILURE**. Independently viewed CI job metadata and actual logs: **3012 passed, 1 failed, 2 skipped**, nine warnings; actual mode `full`, `PROFILE full CMD ['pytest','-q','--durations=20','--junitxml=ci-junit.xml']`. Named failure is the inherited `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph` digest mismatch (`ee185f...` versus `d5a962...`). **`FULL_REPO_PASS` is FALSE**. The unrelated H40 failure must not be waived or mislabeled as passing because the novel two-file candidate is disjoint |

Read frozen author files both via path+exact SHA and direct Git blob read. Independently reconstructed the **entire frozen 277-line Python module** inside an **ephemeral isolated local scratch directory** and verified its computed Git blob SHA-1 **exactly matched `bf944dd2bcdb1d844f2ab91834e0c9b1703383fd`**. This is an exact-byte source check, not a reimplementation. The author's separate 335-line suite was read but **not** reproduced or run locally in full. Tests below are separately written **independent adversarial fixtures**, which distinguish reviewer observations from the author's own CI assertions.

## 2. Independently executed synthetic-only tests

**Actual commands:** `python -m pytest -q /mnt/data/episode_audit_readonly/test_independent_episode_audit.py` and `python -m pytest -q /mnt/data/episode_audit_readonly/test_independent_expected_invariants.py` on the locally exact-byte-verified Python module. All timestamps, structures, `source_identity_hash` strings, zones, confirmation labels, quote booleans and holds were **invented**; these files were **NOT pushed** to GitHub or inserted into the official source/test tree.

1. **Independent positive and observation fixtures: `14 passed in 0.16s`**. Reproduced nested raw-alert/episode/PIT/quote/hypothetical-admission stages for 5/15/30-minute duplicate confirmations; reconnect-epoch duplicate suppression; permutation-invariant replay; simultaneous opposing-side suppression; late OI and quote gate; precommitted same-family rearm after actual invalidation plus 2-hour cooldown; missing/occupied union example **calendar 72 h, eligible 44 h**; 4–24h single-slot occupancy; source/zone definition conflict rejection; future-state rejection for the given row; prefix invariance; and additional malformed identity/coverage probes **as observations of the current implementation**. This verifies **synthetic behavior**, not real opportunity cadence.
2. **Independent proposed causal-contract RED witnesses: `4 failed in 0.46s`** (these are **deliberate negative tests** asserting stronger required invariants; their failure is **not** a claim that the author's green tests failed). They reproduce the four unclosed gates listed below from exact frozen module code. Test outcome distinctions are essential: existing author full CI is red for **H40**; the reviewer's four **newly proposed invariants** are red for episode-contract gaps.
3. **One reviewer hypothesis was falsified by execution and withdrawn.** A repeated *older parent* invalidation does **not** reset lineage after a new child has rearmed, because the predecessor mismatch check rejects it first. The originally attempted witness was corrected and rerun; it now passes as a **safe regression control**, not a reported defect. Do not count a hypothetical bypass that exact execution disproved.

## 3. Exact bounded strengths accepted

| Area | Frozen implementation and observed result | Narrow conclusion |
|---|---|---|
| **Causal episode identity** | `Seed.episode_id` (`#L48-L51`) hashes original `source_identity_hash, structure_id, first_known_at`, not side, reconnection, confirmation, future OI, quote or outcomes. `replay_key` intentionally excludes `connection_epoch` (`#L82-L86`). 5m/15m/30m confirmations under same frozen Seed remain a **single** counted episode. | **PASS synthetic dedup/ID semantics for well-formed inputs** |
| **Order and opposite side** | Stable sort `(decision_at, invalidation-first, replay_key)` and `simultaneous` sets (`#L157-L180`) reject simultaneously conflicting sides; late opposite side does not create a second episode (`#L225-L228`). | **PASS** for declared sides/timestamps, not proof of actual causal confirmation |
| **Basic PIT checks** | Row-specific `seed.first_known_at` and `state_known_at` fences, OI receipt/event age and bound `oi_received_at <= decision_at` (`#L185-L201, #L232-L240`); `quote_known_at` and `admission_known_at` prevent separate late booleans from backfilling (`#L244-L253`). | **PASS only for trusted input clocks already proven externally** |
| **Rearm / invalidation / single-slot** | Latched `invalidated`, parent reference, cooldown and 4–24h planned hold; same-time occupancy and future overlap are excluded (`#L202-L218, #L249-L259`); repeated older invalidation correctly rejected once a child became current. | **PASS** ordinary synthetic fixtures; one cohort-selection ambiguity remains |
| **Clock and result typing** | `Clock.missing/censored/occupied` union clipping and half-open interval accounting (`#L89-L115, #L261-L277`) gave independently observed 72h/44h; `rate_status` stays **`RATE_NOT_ADMITTED`**. Hypothetical planned holds are explicitly **not** used to reduce denominator, only precommitted occupancy. | **PASS** named arithmetic, **no measured rate/frequency or Alpha** |

## 4. Blocking or unresolved independent findings

### E01 — HIGH — 5m/15m/30m **confirmation close / first-known-at is not provable from available schema**

- **Exact source:** `Alert` fields `confirmation_minutes`, `decision_at`, `state_known_at` (`#L54-L80`), and confirmed-state/PIT checks (`#L173-L180, #L200, #L236-L243`).
- **RED witness:** An alert *labeled 30-minute confirmation* at invented decision **12:05** with `state_known_at=12:00` and 30-minute bar assumed **12:00–12:30** is accepted as **`PIT_QUALIFIED=1`**, even though a confirmation from *that* bar could not yet have closed. The implementation **does not store the identity, start/end, close-receipt timestamp or exact period** of the confirmed bar; it simply trusts the caller's `CONFIRMED` and `state_known_at` assertions. This example does **not** imply that *all* 30m confirmations at 12:05 are invalid: a prior 11:30–12:00 closed bar could be legitimate, but **the schema cannot distinguish these cases**.
- **Required fix:** bind the confirmation to a verifiable bar interval, completed-at and receiver-known-at witness; ensure the eligible decision is after that specific closed bar and its first availability. `state_known_at` cannot silently substitute for provider/receiver evidence. Until then this module does not independently certify PIT-qualified confirmation windows.

### E02 — HIGH — `FUTURE_STATE` input mutates the **lineage/cohort state** before the future-state check

- **Exact source:** `#L191-L201`, especially **`lineage.setdefault(family,eid)` on L199 before `state_known_at > decision_at` at L200–201**.
- **RED witness:** Same family/source, original Seed A first-known at **12:00**, decision 12:05 but future state known at **14:00**; later distinct Seed B first-known at **12:10**, decision 12:15 with all B's clocks ≤ decision. **B alone**: `PIT_QUALIFIED=1`. **A+B**: A returns `FUTURE_STATE`, but B returns `REARM_NOT_CAUSAL`, and total `PIT_QUALIFIED=0`. Thus insertion of a temporally invalid record changes later eligibility/cohort counts. The result is conservative undercount, not an unsafe trade admit; it is nevertheless material to episode/rate accounting and requires a documented rule.
- **Qualification:** The author may *intend* every authentic precommitted original seed (including provisional or a future-state alert) to reserve its structure's lineage. If so, a separate **PIT-qualified seed-introduction event** and explicit reserve/rearm state machine must demonstrate that causal property; an invalid future-confirmation row must not implicitly serve as that authority. **Do not automatically delete legitimate provisional seed identity on a speculative fix.**

### E03 — HIGH — clock source gaps cover **decision instant**, not required confirmation/source evidence interval

- **Exact source:** `#L232-L235`, uses `_overlap(decision_at, decision_at+1, clock.missing+clock.censored)`; `Clock` excludes gaps from denominator but has no source-type or evidence-window binding.
- **RED witness:** A 5m `CONFIRMED` alert at synthetic **12:05** with `Clock.missing=((12:00,12:05),)` and default `source_gap=False` returns **`PIT_QUALIFIED=1`** despite 100% missing coverage for the immediately preceding claimed 5m confirmation window. The denominator does exclude these 5 minutes, but the decision stage independently admits that candidate.
- **Required fix:** bind every contributing price/confirmation, quote and optional OI feature to the actual sampled interval/source, and compute missing/censored coverage on the required **feature windows**, not only decision second; or specify and enforce an independently verified upstream source-gap contract. The current rule is insufficient evidence for a source-eligible canonical episode.

### E04 — MEDIUM — `source_identity_hash` has **opaque nonempty-string** validation, no provenance proof

- **Exact source:** `Seed.__post_init__` `#L36-L46` verifies only nonempty `source_identity_hash`, while `episode_id` `#L48-L51` incorporates this arbitrary string in a locally computed SHA-256. The author's own invented fixtures use `synthetic-source-hash`, not a cryptographic digest; this is appropriate for a mock but **cannot** be mistaken for a verified immutable source manifest hash.
- **RED witness:** `source_identity_hash='not-a-cryptographic-hash'` constructs a Seed and permits `PIT_QUALIFIED=1`; requiring an actual fixed-format SHA-256 would raise, which **does not occur**.
- **Required fix:** either rename the field **opaque_synthetic_source_id** and explicitly classify `SOURCE_IDENTITY_UNVERIFIED` for these fixtures, or enforce canonical full-length hex digest + externally verified manifest/blob/source receipts in a future source-qualified contract. Merely hashing the unvalidated string to create an `episode_id` is **not** provider/source integrity proof.

## 5. Quantitative account, epistemic and safety conclusions

For the valid-input fixtures independently reviewed:

- Stage cardinalities satisfy **`0 <= hypothetical_admitted <= quote_screened_conditional <= pit_qualified <= episode <= raw_alert - duplicate_alert - unknown_alert`** for tested scenarios. This is only a necessary finite witness, **not** a universally proven invariant over all possible alerts.
- 5m/15m/30m duplicate timestamps/confirmation modes do not create multiple unique episode IDs; one opposite-side conflict does not create an additional episode. Replay permutations of tested input sets return identical dataclasses.
- Calendrical versus eligible-window arithmetic is **invented**, including overlapping missing/censored/occupied spans; it does not estimate qualified opportunities per 48h. The denominator intentionally excludes **precommitted** occupied intervals but **does not subtract dynamically admitted synthetic holds**; the label `eligible_clock_hours` must not be construed as fully available portfolio capacity for rate estimation without an additional denominator contract.
- Mock quote-screen and admitted-hold booleans, OI event/receipt timestamps, future source identity strings and clock availability are **inputs**, not observations by this module. `rate_status=RATE_NOT_ADMITTED` and zero PnL/fill fields correctly avoid conflating engineering logic with execution evidence.

**Finite corrective path:** one separately dispatched two-file (or specifically re-authorized changed-path) **synthetic-only** repair should: (1) define input witness schema for confirmation bar time and receiver known-at, (2) explicitly freeze seed-reservation versus rejection transitions, including `FUTURE_STATE`, (3) bind source-gap checks to required intervals and missing OI/quote cases, (4) make source identity explicitly synthetic-opaque or cryptographically/verifiably constrained, and (5) rerun independent RED/GREEN deterministic cases plus canonical publisher's existing tests. If such changed behavior is not proven, do not use this candidate as a trusted opportunity-rate numerator/denominator, not even for source-QC release acceptance.

## 6. Independent publication and frozen stop conditions

**Report-only authorized write:** add exactly **`reviews/v0.6/b_line/V06_NEXT_EPISODE_COUNTER_INDEPENDENT_AUDIT_R1.md`** in a **new isolated** `docs/v06-next-episode-independent-audit-r1` branch, directly rooted at immutable dispatch **`8de03d93b53c0c9f6cc40af1045b954300d6f699`**. This review does **not** change target source/tests or the prior H40/strategy result, does not merge or use the holdout. New reviewer-local synthetic tests exist only in disposable scratch and have **not** been published as source/test modifications.

**Hard gates:** `SOURCE_NOT_ADMITTED / G2_ALPHA_NO_GO / TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`, and **`FULL_CI_FAIL_H40`** on the frozen implementation. No measured event cadence, trade frequency, filled orders, profitability, trading costs, new data source admission, market collection or historical return/economic outcome score. No protected H39/H40/H41/Forward/Final Holdout or owner local data roots, accounts or credentials were read.

**Final independent terminal: `EPISODE_SYNTHETIC_REVIEW_FAIL`.** Accepted deterministic/synthetic sub-behaviors remain useful but are **not** independent validation of a canonical, PIT-evidence-complete opportunity counter.
