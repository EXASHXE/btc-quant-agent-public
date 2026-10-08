# V06 B-line G3 — Operational Readiness R1, Linux 3.12, mock runtime + optional nontrading provider smoke

**TASK_ID:** `V06_B_LINE_G3_OPERATIONAL_READINESS_R1`
**CONTROLLER_DISPATCH_SHA:** `ba60efc078e9bb75bdc728e8875ba48fb69d1752` — [Controller immutable operational-only authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/ba60efc078e9bb75bdc728e8875ba48fb69d1752/evidence/v0.6/controller/B_LINE_G3_OPERATIONAL_READINESS_R1_DISPATCH.json)
**START_SHA:** `a56cc413d87a71111f2be02f10052dced9ff0275` (G1 two-parent merged v0.6).
**TARGET_BRANCH:** `feature/v06-bline-g3-operational-readiness-r1`.
**NEW DEDICATED WORKTREE:** `/root/workspace/project/quant-v0.6/g3-operational-readiness`.
**Owner:** Gemini (engineering), Sol optional novel safety semantics review; Luna can run mechanical tests only.

## Gate 0 — Wait for verified integration CI success (no work if blocked)

Read exact [v0.6 merge CI run 37778010147](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37778010147). **If status is not `completed` and conclusion is not `success`**, STOP `G3_BLOCKED_BY_POSTMERGE_CI` and return current URL/status. No reinterpretation of a PENDING/FAIL result as success. Do not retry full tests, ignore failed cases or edit mainline. Verify the remote `v0.6` branch HEAD is still exactly `a56cc413d87a71111f2be02f10052dced9ff0275` (if changed, require new Controller baseline binding, do NOT silently adopt new commit).

Do not touch existing original `/root/workspace/project/rc2-tactical-successor`, G1 `g1-engineering-preview`, G2 R1 `g2-strategy-discovery`, G2 R2 `g2-perp-reconstruction-r2`, or `controller-review`; never clean/stash/reset/move/delete any pre-existing worktree. G3 uses a separate feature branch starting from exact merge SHA with:
```bash
ENTRY=/root/workspace/project/rc2-tactical-successor
WT=/root/workspace/project/quant-v0.6/g3-operational-readiness
BASE=a56cc413d87a71111f2be02f10052dced9ff0275
# read-only: validate actual remote URL identity, v0.6 HEAD, branch collisions, worktree registry, ENTRY state
git -C "$ENTRY" worktree list --porcelain
git -C "$ENTRY" rev-parse HEAD
git -C "$ENTRY" status --porcelain=v1 --untracked-files=all
# only if safe/unused:
git -C "$ENTRY" worktree add --no-track -b feature/v06-bline-g3-operational-readiness-r1 "$WT" "$BASE"
cd "$WT"
test "$(git rev-parse HEAD)" = "$BASE"
```
Do not switch ENTRY branches, clone into ENTRY or touch another task's local artifacts. Stop on any existing branch/worktree ownership ambiguity. No network credential scraping, secrets logs, .env copying or prohibited source access.

## Mission and explicit NON-authorities

G1 Engineering Preview established a synthetic/offline DRY_RUN chain; G3 validates the **deployment and operational lifecycle** independently:
- Linux/POSIX single canonical Python 3.12 process startup/config readiness;
- serialized SQLite schema migration/initialization and cold start with concurrent startup rejection (fcntl where supported);
- durable transaction receipts, approval callback duplicate/replay/stale expiration, expected on-restart PositionSupervisor recoveries and one-worker fencing;
- deterministic fail-closed behavior for missing provider, missing Feishu, stale quotes, account reconciliation, corrupt store, SIGTERM and no valid approvals;
- **OPTIONAL** isolated real OpenAI/Feishu provider *non-trading smoke*, only if test-only credentials are explicitly provisioned and operator sets a narrow enable flag; otherwise `EXTERNAL_SMOKE_NOT_RUN_NO_TEST_CREDENTIALS` without pretending PASS.

**Absolutely forbidden:** live signed Binance, account balances/API keys or trading, TESTNET signed orders, real-fee execution, RC2 protected targets, A-line/H40/H41 science outcomes, overriding execution authority, real funds or unsupervised trade prompts. `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `TESTNET=NOT_AUTHORIZED`, `LIVE_APPROVAL_ONLY=NOT_AUTHORIZED`.

**This task is a G3 engineering evaluation, NOT implementation repair authority.** Allowed new files only:
`tests/test_v06_g3_*.py`, `scripts/ops_g3/**`, `docs/operations/g3/**`, `evidence/v0.6/b_line/g3_operational_r1/**`.
Existing `src/**`, G1 Live/MarketWatch/Tactical, Docker/compose, shared CI, pyproject, controller evidence and protected archives are **READ-ONLY**. If necessary fixes are found, record concrete reproducible BLOCKER/HIGH issue and stop rather than expand scope or edit signed-client/runtime safety paths without new dispatch.

## A. Deterministic operational evaluation first (zero providers)

On authentic **Linux Python 3.12** (GH-hosted Ubuntu is acceptable for hermetic tests; WSL/Windows alone is not evidence of a production native Linux deployment), validate exact interpreter/runtime dependencies, config parsing, single-worker launch, startup output, health/readiness contract and file permission boundaries. Use unique temporary data root under `/tmp/v06-g3-r1-<pid>`, never production database or credential paths.

Test matrix:
1. 2 parallel initializer processes on same DB path: deterministic elected single canonical runtime worker, failed/blocked second, no half-built migrations or duplicate outbox dispatch. **Do not** call this proven if app permits two writers.
2. Cold start + SIGTERM + fresh restart after a durable pending approval and simulated paper fill/stop. Assert transaction deduplication, unbound/unapproved intents never convert into order, no orphan positions, correct PositionSupervisor transitions, and recovery preconditions; if inflight write interrupted, fail closed.
3. Unexpected death at selected legal transaction checkpoints using synthetic fault injection; recreate process and reconcile expected persistent receipts, no double dispatch/no missing protective simulation, no unlocked kill state. Avoid modifying actual runtime module for injection.
4. Two identical callbacks, differing replay event, stale approval, forged case/proposal hash, wrong approver identity, expired TTL, unsupported environment, loss of provider and invalid or missing market observation. Confirm **zero** signed exchange writes, mocks record no side effects for invalid grants.
5. Segregate DRY_RUN/TESTNET/LIVE configs, mainnet credential preparse rejection. The test harness must not instantiate a signed Binance client or read any actual existing key material. Verify `LIVE` mode hard-disabled.
6. Startup service patterns: one-worker uvicorn only; no Gunicorn multi-worker or speculative auto-scale. Docker/Compose startup *static lint and optional ephemeral no-credentials local container*; if Docker permissions unavailable, report `CONTAINER_NOT_VERIFIED`, don't pretend full deployment.
7. Resource and performance: record realistic tiny-fixture startup duration, migration time, cold recovery time and steady memory on tested Linux environment; not a trading signal throughput benchmark. Reproducible machine receipt with exact SHA, Python 3.12, OS, sqlite version, deps hash, selected test targets and elapsed.

Keep tests independent of external networks and protected files. Avoid reopening already accepted broad tests unless a *specific changed source behavior* actually requires it. No repeated repository-wide pytest; full release regressions once at G4 authority boundary.

## B. Optional real provider/Feishu *nontrading* smoke

Provider smoke may run only when:
- Operator independently supplies **dedicated test-only credentials** via secure environment at execution time AND explicitly enables it (e.g. `BTC_QUANT_G3_EXTERNAL_SMOKE=1`), without prompting agent to print, persist or post keys;
- test-only receiver and approver identities are verified and not normal trading production channels;
- all execution backends locked to `DRY_RUN` with mock order client; no Binance keys, private account data or live market account linkage;
- no external **approval callback is allowed to generate trade intent or order**, even DRY_RUN paper intent unless test explicitly quarantines it; smoke should send a benign notice and verify response/authentication with correlation id, never a buy/sell instruction or live-looking order proposal.

OpenAI provider: one bounded non-sensitive synthetic CasePackage/text query for strict schema, refusal/timeouts and associated receipt; model/provider version actual observed, **not** assumed GPT-6 High selection. Feishu: nontrading test notification send/response and, only in controlled callback harness, verify token/signature (without logging secrets), approver identity replay and failure modes. If provider/offline network blocked, report `EXTERNAL_SMOKE_BLOCKED`, not fake a successful connection. Do not attempt to recover credentials through Slack, Gmail, browser, environment dumps or connected account tools.

Externally observed request IDs may be saved **only if demonstrably non-secret**. Remove message content containing identifying/user or account information. Keep exact test receipts, redacted host endpoint, error reason, timeouts and provider nontrade mode. **No subscriptions or notifications to user's existing personal Feishu unless explicitly configured**.

## C. Terminals, evidence and proactive push

Evidence directory `evidence/v0.6/b_line/g3_operational_r1/**`:
- `PLATFORM_AND_SOURCE_IDENTITY.json`: exact integrated baseline SHA and worktree/Git source, Python/OS/SQLite, dependencies, isolation, signed-write zero.
- `COLD_START_RECOVERY_MATRIX.json`: every scenario PASS/FAIL/SKIP with exact observed output/hashes and timestamp;
- `G3_EXTERNAL_NONTRADING_SMOKE.json`: ENABLED+PASS, ENABLED+FAIL or NOT_RUN_NO_TEST_CREDENTIALS, never implicit PASS;
- `G3_PERFORMANCE_SNAPSHOT.json`: measured startup/recovery duration and memory for specific VM and data fixture; no extrapolation to production;
- `TEST_RECEIPT.json`, `G3_R1_REVIEW.md` with negative scenarios, timing, limitations, and explicit G4 blocks;
- `WORKTREE_PRESERVATION.json` with original/G1/G2/review branch-head checks and dirty file COUNTS only (redacted).

Terminal one:
- `G3_R1_OFFLINE_OPERATIONAL_PASS_EXTERNAL_SMOKE_PENDING` (all applicable offline critical negatives PASS, no external credentials);
- `G3_R1_OFFLINE_AND_NONTRADING_EXTERNAL_SMOKE_PASS` (explicit enabled dedicated test external smoke passed; still **not** G4 TESTNET);
- `G3_R1_OPERATIONAL_BLOCKED` (any critical startup/cold recovery/fail closed defect);
- `G3_R1_ENVIRONMENT_INCOMPLETE` (unable to certify Linux3.12/Docker or enough cases);
- `G3_BLOCKED_BY_POSTMERGE_CI` / `BLOCKED_NOT_PUSHED`.

L0 changed Ruff/compile, L1 focused G3 tests and relevant affected G1 safety tests, explicit Linux3.12 receipt. Default no full suite. All optional test skips accounted separately, none silently passed. **Autonomous code/test/evidence commit and push to feature branch**, verify remote HEAD parent/changed files and `REMOTE_PUSH_VERIFIED=true` at end; no direct v0.6 push, no permissions escalation. If cannot publish, return `BLOCKED_NOT_PUSHED`.

Required final summary: exact `CONTROLLER_DISPATCH_SHA=ba60efc078e9bb75bdc728e8875ba48fb69d1752`; baseline `a56cc413d87a71111f2be02f10052dced9ff0275`, branch and remote feature SHA; Python 3.12 OS kernel, repeatable tests (pass/fail/skip/time), one-worker and recovery exact results; provider smoke real/no, Feishu real/no, signed exchange writes 0, all protected reads 0, no live trade, `TESTNET_NOT_AUTHORIZED`, and recommended G4 exact-SHA release candidate gate.
