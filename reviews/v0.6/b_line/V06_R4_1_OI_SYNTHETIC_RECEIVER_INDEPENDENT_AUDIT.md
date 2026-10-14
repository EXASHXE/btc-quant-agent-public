# ChatGPT-1 — Independent Exact-SHA Synthetic OI Receiver/PIT Witness Audit R1

**Terminal verdict: `SYNTHETIC_WITNESS_FAIL` — diagnostic completeness defect; real source/PIT admission remains correctly impossible.** The 2-E two-file invented-only implementation is cleanly frozen, no forbidden network/collector side effects were found in its module, and the actual exact-SHA Python 3.12 full CI is **3014 passed / 0 failed / 2 skipped, no deselection** with 35 new synthetic cases. Nevertheless, independent adversarial inspection identified an **unclosed source-window completeness check**: arbitrarily tiny X/QUOTE/OI intervals disjoint from both required OI 15m periods can still yield `SYNTHETIC_TIME_COHERENT_NOT_ADMITTED`. Further, the JSON decoder silently accepts duplicate keys and first-known evidence is not explicitly constrained to the period end. These are **model/diagnostic soundness defects**, not proof that real source data has been accepted: `evaluate_two_buckets` universally returns `PIT_UNKNOWN/SOURCE_NOT_ADMITTED`. Do not confuse failure of the synthetic witness specification with authorization or any observed market incident.

**Role/date:** ChatGPT-1 Independent Supervisory Auditor, not the ChatGPT-2-E code author or Controller, 2026-10-14 Asia/Singapore. Frozen GitHub source/module/test files and real Actions logs/JUnit/receipt inspected independently; constructed invented attack inputs and executed the exact source-span guard predicate and Python JSON duplicate-key behavior in an isolated offline sanity check. **An independent invocation of the frozen Python module's pytest suite was NOT performed** because exact source files were available through the GitHub connector but not independently materialized as an executable local checkout. Distinguish this static/expression witness from the real author CI. No market data, protected files, private paths, funds or orders.

## 1. Frozen authority, exact source identity and no-scope-violation evidence

| Object | Independently verified identity |
|---|---|
| Controller exact review dispatch | **`3e8ea27604574c63caf43b5e6d4bff7feb979908`**, `prompts/v0.6/b_line/V06_R4_NEXT_1_SYNTHETIC_RECEIVER_INDEPENDENT_AUDIT.md`, Git blob **`aae8ab73ec7cc6be3cb984c4fee49734dbf77d40`**. |
| 2-E implementation exact frozen SHA | **`2320c59ad7b324cdf3947826e82e042d8be38ddc`**; Git **direct parent `13e3a710b137efeec2e21e3002f748834ec0cc22`** (the authorized clean code base). Remote `feature/v06-r4-2e-oi-synthetic-witness-r1` HEAD equals frozen full SHA. Git compare **ahead 1 / behind 0**, **exactly two ADDED files**, no other modifications/deletions/renames. |
| Source module ADD | `scripts/strategy_research/g2_oi_pit_synthetic_receiver_witness_r1.py`, **Git blob `a056e3a4653bb84363120a61e20b7e9245af64e5`**, **292 lines**. |
| New pytest ADD | `tests/test_v06_g2_oi_pit_synthetic_receiver_witness_r1.py`, **Git blob `221f36f97167ebba4342e4af88d19393b42e5b6e`**, **315 lines**. |
| R3 scientific design | 2-R **`35c269aecf0f1b756575af2ac5e355f2cf53757c`**, doc blob `56482b2ce305071d5a5fb3b3e19468fb1b33a828`; 2-C independent challenge **`a1e9632a30f330041bcffb22c2ba3d3d656963bc`**, blob `2d4878df19c08b72ae1572c6cbbd0d7647ef57e3`. Consequential independent ChatGPT-1 R3 audit **`371a0c7160cf2da6685a3588d7b9a48c686443c8`**, `R3_CAUSAL_DESIGN_PASS_WITH_LIMITS`, source still blocked. |
| Actual CI | [Actions **`38583469127`**](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38583469127), head exact **`2320c59a...`**, event **push**, Python 3.12 quality job **`115919142375` SUCCESS**, compatibility manual full job **SKIPPED**. |

Both source/test files were fetched by exact commit path and independently by the corresponding exact Git blob. No software integration into Episode/G1/P1D, live exchange adapter, CI planner, H40, protected golden, existing research data, persistent recorder, network or filesystem recording is in the two-ADD diff. The module itself imports only **json, dataclasses, decimal, hashlib, typing** and has no provider/system clock, socket or file persistence entrypoint. Its test's import-AST negative, and external code review, agree with that restricted surface. Its `ClockWitness.synthetic_signed` and caller-provided `origin_receipt/rights_receipt` do **not** grant real rights; all emitted `Verdict` values are hardwired to `PIT_UNKNOWN`, `SOURCE_NOT_ADMITTED`, `SYNTHETIC_ONLY`. That protective boundary is sound despite the synthetic diagnostic bug.

## 2. Real CI artifact and exact execution evidence — genuine but incomplete tests

**Direct job log** on exact SHA: `PROFILE full CMD ['pytest','-q','--durations=20','--junitxml=ci-junit.xml']`, **`3014 passed, 2 skipped, 9 warnings in 880.20s`**, exit 0. Ruff and compile checks passed; no H40 node deselected in this OI run. This establishes a real Python 3.12 **`FULL_REPO_PASS`** on the frozen code, *not* actual origin admission and not independent repeated pytest.

**Machine artifact independently downloaded and opened**: artifact ID **`11905246074`**, `b-line-test-receipt-2320c59ad7b324cdf3947826e82e042d8be38ddc`, metadata SHA-256 digest **`sha256:742e95dabac90622f3e12b56f62f2d56a657e52884f0fdcb4215665d3051ee78`**. It contains **`ci-test-plan.json`** and **`ci-junit.xml`**. JSON `code_sha=tested_sha=2320c59a...`, `event=push`, `profile_executed=full`, `returncode=0`. Independently parsed JUnit: **3016 testcases**, **3014 passing / 0 failed / 0 errors / 2 skipped**. **35 specifically named testcases** from the new 2-E receiver synthetic file were present and passed. On this new-branch push `before=000...000` and the planner's general `changed` covers many diffed repository paths; immutable candidate commit scope is independently established by Git compare, not by assuming the branch-creation risk-plan changed list is the commit diff. `protected_reads=0` is **self-reported**, not independent protected-I/O telemetry.

The two skipped legacy tests require a non-protected local `ETHUSDT.parquet` omitted in remote CI and are unrelated to OI source legitimacy. A full test PASS says those 35 selected fixtures passed, **not that all adversarial source-window contracts were exercised**. No actual RED-before-fix run is claimed; the author task did not require a RED receipt if none existed.

## 3. Independently constructed negative cases and causal contract

### OI-W01 HIGH — required price/quote/OI windows are NOT proven to cover the underlying two-bucket decision

**Frozen source:** `EvidenceSpan` defines `source,start_ms,end_ms,missing,censored` (module ~L111–L117). In `evaluate_two_buckets` (~L250–L292), the whole coverage check is:

```python
if any(span.start_ms >= span.end_ms or span.end_ms > decision_ms
       or span.missing or span.censored for span in evidence):
    return stop("SOURCE_GAP")
if {"X", "QUOTE", "OI"} != {s.source for s in evidence}:
    return stop("SOURCE_GAP")
```

This only checks that at least one nonempty, nonmissing interval of each *label* exists and ends by decision. **It does NOT enforce intersection/coverage with the actual X feature window, quote decision clock, newest/prior OI 15m periods, either underlying source bucket or missing/censored subsegments.**

**Independent invented counterexample with exact caller-level values:**
- Existing test's `END=3_600_000`, `PERIOD_MS=900_000`, `DECISION=3_800_000`. Construct the new test's **valid two-bucket synthetic `state=pair()`**; its two OI bucket ends are **2_700_000** and **3_600_000**, and original invented ACK-known times from the existing helper are **3_700_007 ms**, before D.
- Instead of the existing `evidence()`, provide `evidence=(EvidenceSpan("X",0,1), EvidenceSpan("QUOTE",0,1), EvidenceSpan("OI",0,1))`, all with `missing=False,censored=False`; pass existing fake nonempty rights/origin strings.
- The exact boolean span guard returns **FALSE (no SOURCE_GAP)** and the source-label set check passes; both frozen synthetic bucket versions are time-known by D. Therefore the function's subsequent branch yields **`diagnostic=SYNTHETIC_TIME_COHERENT_NOT_ADMITTED`**, `selected_versions` length 2, **even though every claimed contributing evidence interval was merely 1 ms at 0–1, and the entire required 15m bucket / decision quote exposure is unproven**.
- Independently executed the *identical boolean predicate* over these invented values in an offline Python mini-check: `actual_guard_blocks=False`, `full_window_covered=False`, `latent_gap=True`. **This is not a claim that the exact frozen module was dynamically run locally**. The output status still reads `PIT_UNKNOWN/SOURCE_NOT_ADMITTED` by design, so no authentic data was admitted. The bug is specifically the false positive **synthetic time-coherent/source-window diagnostic** and missing **E03-like full-window negative**.

**Required correction:** Fix the source-neutral X/quote/15m-OI *contributing interval identities* and explicit coverage/exposure masks: confirm both completed OI buckets' full relevant source-observation intervals, their source-specific receipt ages and quote known-at at decision, matched underlying X confirmation interval, gaps/censor spans and no out-of-window fake interval. Explicit zero/short/disjoint window tests must result `SOURCE_GAP/SOURCE_EVIDENCE_UNKNOWN`, not `SYNTHETIC_TIME_COHERENT_NOT_ADMITTED`. Keep final `SOURCE_NOT_ADMITTED` always. A valid *set of labels* does not prove a valid *set of source-time witnesses*.

### OI-W02 MEDIUM — duplicated JSON keys silently accepted by ordinary parser

**Frozen source:** `_decode` (~L119–L150) invokes `json.loads(a.raw_body)` without an `object_pairs_hook` rejecting duplicate object member names, then checks only the final collapsed `dict` keys. An invented payload with two `"sumOpenInterest"` keys, e.g. `"sumOpenInterest":"1"` followed by `"sumOpenInterest":"999"` in the same correctly shaped body, will silently yield quantity **999** under Python's standard JSON parser even when the SHA/length over that raw payload match. The existing `test_13` decoder negatives cover malformed/empty JSON but not duplicated members; a normalized value with ambiguous source bytes is not a trustable literal decoder contract. **Independently executed Python `json.loads` against such an invented payload and observed the later duplicate key wins**; source module branch inspection shows no duplicate-key check.

**Required correction:** strict duplicate-key rejection (and deterministic numeric string bounds, canonical source-content parsing) with an explicit synthetic negative. Do not equate successful hash of ambiguous bytes with authenticated data or permit a duplicate raw object to define a valid version. This does not imply any real exchange sends duplicate keys; it is a negative fixture.

### OI-W03 MEDIUM — receiver first-safe time can precede its own claimed OI period end without fail-close

`ClockWitness.safe_upper` computes an invented `anchor_utc_upper_ms + ceil(monotonic elapsed)+drift`. `append_attempt` accepts a valid `_decode` period key and sets `first_known_at_ms=safe` without checking **`safe >= provider_period_end_ms`** or applying R3's `K(v)=max(period_end_safe, durable_receiver_upper_safe)` for its metadata. `evaluate_two_buckets` does check `period_end < decision`, so it does **not** admit a future bucket at a decision before its end; nevertheless, it could report an impossible `first_known_at_ms` earlier than that bucket's completed period end and later call it `SYNTHETIC_TIME_COHERENT_NOT_ADMITTED` once the decision is after period close. The receiver's internal epistemic timestamp claim is therefore not self-consistent for such invented clock envelopes.

**Required correction:** explicitly enforce a consistent period-complete-before-receiver-known upper bound, or fail `CLOCK_UNKNOWN/PERIOD_RECEIPT_ORDER_UNKNOWN` for physically impossible receipts; independent counterexample with synthetic clock anchor earlier than period end. Still no provider publish-time backfill or real admission.

### OI-W04 ACCEPTED — useful fail-closed synthetic features remain valid

- The module never exposes source/PIT admission; fake signed flags, claimed raw 64-hex digest, placeholder chrony/rights/origin evidence do not change this terminal boundary.
- Header-only/incomplete/truncated/invalid digest and missing fsync ACK result in no version; delay-safe known-at includes durability ACK upper bound. In particular after-body before-fsync receipt is **not** treated as usable by D; missing or same-boundary source is rejected. Real durable fsync and clocks remain caller-invented, not independently attested.
- Duplicate exact bytes and normalized numeric values attach to earlier append-only version identity; later numeric correction appends a fresh version without overwriting earlier receipts; explicit integer sequence replay permutation is deterministic in the supplied fixture. These are testable invented state semantics, **not proof of true append-only storage, authenticated clock, signed source or legal rights**.
- Clock epoch mismatch, wall rollback, synthetic source gaps, 418/429 stop and unknown contract/unit/parser reject in the tested negative paths. No actual exchange request or new data collection occurred.

## 4. Consequential terminal and next bounded task

**Reason for FAIL despite full green CI:** the task specifically requires independently attacking **required source-window completeness** and decoder/PIT source credibility. The two-ADD module's synthetic `SYNTHETIC_TIME_COHERENT_NOT_ADMITTED` outcome overstates its validated contributing-source timeline; OI-W01 is a deterministic counterexample against that central diagnostic. The module's unconditional **`SOURCE_NOT_ADMITTED` safety guarantee remains effective**; this is a **scientific witness completeness defect**, not evidence of unsafe live trading or a broken source-admission permission, because no such permission exists. The exact CI genuinely passed all existing tests but **did not test the uncovered condition**. OI-W02/W03 also require negative fixtures before any potential wider integration.

**Permitted action here: only independently publish this report.** Under a *new separate* Controller exact-SHA corrective dispatch, request an outcome-blind invented-only R2 repair limited to the two file paths: implement source-span coverage, strict duplicate-key decoding and period-end/first-safe consistency, then add reviewer-originated failing-before-fix negatives and full head-equal RED/GREEN/CI evidence; independently challenge again. No self-granted integration or direct modification of the 2-E frozen proof.

**Explicit persistent gates:** `SOURCE_NOT_ADMITTED / HISTORICAL_2021_2023_OI_SOURCE_NOT_READY / NOVELTY_CANDIDATE_SOURCE_BLOCKED / G2_ALPHA_NO_GO / TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. No 72h source-QC/collector authorization, actual rights verification, historical outcome replays, signed venue witness, fee or Alpha/frequency assertion, release or branch merge.

**Publication scope:** **ADD ONLY** `reviews/v0.6/b_line/V06_R4_1_OI_SYNTHETIC_RECEIVER_INDEPENDENT_AUDIT.md` on independent `docs/v06-r4-1-oi-synthetic-receiver-audit` rooted at Controller dispatch **`3e8ea27604574c63caf43b5e6d4bff7feb979908`**. Report exact new Git commit/blob/parent and sole-file diff after remote publication. No changes to 2-E code, tests, source selection, CI, safety guards or protected results.

**FINAL: `SYNTHETIC_WITNESS_FAIL` (invented-only diagnostic soundness); `SOURCE_NOT_ADMITTED` always.**