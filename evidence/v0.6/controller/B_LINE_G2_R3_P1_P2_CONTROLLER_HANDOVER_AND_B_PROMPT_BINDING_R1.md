# B-line v0.6 — P1/P2 Controller handover and Gemini B prompt identity correction (2026-10-09)

**Type:** immutable docs-only Controller identity correction and bounded P2 disposition; **NOT** an engine acceptance, preregistration, data-body admission, TESTNET or trading grant.

## Exact verified inputs

- Code baseline `v0.6@e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`.
- Docs parent for this correction: `v0.6-docs@be92966f4f0c8f0f152204973e4296ac5d5cd405`.
- Gemini A repaired exact source target `5c542edd418a74b440162610fd540b1f01e423d3`, parent `2f0383816127cb7d87cf5deb559aeda0b04f1624`. [Focused CI 37875087577](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37875087577) completed SUCCESS, not independent behavior PASS.
- Gemini B existing branch `feature/v06-bline-g2-overnight-verifier-b@a0aacd105ac3f3173b15d91c869990748178e222`; no subsequent remote deliverable at review.
- Original immutable B authorization `3fb4508110c031eb0ff9226a7e42d918684c554f` includes [dispatch JSON](https://github.com/EXASHXE/btc-quant-agent-public/blob/3fb4508110c031eb0ff9226a7e42d918684c554f/evidence/v0.6/controller/B_LINE_G2_R3_P0_B_INDEPENDENT_REAUDIT_R1_DISPATCH.json). However the corresponding Prompt file is **absent** at that SHA (404), and only occurs in later docs commits. Therefore the original pinned Prompt URL must **not** be used or represented as fetched.
- Exact immutable prompt for the **same already-authorized B review scope**, now bound to [v0.6-docs@be92966f...](https://github.com/EXASHXE/btc-quant-agent-public/blob/be92966f4f0c8f0f152204973e4296ac5d5cd405/prompts/v0.6/b_line/V06_G2_R3_P0_GEMINI_B_INDEPENDENT_REAUDIT_R1.md), Git blob `b0c17854fd7605dfb508acd319af1535d8707d82`. Compare against the original dispatch JSON and this correction; this is a binding repair, **not a new A/B repair cycle**.

## Controller dispatch binding correction — no scope expansion

`CONTROLLER_DISPATCH_SHA` for this **corrective publication** is the real Git commit containing this document, to be provided as the full immutable Git SHA after push. This SHA is not precomputed, and the old `3fb45081...` remains the **original** dispatch identity rather than falsely claiming its absent Prompt existed. Verify this committed document, the original JSON at `3fb45081...`, and the Prompt blob at `be92966f...` before work; any mismatch is `BLOCKED_AUTHORITY_IDENTITY`.

Executor: existing Gemini B verifier only. TASK_ID remains `V06_G2_R3_P0_B_INDEPENDENT_REAUDIT_R1`. Original B branch and worktree are reused unchanged: `~/workspace/project/quant-v0.6/g2-overnight-verifier-b`. Start from B exact SHA above. Review A exact SHA above using **independent, executable synthetic interaction tests**, not only static AST or A-owned regression tests. Keep A01–A08 scope, eight original candidates, fill ACK/economic lifetime, 4h/12h, PIT/mark availability, reserve/cash/funding, state separation and all negative cases. The [bound Prompt](https://github.com/EXASHXE/btc-quant-agent-public/blob/be92966f4f0c8f0f152204973e4296ac5d5cd405/prompts/v0.6/b_line/V06_G2_R3_P0_GEMINI_B_INDEPENDENT_REAUDIT_R1.md) supplies the exhaustive original allowlist, test matrix and terminal receipt schema. This correction **does not** authorize changing its scope, making a second B branch, editing A, accessing actual market bodies or replaying protected outcomes.

B auto-commits, non-force pushes to its **existing** authorized branch, then verifies remote HEAD/parent/files/test evidence. Terminal state must be one of the original B Prompt vocabulary, with corrective SHA, original dispatch SHA, bound Prompt ref/blob, exact A SHA and B final remote SHA. No extra full-suite run unless a behavior finding warrants it. After B delivery, Controller performs L2 adjudication; **no P1 acceptance prior to that event**.

## Controller disposition of P2 Sol report (bounded)

Read [Sol terminal decision at 7f96369b...](https://github.com/EXASHXE/btc-quant-agent-public/blob/7f96369b1209ffdaca5d7f1233c2c9c0ae17ae29/evidence/v0.6/b_line/g2_r3_data_readiness_fastpath/DATA_READINESS_DECISION.json): `LOCAL_ROOT_UNKNOWN` is an accepted **evidence limitation**, **NOT** physical-source absence, source-body authorization or scientific admission. Its 67-month BTC / 2,934,720-row manifest is metadata-only. ETH/SOL historical provenance, true 1m marks, funding/fees/slippage and licence are not admitted.

**P2 choice / stop-loss:** Do **not** commission further open-ended root discovery. First allow **one operator-supplied exact canonical absolute dataset root** (or existing explicit static binding). The future executor is limited to a dedicated authorization for lstat on the **six already named** nonprotected BTC March/April 2021, 2023 and 2025 relative paths; no global walking, no body read/hash, no old holdout contact. If no exact owner root is supplied, **terminate local-reuse metadata discovery**, choose one separately frozen finite replacement-source admission or stop. Do not silently promote BTC-only data to the original three-symbol scientific-quality contract; BTC-only is DIAGNOSTIC_ONLY unless prospectively redesigned and re-authorized. No replacement download/source test occurs under this document.

The old BTC `[2026-02-01,2026-08-01)` FINAL HOLDOUT stays PROTECTED/DISPUTED; old R2 exposure does not release it. Option A (March warmups/April developmental slices 2021/2023/2025) remains **proposed, not selected**. No effective `FIRST_PUSHED_PREREG_SHA`; no real price/funding/mark body access.

## Next gates

1. **Gemini B:** complete the **already dispatched** bounded P1 exact-source dynamic re-audit under this corrected prompt identity. P1 stays `AWAITING_B_INDEPENDENT_BEHAVIOR_EVIDENCE`.
2. **Owner/Controller P2:** either bind one exact canonical local root for a separately authorized six-path metadata check **or explicitly abandon local reuse** and select a single bounded source-admission fallback. P2 stays `LOCAL_ROOT_UNKNOWN__NO_SOURCE_ADMISSION`.
3. **Controller P3:** only after both P1/P2 closure, publish/verify eight-candidate first-pushed prereg SHA **before** a distinct authority permits selected-development historical data-body reads.
4. P4 diagnostic developmental replay and P5 independent validation / engineering TESTNET remain downstream, not implied here.

**Permissions remain:** `EMPIRICAL_PRICE_BODY_AUTHORITY=NONE`; `G4_TESTNET=NOT_AUTHORIZED`; `LIVE_APPROVAL_ONLY=NOT_AUTHORIZED`; `REAL_FUNDS_WRITE_AUTHORITY=NONE`; `AUTONOMOUS_LIVE=FORBIDDEN`.
