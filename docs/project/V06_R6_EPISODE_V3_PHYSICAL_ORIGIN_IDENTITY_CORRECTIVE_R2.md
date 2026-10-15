# Episode V3 R2 — Physical-Origin, Rearm, E_S/E_X Estimand and Action-Slot Corrective Contract

**Author:** ChatGPT-2-R Independent Research Scientist; **work:** outcome-blind document-only correction.  
**Exact Controller dispatch:** commit `c2d6276f9ee857d760adcc61b073547888d67535`; prompt `prompts/v0.6/b_line/V06_R6_2R_EPISODE_V3_PHYSICAL_ORIGIN_REPAIR_R2.md`; Git blob `0e0c78c6b060ba7c320de6d4462c4d8200289c9f`.  
**Branch:** `docs/v06-r6-2r-episode-identity-correction-r2` direct from that dispatch; **only ADD** this document. Output SHA/Blob are verifiable after publication, not knowable in the file before commit.  
**Terminal proposed:** `EPISODE_V3_R2_DESIGN_READY_FOR_2C_REVIEW`, design-author completion **only**, independent 2-C/1/0 not performed. `SOURCE_NOT_ADMITTED / NOVELTY_CANDIDATE_SOURCE_BLOCKED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE` persist. No network market data, no historical outcome/PnL/backtest, protected A-line H39/H40/H41/Forward/Final Holdout, owner data roots/private accounts/secrets, funds, trades, actual implementation/tests or merge.

## 0. Frozen R5 verdicts, old identity and exact inputs

| Evidence | Immutable commit SHA | File / exact Git blob | Binding finding |
|---|---|---|---|
| Old 2-R Episode V3 R1 | `68f7b48feeeef611f0a514600d72217058f21637` | `docs/project/V06_OI_R3_EPISODE_ID_V3_CAUSAL_CROSSWALK_R1.md` / `493354c2ecf3270ca1ae05933dcfeedf2eaabd63` | Prior R1 **not modified or accepted** |
| 2-C independent FAIL | `90d7ef9c5485a72f6bcf4dacdc4310a7ff9373e6` | `reviews/v0.6/b_line/V06_R5_2C_EPISODE_V3_ADVERSARIAL_CHALLENGE_R1.md` / `b4454dc18008fdfe504785decec1ae70cb9f81ec` | `EPISODE_V3_CHALLENGE_FAIL`, V3-C01–C06 |
| 1 consequential FAIL | `c2e3424b243e7796c8c595b8a836afe6795937a9` | `reviews/v0.6/b_line/V06_R5_1_SCIENCE_PA_EPISODE_COST_CONSEQUENTIAL_AUDIT_R1.md` / `c80d0c357dd2a99d64dce8bb1b641e743d6a636d` | `R5_SCIENCE_MATERIAL_FAIL`; Episode E01–E05 |
| Controller R5 L2 | `7300afa425277cf8f328082c15f17002552d6e8c` | `reviews/v0.6/b_line/V06_CONTROLLER_R5_L2_ALPHA_AND_SOURCE_FEASIBILITY_ADJUDICATION_20261015_R1.md` | `SOURCE_FEASIBILITY_BLOCKED / EPISODE_V3_MATERIAL_FAIL` |
| Earlier R3 X/OI method | `35c269aecf0f1b756575af2ac5e355f2cf53757c` | `docs/project/V06_NEXT_OI_C01_C03_CAUSAL_METHOD_AND_RECEIVER_DESIGN_R3.md` / `56482b2ce305071d5a5fb3b3e19468fb1b33a828` | Old `E_X^{R3}` estimand remains separately frozen |
| Episode R2 synthetic code | `bc27ab8ab41319ba08f381d908d12f8fb05a104e` | `scripts/strategy_research/g2_next_episode_identity_r1.py` / `4c78dd9797b35fb2e49a1eba006e764062b2dcc6` | Synthetic Seed/Alert, cannot grant source identity |
| Episode R2 independent synthetic PASS_WITH_LIMITS | `31b0d12d202862899829158f3b50c44fab8067df` | `reviews/v0.6/b_line/V06_NEXT_EPISODE_R2_INDEPENDENT_CAUSAL_AUDIT.md` / `61c3d6de7b0688d44e498f205a31a11744280e83` | 49 focused remote passes apply to *earlier synthetic R2*, not this design |

| R5 issue | Old failure | Repair in this sidecar | Still unproven |
|---|---|---|---|
| V3-C01 / E01 **BLOCKER** | Physical ID contained discovery-rule ID and first receiver-known timestamp; one impulse split | Common verified upstream origin equivalence and atomic registry; rules, receiver epochs, clock receipts are children (`1) | Actual authenticated physical shock source and origin segmentation |
| V3-C02 / E02 **BLOCKER** | Parent/cooldown demanded for all new origins; independent simultaneous shocks suppressed | Separate independent physical creation, same-lineage rearm, strategy cooldown, portfolio occupancy and event cancellation (`2) | Genuine source lineage membership |
| V3-C03 / E03 **HIGH** | Nominal bar close / future-invalid side could poison another side | Prequalify bar, durable-known clock and source witness **before** side conflict reduction at fixed decision tick (`3) | Production PIT clock and tests |
| V3-C04 / E04 **HIGH** | Old R3 E_X changed target without re-registration | All cohort and theta versions distinct; X-blackout unknown, separate policy NO_ACTION denominator (`4) | Source/population power and trade cadence |
| V3-C05 / E05 **HIGH** | Evidence version in executable key minted duplicate action after source correction | Write-once source-view-invariant action slot, immutable as-known snapshot (`5) | Actual durable idempotent runner / ACK |
| V3-C06 **HIGH** | Opaque hash treated as possible original witness | Explicit synthetic vs real trust grading and honest UNMAPPABLE legacy receipts (`6) | Legal source/venue identity/first-known |

## 1. Physical origin vs discovery rule, receiver and physical-group witness

**Do not claim that a Binance trade, OI bucket or OHLC bar is inherently a uniquely defined "physical shock".** One native trade/sequence item is an atomic exchange observation; grouping items into an impulse requires a **separate, uniform, preregistered, causal origin-segmentation specification**. That specification must have independently verifiable original membership, deterministic source-native discriminator and proof of whether two observations refer to the same underlying origin. A technical indicator's discovery rule is *not* the authority for physical equivalence.

Definitions:
- `NativeSourceAtom`: authenticated provider-side stable ID/sequence **if available**, with venue, exact BTCUSDT USDⓈ-M contract/spec and native source version. Not invented from local timestamps.
- `PhysicalOriginProof`: authenticated common origin-namespace + versioned origin segmentation specification + independently evidenced original source lineage/range + **unique origin discriminator**. Equality and inequality are both evidence claims; ambiguous groups sharing partial sources are NOT automatically equal or distinct.
- `PhysicalEventRegistryRecord`: authoritative immutable physical-origin parent, with one canonical proof digest. Registry first-known and later corrections are **fields/children, not key material**.
- `OriginObservation`: per discovery rule/version and receiver session: safe first-complete-and-durable UTC known-at upper bound, monotonic epoch/attestation, raw-body hash, parser/source version, candidate X attributes. Many such observations per parent.
- `DirectionClaim`: downstream 5m/15m/30m closed-bar first-durable witnessed LONG/SHORT confirmations, side-conflict state and causal known-at.
- `PolicyDecision`: frozen source-as-known/quote/risk/NO_ACTION snapshot on its own policy decision/action slot.

**Formal physical equivalence:** `o1 ≡_phys o2` iff both carry an independently proved **identical canonical native-origin-group witness** under the *same* source/contract/segmentation namespace. Different fully proved original group discriminator => two distinct parents, even if both timestamps are 12:00:00. Missing source-side original group proof, only matching bar timestamp/price or overlapping unadmitted sequence ranges => `ORIGIN_UNJOINABLE`. Contradictory proof or unresolved overlapping group segmentation => `ORIGIN_AMBIGUOUS`. No transitive union of weak "maybe same" aliases. A SHA that matches unverified local JSON proves only byte integrity of that synthetic/local data, not exchange origin.

**Canonical physical key (conceptual; source identity NOT qualified):** `H("V06_ORIGIN_V3_R2" || Canonical({trusted_source_origin_namespace, versioned_contract_identity, common_origin_segmentation_spec_version, independently_unique_origin_discriminator, source_lineage_root}))`. The canonical byte encoding, segment ownership and proof validation must be separately frozen by a future implementation permit. It **MUST NOT** contain `discovery_rule_id`, original or subsequent receiver clock, connection epoch, confirmation 5m/15m/30m, side, X signal, OI, quote, policy parameters, occupancy, entry time, returns or after-cost outcome. Segmentation spec is the **shared original physical-origin rule**, NOT the separate rule `R_fast` or `R_slow` that *recognizes* it.

**Registry atomicity/concurrency:** One authoritative origin-key namespace and linearizable compare-and-set (unique canonical original proof key). Two rule observers and two receivers submit identical original proof → **one** parent registration, append 2+ distinct `OriginObservation` records with their *own* clock known-at. Concurrent provisional unjoined observations cannot independently certify a physical parent. If two registries or disconnected receivers mint divergent physical IDs from the same proof before reconciling, flag `ORIGIN_REGISTRY_SPLIT_BRAIN`, stop action admission, preserve both raw receipt paths and seek separate audited alias resolution. No "first arrival wins" unverified native origin, no silent ID overwrite. Hash collision over **different** immutable certified cores => `CORE_CONFLICT/STOP`. This is a *proposal*, not a working database.

**Trust grade:** `SYNTHETIC_ORIGIN_FIXTURE` (invented IDs/intervals, counts have no empirical meaning); `AUTHENTIC_ORIGIN` only after **separate** verified legal rights/retention, authentic transport peer/origin witness, original source proof, independently attested UTC+monotonic receiver interval and durability, contract native unit/spec, versioned registry and reviewer admission; `ORIGIN_UNJOINABLE` when equality/inequality unproved; `ORIGIN_AMBIGUOUS` when contradictory. In this task the AUTHENTIC set is **empty/NOT ESTABLISHED**, *not* zero real market shocks.

**Identity demonstration:** Invent a native source-group `SYN_A[700..703]`. `R_fast` sees it at 12:00:02.100, `R_slow` sees it at 12:00:05.200. Both use one common original proof → exactly **1 hypothetical physical ID**, 2 observations. Invent `SYN_B[200..205]` with independent certified original discriminator at exactly the same timestamp as `SYN_A[100..105]` → **2 physical IDs**. Without proof of the original groups, both cases become `ORIGIN_UNJOINABLE` instead of a manufactured integer parent count.

## 2. Independent original creation vs same-lineage rearm vs policy eligibility

**Four separate state axes; no universal parent requirement for physical creation.**

**Physical-observation axis:** A newly independently witnessed source-original impulse always creates a new source-neutral `E_S` record. There is **NO requirement** that any other origin be invalidated first, no elapsed cooldown, no policy capacity test. A and B with independent native source identities at the same timestamp produce two E_S roots even if A is still CONFIRMED or a one-position BTC policy holds A. A same-source replay (different receiver or discovery rule) is an observation of A, not B.

**Lineage-rearm axis:** *Only* a claimed **same-lineage successor** needs independent **new** upstream origin proof, explicit parent-origin causal lineage, parent X invalidation/cancellation durably known before eligible rearm, and a **precommitted parent** minimum cooldown known before the parent's original policy action. `successor.first_safe_known >= parent.invalidation_safe_known + parent_frozen_rearm_cooldown`, with previously fixed structural equivalence/rearm conditions, are required for rearm eligibility. If successor C has a verified distinct physical origin but same-lineage parent still CONFIRMED or the clock fails cooldown, C **stays in E_S** with `REARM_INELIGIBLE`; its new *action opportunity* is denied, not its existence. A repeated confirmation, opposite-side flip or replay of A **cannot** constitute a new same-lineage physical origin. If source doesn't prove whether B is truly independent vs successor, flag `LINEAGE_UNDECIDABLE/NO_ACTION` rather than default to most convenient category.

**Policy cooldown/occupancy axis:** A policy may be cooling down even when B is independent. `POLICY_COOLDOWN`, `PORTFOLIO_OCCUPIED`, inability to fund size, or quote not available => per-policy `NO_ACTION`; never remove a physical B origin, parent X ledger entry or source-valid calendar slot. Independent early-X and wait-for-Z portfolio worlds evaluate the **same exogenous ordered physical origins** with different risk, holdings, NO_ACTION decisions. The design imposes one aggregate BTC active position per policy; reported hold 4–24h is prospective and **not an observed fill**.

**Cancellation/invalidation axis:** 
- `ORIGIN_IDENTITY_CANCELLED`: independent origin witness invalid, no certified E_S membership; audit receipt retained.
- `X_INVALIDATED` / `DIRECTION_UNQUALIFIED`: original physical origin remains E_S; no X action.
- `REARM_INELIGIBLE`: genuine distinct same-lineage origin remains E_S, fails rearm eligibility.
- `POLICY_NO_ACTION`: quote/risk/cooldown/occupancy/Z/clock failure; E_S and X eligibility unchanged.
- `PARENT_STATE_UNKNOWN`: cannot prove parent invalidation/first-known or safe cooldown; no rearm action.
Cancellation and later source amendments are **append-only as-known states**, never retroactively erase an already frozen earlier origin, side qualification or action slot.

**Normative cases (all hypothetical):**

| Scenario | Certified physical E_S | X-direction cohort | Portfolio entry |
|---|---|---|---|
| Independent B while A still confirmed | A and B, count 2 | Both may meet X at their own ticks | ≤1 if one occupied BTC slot |
| Distinct same-lineage C, invalidated A, frozen lockout satisfied | A and C, count 2 | C may be X qualified | Dependent on separate policy gate |
| Distinct same-lineage C, parent not invalidated / lockout fails | A and C, count 2 | C `REARM_INELIGIBLE` for action-cohort | NO_ACTION |
| Same physical A, second rule/epoch | A, count 1 | New claim on same A, not second opportunity | One fixed slot |
| Unknown physical origin proof | `UNKNOWN` certified count | `ORIGIN_UNJOINABLE` | BLOCK/NO_ACTION |
| Missing X feed/clock interval with no alerts | Latent count `UNKNOWN` | `X_SOURCE_UNKNOWN` | Never call blackout zero events |

## 3. As-known claim proof before conflict reduction; fixed time cutoff

For each source-attributed origin p, prespecified policy decision tick t and direction claim c, **first compute**:

`qualified_claim(c,p,t) := origin_identity_admissible_as_of(p,t) AND claimant_rule_precommitted AND side(c)∈{LONG,SHORT} AND witnessed_complete_bar(c) AND bar_start<bar_end<=first_complete_and_durable_UTC_hi(c)<t AND full_price_X_window_source_covered AND source_contract_units_ok AND original_origin_join_proven AND claim_state_first_known_hi<t AND invalidation_as_of_t_not_applicable AND independent_receiver_monotonic_UTC_attested`.

Use strict-before-cutoff comparison by default. A separate, explicitly attested monotonic event-order witness is required to permit equal-clock-bound events; nominal matching timestamps never establish a safe order. A 30m bar whose actual end is in the future **cannot** enter the conflict set even if `state=CONFIRMED`; a 15m period-end is not first-known. Do **not** reserve original X lineage, mark a conflicting side, or alter action-slot reservation from `FUTURE_STATE`/invalid source windows. The frozen Episode R2 code computes a nominal `simultaneous` opposing-side prepass before `_confirmed_bar_pit`; **that procedure cannot be reused** without the prequalification barrier.

**Decision-tick cutoff:** The first X-known tick and, for a delayed policy, fixed `D=ceil_scheduler(t_X+W_fixed)` are frozen by policy rule based on X-only known information, **not** on OI arrival, favorable quote, future bar/price or opposing message. A grace period/watermark is part of that precommitted tick policy and incurs a separate latency cost; never move a tick ex post so a later conflict appears simultaneous. All receiver assertions must have an independent durable-known upper bound and monotonic/UTC epoch bridge; incomparable epochs ⇒ `CLAIM_CLOCK_UNORDERED/CONFLICT_UNKNOWN/NO_ACTION`.

**Set rule:** `Q(p,t)={c: qualified_claim(c,p,t)}`. If no qualified directional claim → `NO_QUALIFIED_SIDE/NO_ACTION`. If `sides(Q)=={LONG,SHORT}` → one origin with `SIDE_CONFLICT_KNOWN_AT_T/NO_ACTION`. If singleton → eligible side subject to explicit parent-lineage rearm + policy checks, with only **one** candidate action per original policy/tick. A later opposite-side qualified message at t2>t is `LATER_SIDE_FLIP`; it may be noted and block later opportunities, **never** rewrite the earlier t action or delete its parent. Same physical origin, different confirmation frames: many claim receipts, one origin.

**Prefix/test invariants:** Reorder all independently valid same-tick input receipts; Q and the result must not change. Inject any later received opposite side, corrected OI or invalidation into an as-of-t replay; original X cohort, conflict state, action-slot key and terminal decision at t remain byte-for-byte frozen. Early-X and fixed-wait policies legitimately have different t, hence a direction singleton at t_early and conflict at t_wait **can both be correct** for their distinct policies; neither result overwrites the other.

## 4. Frozen population and estimand version crosswalk

**Never relabel `E_X^{R3}` as `E_S^{V3}` or `E_X^{V3}` without separately authenticated original event mapping and a new Controller method acceptance.** Previous R3 could contain side-bearing identity and a different confirmation/rejection population. It is not invertible into this physical-origin count from published hash alone.

| Cohort | Explicit proposed versioned definition | Counting/estimand boundary |
|---|---|---|
| `E_X^{R3}` | Old R3 price/X-only parent per its frozen source/side identity/rejection funnel | Preserved legacy target; original counts **NOT INFERRED** from V3 |
| `E_S^{V3-R2}` | All separately authenticated distinct original physical shocks observed under X-covered scheduled source intervals, regardless of direction, OI, late receipt, same-lineage rearm gate, quote, risk, occupancy | Source-neutral **physical-origin** population; maintain typed unjoinable observations separately |
| `E_X^{V3-R2}` | Subset of E_S passing **single side X-only completed/pre-known claim** and same-lineage rearm eligibility if applicable at a prespecified tick; OI/cost/quote/portfolio do not filter it | Narrower X-qualified target; side conflict, provisional and ineligible rearm remain visible in E_S X-rejection funnel |
| `C_Z^{V3-R2}` | E_X members with source-admitted consecutive unit-stable OI buckets safely first-durable-known by fixed X-derived D | Only source-selected **conditional** information population |
| `C_EXE^{V3-R2}` | C_Z with a common delayed-time X/Z-arm-independent quote/risk guard, before either arm's chosen action | Conditional diagnostic, **not** full policy or realized fill |
| `P^{R6}` | Full exogenous chronological E_S observed stream, keeping E_S\E_X as NO_ACTION and X-source blackout as separate UNKNOWN exposure | New broader early-X vs fixed-wait policy target, **not old theta_B** |
| `E_calendar^{R6}` | All scheduled UTC wall-clock slots, X-covered hours, X-blackout/censored spans, unknown possible shock exposure | Full 24/7 opportunity count unknown during gaps |

**Denominator receipts:** `N_scheduled_UTC_slots`, `valid_X_exposure_hours`, `blackout_X_hours`, `N_E_S_verified`, `N_origin_unjoinable_observations`, `N_E_X_valid`, `N_side_conflict`, `N_X_unconfirmed`, `N_rearm_ineligible`, `N_C_Z`, `N_Z_late/missing/revised`, `N_C_EXE`, per-policy eligible/NO_ACTION/occupied/intent status, and terminal source-known age. Break down by independently supported UTC week, prior-only vol state, side-or-conflict, receiver epoch. **No alert in X blackout ≠ zero market shock**; no made-up rate per 48h. Origin equivalence unknown ≠ certified 0 or certified 2; retain unknown cardinality.

**Synthetic cohort illustration only:** Assume exactly 10 physically distinct authenticated-by-fixture original shocks in fully source-covered intervals; two provisional, one same-tick contradictory side, seven distinct X-qualified, of which two have Z unavailable. Then `|E_S|=10, |E_X^{V3-R2}|=7, |C_Z|=5`. The seven-denominator conditional Z support is 5/7; the full structural source-observed count is 10. All three X-ineligible original shocks remain `NO_ACTION` in P. **Do NOT infer |E_X^{R3}| as 10 or 7** without genuine legacy source/eligibility witnesses. These numbers are not real BTC observations or economic results.

**Information estimand A, newly versioned:** `theta_A^{R6} = E[U_D(f(X,numeric_Z))-U_D(f(X)) | C_Z^{V3-R2}]`. Every arm uses the same frozen X at earliest X-known t_X, same **OI-independent** delayed D, source/quote/risk/cost rules, parent event, action clock and NO_ACTION accounting; A differs solely by source-qualified **numeric** aggregate OI Z, not by transport lag/receiver-health or later prices. `theta_A^{R6}` remains conditional, cannot be extrapolated into E_S/missing-X calendar or old R3 target. No U calculation authorized.

**Policy estimand B, new broader definition:** `theta_B^{R6}(P^{R6}) = E[V_{T}(pi_wait_Z_no_action; P)-V_{T}(pi_X_early; P)]`. The two policies ingest the *identical* source-neutral E_S chronological parent ledger; X-unconfirmed/side-conflicted/rearm-ineligible events are explicit **NO_ACTION**, and source-blackout exposure is **UNKNOWN**, not counted as observed quiet periods. Natural early X decides at its own first permissible quote/decision tick; Z policy waits until a fixed X-derived D and chooses NO_ACTION for any Z unknown or untrusted. **Different branch-specific cash, 4–24h occupancy, cooldown, quote age and nonfills are required** to eventually estimate economics, never altered E_S membership. A fallback-on-unknown policy is separately registered; do not add after outcomes. `theta_B^{R6}` is NOT `theta_B^{R3}(E_X^{R3})` or narrower `theta_B^{V3}(E_X^{V3})`. No realized fills, fees, funding, stop/ACK or terminal wealth source exists.

**Interpretation/variance:** The earlier ~one qualified opportunity per 48h is a planning objective, not a measured estimate. The proposed 20-week coverage floor and 95% cluster precision from prior design are **unobserved**, cannot be established in a 72h OI receiver QC draft; source availability may be missing-not-at-random, with joint strata having zero positivity even when marginals look adequate. Historic H32/H33/H34, R3/Goal-B/F1–F3 exposure remains in familywise multiplicity. No efficacy/novelty/alpha prereg permission from this sidecar.

## 5. Exactly one write-once action slot per origin-policy-tick

**Binding identifier** (typed and versioned, **never evidence-view versioned**):

`action_slot_key = (physical_origin_or_typed_unjoinable_seed, policy_version, decision_tick)`.

Namespace: `ACTION_SLOT_V3_R2`, unique constraint on normalized canonical tuple. `policy_version` fully identifies early-X / wait-OI / fallback (if ever separately preregistered) and fixed policy root; `decision_tick` is precommitted and may not be regenerated after a late source revision or altered quote. Each policy's original shock has a fixed permitted action-tick budget (normally 1) to prevent downstream 5m/15m/30m reconfirmation from reopening the same opportunity. Different truly independent origins have distinct keys, though one-position occupation may deny admission for B.

**Source-evidence snapshot is a FIELD, not the action ID.** At or before the fixed tick, reserve the slot in a durable write-once store and freeze `(X_version, qualified_claim_set, Z_version_or_UNKNOWN, immutable_as_known_source_view, quote_guard, side_or_conflict, policy/cooldown/occupancy_state, decision_reason)`. Required state machine: `UNRESERVED → RESERVED_PREDECISION → TERMINAL_ACTION_INTENT | TERMINAL_NO_ACTION | TERMINAL_BLOCKED_UNKNOWN`. One terminal outcome-blind decision per slot, identical result on retry, duplicate delivery or reconnect. Unknown reservation durability/cross-process race ⇒ `SLOT_STATE_UNKNOWN/FAIL_CLOSED`. No assertion of actual market orders, quote fills or money transfers.

**Late revision** is recorded as `PostDecisionSourceAudit(immutable_slot_ref, logical_source_key, new_raw_receipt_version, first_durable_known_at, relation_to_original_as_known)`, not an alternative executable action ID. Example: Z v1 first durable at 12:19:40, fixed D=12:20:05, subsequent corrected v2 first durable at 12:28. **One action slot at D with v1**; v2 must not create a second emitted action, rewrite the old Z, or alter past C_Z membership. A→B→A same-bucket reappearance **without independent provider revision ordering** ⇒ `SOURCE_VERSION_AMBIGUOUS / REVISION_ORDER_UNKNOWN` for any *uncommitted* OI-based decision, never reuse the early A's receipt clock as a new A; old terminal stays frozen. This acknowledges separate Codex receiver W04 HIGH OPEN.

**Unjoinable physical root:** Use a local typed `UNJOINABLE_SYNTHETIC_SEED` for *synthetic and forensic replay only*, not a certified count or executable real trade. If production source lacks authenticated physical origin/equivalence, freeze `TERMINAL_BLOCKED_UNKNOWN` and never issue an eligible action, even if a source string is 64 hex characters. No action admission until independent source authority.

**At-same-tick priority:** two distinct physical events may compete for one policy slot of portfolio capacity; predetermine stable **source-witness-based** priority, not input order or favorable future return. If priority is unprovable (same-order incomparable epochs), `AMBIGUOUS_PRIORITY/NO_ACTION` for competing intents; parent event count remains two. Dynamic hypothetical holds never rewrite precommitted calendar denominators.

## 6. Exact legacy crosswalk / proof obligation / noninvertibility

Episode R2 synthetic code uses `Seed.episode_id = sha256(JSON([source_identity_hash, structure_id, first_known_at]))`; `source_identity_kind=SYNTHETIC_OPAQUE_ID`; `Accounting.source_qualified=0`. Hash invertibility fails and a synthetic 64-hex value is not a venue source proof. R3 old `hash(contract_spec,X_formula,shock_start,shock_end,side,rearm_id)` may assign different IDs to a single physical root or collapse unrelated roots; without original upstream canonical evidence no correct migration exists.

**Append-only mapping receipt**: `old_contract_version, old_commit/blob, old_hash, original_source_witness_ids, new_origin_registry_version, candidate_origin_key_or_null, cardinality, proof_grade, mapping_first_known, reason`.
- `ONE_TO_ONE_PROVEN`: independently attested original source identity, clock and same upstream physical witness fully reproduce both legacy and new IDs.
- `MANY_TO_ONE_PROVEN`: multiple side-bearing/observer R3 IDs are proven to map to one independently authenticated original impulse.
- `ONE_TO_MANY_PROVEN`: if legacy really collapsed two authenticated independent origins, retain prior versioned count but **do not** retroactively split/score outcomes.
- `UNMAPPABLE_SOURCE_UNKNOWN / UNMAPPABLE_ORIGIN_EQUIVALENCE / UNMAPPABLE_CLOCK / UNMAPPABLE_VERSION / UNMAPPABLE_RIGHTS`: historical original receipt unavailable, no lawful source, ambiguous grouping, unsupported contract.
- `SYNTHETIC_ONLY_MATCH`: only invented R2 fixture equivalence and no source authorization.

Even the plausible association of two R3 hashes at the same timestamp or opposite side **does not prove** same source origin. Do not access protected old data to attempt reconstructing missing native origin records. No old outcome replay, new historical score, unblinding or restart of retired trial budget.

## 7. Invented counterexamples and expected status — NOT executed

All source IDs, sequence values, UTC timestamps and denominators below are **invented fixtures**, not actual provider observations. Positive source-authenticity flags, where mentioned, mean only fixture-assumed truth. Later independent implementer must add negative cases and real RED/GREEN under its own Controller permit.

| Case | Synthetic-only causal trace | Required contract outcome |
|---|---|---|
| **T01 rule aliases** | One original fixture native interval SYN-A [700,703], discovery `R_fast` and `R_slow` | **1 E_S**, 2 OriginObservation records, common origin key; rule ID excluded |
| **T02 receiver timestamp skew** | One SYN-A; observer A durable-safe 12:00:02.100, B 12:00:05.200 | 1 parent, 2 receiver receipts, no second physical ID; concurrent CAS same proof |
| **T03 independent simultaneous origins** | Certified independent SYN-A [100,105] and SYN-B [200,205], both at 12:00:00 | **2 E_S**, no invalidated parent needed; if X both qualified, **2 E_X** before policy |
| **T04 independent origin in occupied slot** | SYN-A position hypothetically held 12–16, independent SYN-B at 13 | 2 E_S; B not erased; one portfolio policy returns `PORTFOLIO_OCCUPIED/NO_ACTION` |
| **T05 same-lineage invalid rearm** | Distinct SYN-C successor of SYN-A, A invalidated 13:00, frozen 2h cooldown; C known 14:59 | C remains +1 E_S, `REARM_INELIGIBLE` X/action, NOT erased |
| **T06 valid rearm** | Independent same-lineage new origin SYN-C at 15:05 after A invalidation 13:00 +2h cooldown | C new E_S and eligible rearm if X safe; original A unchanged |
| **T07 side false-future invalidity** | 5m LONG bar closed 12:30, durable at 12:30:01; nominal 30m SHORT claims CONFIRMED at 12:30 but bar actually ends 12:45 | At tick 12:30:02, only LONG qualified; SHORT excluded *before* conflict prepass |
| **T08 later opposing receipt** | Same A LONG known 12:30:01, SHORT fully closed 12:30 but receiver known 12:30:07; fixed tick 12:30:02 | Singleton LONG as-of first tick; later side flip cannot retroactively conflict or rewrite action |
| **T09 fixed later conflict tick** | Same as T08, a different precommitted policy tick 12:30:10 | Both sides in Q; 1 original, `SIDE_CONFLICT_KNOWN_AT_T/NO_ACTION`; explicit wait cost |
| **T10 future-state poisoning** | Nominal SHORT `state_known_at=12:31` but tick 12:30:10; valid LONG already known | SHORT excluded, no lineage reserve, Q still LONG; prefix invariant |
| **T11 late OI correction** | SYN-A X known 12:15:02, D 12:20:05; OI v1 durable 12:19:40, v2 correction durable 12:28 | One slot, original frozen v1 at D; v2 only audit; never second action |
| **T12 A→B→A undecidable source revision** | Same OI bucket values 100, 200, 100 over three receipts, provider revision identity absent | `SOURCE_VERSION_AMBIGUOUS/NO_OI_ACTION` before commit; preserve attempts and old as-known terminal |
| **T13 duplicate across receiver epochs** | Same original SYN-A and claim delivered again after reconnect | One physical event/claim/action slot, two attempts; epoch cannot rekey |
| **T14 X blackout** | 12–13 entire X source missing, no alerts | Latent physical and trade opportunities `UNKNOWN`, NOT zero events/rate |
| **T15 legacy opaque hash** | Old R2 `source_identity_hash` = 64 repeated a characters, synthetic-kind, no raw origin proof | `SYNTHETIC_ONLY_MATCH / UNMAPPABLE`, never source admitted |
| **T16 legacy side collision ambiguity** | Old R3 LONG and SHORT hash same timestamp but original upstream discriminator absent | `UNMAPPABLE_ORIGIN_EQUIVALENCE`, no forced parent merge |
| **T17 E_S/E_X NO_ACTION cohort** | Ten authenticated-in-fixture original physicals: 2 provisional, 1 conflict, 7 directional, 2 of 7 Z missing | `E_S=10, E_X^{V3}=7, C_Z=5`, P has ten rows including 3 NO_ACTION; `E_X^{R3}` unknown |
| **T18 simultaneous physicals one action capacity** | Independent X-qualified A,B both 12:00 under a one-BTC-slot policy | 2 E_S / 2 E_X, at most one hypothetical action; other `PORTFOLIO_OCCUPIED` |
| **T19 source grouping ambiguous** | Same timestamp and partly overlapping alleged native interval with no approved source group discriminator | `ORIGIN_UNJOINABLE/AMBIGUOUS`, no certified 1-or-2 event count/action |
| **T20 crash before durable slot** | First process reserves provisional action, crashes without durable receipt, new epoch replays corrected evidence | `SLOT_STATE_UNKNOWN/NO_ACTION`, not a second emitted intent |

**Additional falsifiers:** discovery rule/receiver clock changes physical ID; independently authenticated distinct physical impulses collapse solely by equal timestamp; policy occupancy deletes E_S origin; same-lineage not yet invalidated gets new eligible action; a future invalid bar poison changes an earlier Q; late revision creates second write slot; full E_S NO_ACTION records dropped; X blackout scored zero; retrospective source reclassification, source rights not evidenced, legacy opaque hash promoted to authenticated origin. Any such weakness means `IDENTITY_DESIGN_BLOCKED` pending independent repair.

## 8. Open unknowns and independent 2-C → 1 → 0 handoff

**All real unresolved:** Does an authorized Binance native dataset even supply stable **physical impulse** group identity rather than only trades/bars? Can a scientifically and legally acceptable common origin grouping and proof exist without downstream rule bias? Real two-receiver origin attestation and CAS issuer/clock durability; current REST/WS/region/source rights, raw payload retention, contract spec, original UTC/monotonic upper bounds, source revisions A→B→A/W04, hash and parser versioning; genuine side conflict/rearm incidence and X-source missing shocks; actual E_S/E_X/C_Z effective independent coverage and joint positivity; real 4–24h execution fills, queue, stop protection ACK, signed funding, fees, terminal capital; a qualified opportunity about every 48h; after-cost alpha. **No numeric observational result or experiment is present.**

**Independent review order:** New author commit/blob verified remotely → **different 2-C** applies `prompts/v0.6/b_line/V06_R6_2C_EPISODE_V3_R2_CHALLENGE.md` at same dispatch SHA, Git blob `3ad66913a5d7dbd860f21646214de24f062076f8` → separately assigned **ChatGPT-1 consequential reviewer** after 2-C freeze → ChatGPT-0 Controller final method/source authority. No author self-PASS. Even a positive challenge verdict stays **DESIGN_ONLY**; no real source canonical ID, strategy prereg, empirical rate, Alpha, TESTNET/LIVE.

**Execution disclosure:** This author read only immutable public GitHub prompts/reports/synthetic code Git object metadata; no market API/WS data requests, no historical raw returns/PnL, no reserved or protected data/root probes, no private data/credential access, trades/accounts/funds, no production code/test/CI changes or merge. The T01–T20 invented negative fixtures are **specifications, not executed tests**. Any GitHub Actions run triggered by this docs commit must be reported with observed exact SHA/status, not manufactured or used to imply synthetic scenario coverage.

**Final proposed terminal:** `EPISODE_V3_R2_DESIGN_READY_FOR_2C_REVIEW / SOURCE_NOT_ADMITTED / G2_ALPHA_NO_GO`.
