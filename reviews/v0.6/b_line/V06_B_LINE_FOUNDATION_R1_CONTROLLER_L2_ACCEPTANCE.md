# v0.6 B-line Foundation and CI Fast Path R1 — Controller L2 Acceptance

**Decision:** `ACCEPT_V06_B_LINE_FOUNDATION_R1_ENGINEERING_ONLY`.
**Scope:** accepted Tactical/MarketWatch baseline and bounded CI Fast Path integration; **not** a Tactical RC2 strategy-quality PASS, TESTNET authorization, protected holdout retry, or LIVE deployment.

## Exact lineage
- v0.6 base: `8ecff4ec4b25bf73a35309689fd3ecfacc0d3399` (A-line H41 baseline unchanged).
- implementation commit: `abcb8fb9c975288a2579e1202a3472c80c965a8c`, direct parent base.
- executor evidence-only commit: `5706a1f6e54fbd2deb2e940119952d16c1356148`; parent implementation.
- independently applied Controller CI fail-closed rename repair: `d6500140f3141d179181f2360ad815b5bfe9c954`, parent evidence commit. Only `scripts/ci/test_plan.py` and `tests/test_ci_test_plan.py` changed, append two real hermetic rename fixtures.
- Accepted Tactical source: `52c16a28153de307dc6132c0975fe29341a0a918`; historical common ancestor `407dabc415ae8cae4210250e992941c8b9b25464`. CI candidate reference `430becb96389a62481e4d4def07065054e658eee`.
- Controller dev dispatch `9bca4d5e13084569096077ced3bb8dfc09482c1f` [frozen JSON](https://github.com/EXASHXE/btc-quant-agent-public/blob/9bca4d5e13084569096077ced3bb8dfc09482c1f/evidence/v0.6/controller/B_LINE_FOUNDATION_R1_DEV_DISPATCH_AUTHORITY.json).
- No whole-branch Tactical, Live V1 or RC2 validation merge occurred. Feature branch `feature/v06-bline-foundation-r1` is a direct descendant of v0.6 base.

## Independent verification at exact remote SHAs

1. GitHub compare base..evidence HEAD: **two commits** before the Controller CI rename repair, 42 changed paths including four append-only evidence files, **no h40/h41 source or tests modified**. Git tree blob comparisons show **35 imported Tactical files match pinned accepted source SHA exactly**. No new execution/approval/decision module imports outside accepted Tactical baseline.
2. Executor evidence [manifest](https://github.com/EXASHXE/btc-quant-agent-public/blob/5706a1f6e54fbd2deb2e940119952d16c1356148/evidence/v0.6/b_line/foundation_r1/INTEGRATION_MANIFEST.json) and [validation](https://github.com/EXASHXE/btc-quant-agent-public/blob/5706a1f6e54fbd2deb2e940119952d16c1356148/evidence/v0.6/b_line/foundation_r1/VALIDATION_RESULTS.json) claim local 314 PASS / 0 failed / 0 skipped, Planner 10 PASS; no protected reads/writes.
3. **Independent** [CI run 37731939480](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37731939480) SUCCESS on evidence HEAD `5706...`, **314 passed, 2 warnings**, mypy 129 source files no errors; Ruff and compile pass; action identifies first branch push with before all zeros and selects 17 scoped test files across full branch diff.
4. Controller discovered a narrow **CI rename bypass** missed by prior tests: `git diff --name-only` detects rename destination only, potentially treating test-to-docs or executable-source-to-docs moves as docs-only. Corrected to `git diff --no-renames --name-only`, which exposes both deletion and addition for classification. Added two **actual synthetic Git rename** regressions.
5. **Independent** [CI run 37741245947](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37741245947) SUCCESS on `d6500140f3141d179181f2360ad815b5bfe9c954`: **12 CI-planner tests PASS**, including two rename regressions; Ruff, compile, plan selection succeed. No full pytest unnecessary for two-file CI planner change.
6. Executor worktree-preservation receipt states original `/root/workspace/project/rc2-tactical-successor` stayed on validation branch SHA `1a575...` and no local file mutation occurred, while isolated sibling worktree was used. **This is executor-asserted**, not directly observed from remote by Controller.

## Admission / exclusion

Accepted for **nonprotected engineering integration** into v0.6 code only, preserving reviewed history. Controller shall use fast-forward after checking `v0.6` remains `8ecff4ec...` and feature HEAD remains `d6500140f3141d179181f2360ad815b5bfe9c954`. No cherry-pick or reconstructing commits. `v0.6` CI on resulting HEAD must be monitored as normal post-integration check.

**Persistent blockers:** RC2 Policy Quality Authority `NONE`; protected attempt original invalid development dispatch and partial target-source exposure; R1.1 validation repair `1a575...` **not** part of this merged code; distributed once-only L3 fence unproven; historical FIL/full-window approved-fixture regressions outstanding. WP-A, WP-C, WP-D package acceptance is component-specific and their cross-integration, Feishu/provider credential smoke, TESTNET E2E, Live V1 independent safety acceptance all pending.

**No release rights:** `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `LIVE_APPROVAL_ONLY=NOT_AUTHORIZED`, `AUTONOMOUS_LIVE=FORBIDDEN`, `PROTECTED_RETRY=NOT_AUTHORIZED`.

## Future mandatory executor delivery contract

All subsequent Gemini/Sol/Luna implementation and docs tasks must complete their allowed tests, proactively **commit + push to explicit feature/evidence branch**, verify remote SHA, parent and changed scope, and report `REMOTE_PUSH_VERIFIED=true`. No need for user to request push. If not pushed, return `BLOCKED_NOT_PUSHED`. No force pushes, no direct unreviewed v0.6 mutation, preserve original local checkout `/root/workspace/project/rc2-tactical-successor` via isolated worktrees. Push success is not Controller acceptance.

**Next:** controller-owned engineering-only B-line WP-A/WP-C/WP-D integration planning, governed by accepted component exact SHAs; separately work on protected retry L3 fence and strategy evidence, no auto-promotion.
