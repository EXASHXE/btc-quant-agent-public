# v0.6 B-line G2 R3 — Controller executor reassignment for ONE final independent engine audit

## Binding Controller execution reassignment

**Decision: `REASSIGN_PENDING_FINAL_INDEPENDENT_B_ROLE_TO_GPT6_SOL_HIGH__PRESERVE_SAME_ONE_SHOT_AUDIT_AND_START_SHA`.**

This action **does not** revoke prior audit scope, reset A/B, restart an audit, authorize any coding fixes, or preaccept P1. It changes only the **executor model** of the currently unstarted final adversarial reviewer from Gemini B to **GPT-6 Sol High** (or best available deep-reasoning Sol High setting if the Codex environment exposes it). Sol occupies the **independent B VERIFIER role** and may not self-accept. ChatGPT-0 remains Primary Controller and performs final L2 source/evidence adjudication.

### Identities verified before reassignment

- Repo: `EXASHXE/btc-quant-agent-public`.
- Reuse **already-created, still clean remote audit branch**: `feature/v06-bline-g2-r3-p1-alt-engine-final-independent-b-r1`.
- Exact **audit branch START/remote HEAD**: `ed9dc16f3dbeaada88806b69ad032526886a2ae4`, reverified as unchanged at reassignment. The original audit authorization was published at the same commit. New role reassignment authorization is a **different docs-only Git SHA** in `v0.6-docs`; do not expect it to be the worktree HEAD. Link and verify it separately.
- Immutable audited A SHA: `164243b770f74f98876b55a7f070b1adf2f554d5` (no A commit drift).
- Original one-shot B source/evidence audit authority SHA: `ed9dc16f3dbeaada88806b69ad032526886a2ae4`.
- Original detailed audit prompt SHA: `18ad412969e224bb19e56d77444c23f766b367f6`, [original audit contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/18ad412969e224bb19e56d77444c23f766b367f6/prompts/v0.6/b_line/V06_G2_R3_P1_ALT_ENGINE_FINAL_INDEPENDENT_B_SOURCE_AND_RUNTIME_AUDIT_R1.md). All behavioral tests, output allowlists, exact T01–T34 expectations and protected-data fences remain IN FORCE except where a new pinned Sol execution prompt explicitly refines the proof order and executor role.
- Accepted AM01/AM02 prospective semantic contract `821d23427a5f6d0b4635f32f226ddc779358ab72`, Sol design oracle `c0b41d1ce62e0fe852edfc6e162f1bc3dc6dcc01`, original 8 formula root `e5b2006a89441f7eb2ec900e508aff451106b87a`.
- A GitHub CI 37949429222 actually failed inherited H40 SHA golden (2819 pass / 1 fail / 2 skip). This alone is separate from semantic verdict. A reports 35/35 self-tests on Python3.12/3.13; unverified independently.
- There is NO preexisting audit report/commit on the B branch to discard. Do not create another B branch, change A's source, or repeat the same audit in parallel under Gemini.

### Why Sol and not Controller alone

The independent verifier needs **actual isolated runtime execution**, test-case construction, source import identity validation, and the ability to commit/push machine receipts to the dedicated B branch. The Controller can source-review remotely and adjudicate but should not be the only party both generating an oracle and accepting it. Sol High handles exact-source execution and adversarial runtime investigation; Controller independently verifies and adjudicates its pushed evidence.

### Critical independent science/engineering gates

1. **G1**: `ReplayEngine.run_simulation` (not a unit helper) must produce nonempty real 4h BASE/STRESS winning/losing synthetic trades and 12h BASE known fixed-schedule trades, each with trade identities and independent journal/cash/net fee/funding accounting. Current A tests T28/T29 assert no nonzero-trade condition; do not infer zero without actually running.
2. **G2**: A `money.py::assert_invariants` unconditionally returns True for I07 and I09–I17. Verify if separate event-level enforcement actually covers ALL originally frozen I01–I17 in public runtime; don't count loops incrementing invariant names. Independently inject illegal settlement, cooldown reset, Mark future, partial-exit sum and ACK mismatch to falsify.
3. **G3**: Frozen R1.1 requires each of eight candidates and BASE/STRESS scenario to have **independent 1000-USDT books**. A source uses `book_id=config.cost_scenario.value`; run A solo, B solo, A+B combined with candidate order permutations and a kill/loss witness, and compare equity/trades, not only static text.
4. **G4**: A handoff has wrong equations vs R1.2; distinguish documentation defect from actual `money.project_as_of` runtime formulas. Frozen Controller method wins.
5. **G5**: A terminal boolean omits pending ACKs, fees/receivables and cash-to-net. Check honest terminal state, 240h warmup and all tails, financial owner tombstones until obligations finalize.
6. Review complete T01–T34 audit obligations, prioritizing causal/source-provence and conservative funding/risk. Stop early on a **reproduced material** semantic blocker and document unrun cases as NOT_RUN, not PASS. No 15-minute global CI rerun if inherited H40 is already characterized.

### Exit

One of exactly `ALT_ENGINE_B_TERMINAL_NO_GO__STOP_ENGINE_CAMPAIGN`, `ALT_ENGINE_B_SEMANTIC_ACCEPTABLE_FOR_CONTROLLER`, `ALT_ENGINE_B_EVIDENCE_INCOMPLETE__NO_PROMOTION`, `BLOCKED_IDENTITY_OR_SCOPE`, `BLOCKED_NOT_PUSHED`. For NO-GO no automatic new engineering fix task, no endless patch/re-audit loop. For ACCEPTABLE, only Controller can accept engine, still no P3/P4. Sol independently authors evidence/test scripts within the original B-only allowlist, pushes non-force, verifies actual remote SHA parent, changed-path list and real CI. Original 8 strategies/positions/market source data must not be accessed except synthetic input.

### Scientific gates

`P1_ENGINE_ACCEPTED=NO`; `P2_SOURCE_ADMISSION=LOCAL_ROOT_UNKNOWN`; prior Sol science `SCIENCE_READY` only restricted proxy development; `P3_FIRST_PUSHED_PREREG=NONE`; `P4_MARKET_DATA_BODY=NONE`; `TESTNET=NONE`; `REAL_FUNDS_WRITE=NONE`.

**The next frozen Sol High execution prompt** is separately published in `v0.6-docs`, its immutable SHA is included in the invocation. Its `CONTROLLER_DISPATCH_SHA` is the Git commit publishing THIS reassignment decision, NOT this uncomputed document content hash.
