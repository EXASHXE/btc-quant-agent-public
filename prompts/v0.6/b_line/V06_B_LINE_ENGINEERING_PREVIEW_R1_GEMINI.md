> **Local-worktree location override (Controller-approved, no other authority change):** [V0.6 workspace layout](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/V0.6_PARALLEL_LOCAL_WORKTREE_LAYOUT_V1.md), `CONTROLLER_WORKSPACE_OVERRIDE_SHA=595d0b87cdad43f924f1e0040b8d6b33ae241237`. The formerly specified sibling worktree path is replaced by `/root/workspace/project/quant-v0.6/g1-engineering-preview`. The original G1 CONTROLLER_DISPATCH_SHA, allowed source scope, base code SHA, DRY_RUN limitation, security fences, and proactive branch push all remain unchanged. Run [bootstrap prompt](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/prompts/v0.6/ops/V06_PARALLEL_WORKTREE_BOOTSTRAP_R1.md) first; if old task worktree exists, stop for migration rather than moving it.

# v0.6 B-line Engineering Preview R1 — WP-A/C/D controlled integration and offline end-to-end DRY_RUN

**Executor:** Gemini implementation engineer; **Controller:** ChatGPT-0 (B-line). One coherent work package with terminal push, not a fresh strategic research or protected-holdout task.

| Immutable field | Binding |
|---|---|
| TASK_ID | `V06_B_LINE_WP_A_C_D_ENGINEERING_PREVIEW_R1` |
| REPOSITORY | `EXASHXE/btc-quant-agent-public` |
| CONTROLLER_DISPATCH_SHA | `8f0ccb2dbbc0612e3218ea554309d123959118f7` — development-only Controller docs commit containing [dev authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/8f0ccb2dbbc0612e3218ea554309d123959118f7/evidence/v0.6/controller/B_LINE_ENGINEERING_PREVIEW_R1_DEV_DISPATCH.json) |
| BASE BRANCH / exact START_SHA | `v0.6` / `d6500140f3141d179181f2360ad815b5bfe9c954` |
| NEW IMPLEMENTATION BRANCH | `feature/v06-bline-engineering-preview-r1` from the exact START_SHA |
| LOCAL ENTRY CHECKOUT | `/root/workspace/project/rc2-tactical-successor` |
| DEDICATED SIBLING WORKTREE | `/root/workspace/project/quant-v0.6/g1-engineering-preview` |
| R8 Live V1 baseline | `08e81bec003d645a0a0582db183a1b6916887eff` — safety semantics accepted, **independent TESTNET release held** |
| WP-A Controller-accepted | `606f286dbb5d7af46776043d1287d9b3e7b1e679` — startup & operational |
| WP-C Controller-accepted | `72b39de71024b3051357c17eee7922e657dcb81f` — LLM/approval, external smoke pending |
| WP-D Controller-accepted | `3a83ccd9dbf7b627c98f70a9ad7ee4b0e19eeaea` — release/operability, exact integration manifest pending |
| Normal operating profile | `ENGINEERING_PREVIEW_OFFLINE_DR Y_RUN` (actual implementation enum must be `DRY_RUN`; the label is descriptive only) |
| Real trading / TESTNET permission | **NONE**; no external exchange-write calls, no real credentials, no protected outcomes |

Review first: [v0.6 Controller role](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/roles/V0.6_CHATGPT_0_PRIMARY_CONTROLLER.md), [canonical roadmap](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/V0.6_PROJECT_STATUS_AND_ROADMAP.md), [real-funds gates](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/docs/project/V0.6_REAL_FUNDS_TEST_READINESS_GATES.md), [RC1 release contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.5/live_v1/V0.5.5_B_LINE_INITIAL_USABLE_RELEASE_V1_RC1_CONTRACT.md), [WP-A](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.5/rc1/V0.5.5_RC1_WP_A_CONTROLLER_REVIEW.md), [WP-C](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.5/rc1/V0.5.5_RC1_WP_C_CONTROLLER_REVIEW.md), [WP-D](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.5/rc1/V0.5.5_RC1_WP_D_REPAIR_CONTROLLER_REVIEW.md), [R8 safety disposition](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.6-docs/reviews/v0.5/live_v1/V0.5.5_LIVE_V1_B5_R8_CONTROLLER_ADJUDICATION.md).

## 0. Objective, limits and outcome

Produce a real, repeatable **local offline DRY_RUN** engineering-preview integration of the **already accepted** MarketWatch/Tactical foundation in `v0.6` plus R8's reviewed Live V1 baseline and WP-A/C/D scoped accepted deltas:

```text
approved synthetic/public-data fixture (OFFLINE)
→ MarketWatch/Tactical signal & quality flags
→ deterministic immutable CasePackage
→ strictly mocked primary LLM AnalysisResultV1
→ DecisionFusion + deterministic RiskCompiler
→ TradeProposal
→ mock Feishu notification / simulated human APPROVE-REJECT-REVIEW
→ approval-identity/hash/TTL check
→ DRY_RUN-only (no signed client / network orders)
→ simulated order/fill/protection/reconciliation
→ PositionSupervisor event / durable restart and audit receipt
```

It is acceptable for a **no-trade/WAIT/manual-review** case to exit without simulated orders, but E2E test **also** needs a fully authorized synthetic DRY_RUN-only positive path. No LLM may decide executable quantity/leverage or increase authorized risk. All provider and transport accesses must be mocks with explicit zero-real-write assertion.

**Explicitly NOT being done:** protected RC2 source/outcome replay, strategy-quality qualification, parameter retuning, live write capability, genuine TESTNET orders, credentialed OpenAI/Feishu/Binance smoke, or promoting the still-unaccepted R8 B5 validation as PASS. The legacy `WP-B` failed decision-quality evaluation is **not** accepted; do not import it as a passed strategy or bypass quality gates.

## 1. Local filesystem and Git safety — required first

User's present working directory `/root/workspace/project/rc2-tactical-successor` may be on a historic validation branch (previous evidence: `validation/b-line-rc2-final-holdout-infra-repair-r1`) and belongs to ongoing work. **Never** checkout, reset, clean, stash, hard-restore, edit, delete or switch its branch. It is an entry repository **only**.

Read-only preflight:

```bash
ENTRY=/root/workspace/project/rc2-tactical-successor
WT=/root/workspace/project/quant-v0.6/g1-engineering-preview
cd "$ENTRY" || exit 1
pwd -P
git rev-parse --show-toplevel
git status --porcelain=v1 --untracked-files=all
git rev-parse HEAD
git branch --show-current
git worktree list --porcelain
git remote -v  # redact user-info/tokens in reported URLs
```

Check `ENTRY` is the actual repo root and identify a preconfigured remote *provably pointing to* `EXASHXE/btc-quant-agent-public`. If not, stop `BLOCKED_REPO_OR_REMOTE_IDENTITY`: no `git init`, clone over existing checkout, remote rewrite, or pushing private history to unintended remote.

Fetch only needed branches/objects through verified remote **without changing ENTRY checked-out HEAD**. Verify `origin/v0.6` (or the correctly identified public remote tracking ref) equals `d6500140f3141d179181f2360ad815b5bfe9c954`, and `8f0ccb2dbbc0612e3218ea554309d123959118f7` exists as an ancestor of fetched `v0.6-docs` and contains exact development-authority JSON. Verify five pinned commit objects (`START_SHA, R8, WP-A, WP-C, WP-D`) by `git cat-file -e <sha>^{commit}`. Drift, unverified source, or missing ancestry ⇒ stop rather than silently use latest.

Create an isolated sibling worktree only if **`$WT` does not already exist** and branch unused:

```bash
git worktree add --no-track -b feature/v06-bline-engineering-preview-r1 \
  "$WT" d6500140f3141d179181f2360ad815b5bfe9c954
cd "$WT" || exit 1
test "$(git rev-parse HEAD)" = d6500140f3141d179181f2360ad815b5bfe9c954
git status --porcelain=v1
```

If worktree/branch already exists, resume **only** if exact task ownership/parent is proven and workspace is safe; otherwise `BLOCKED_WORKTREE_COLLISION`. Do not overwrite/delete existing worktrees, user files, secrets, untracked archives or caches. No `git reset --hard`, `git clean -fdx`, `git stash` in ENTRY, `git push --force`, forced checkout, destructive `rm -rf`, global git config edits, or speculative credential recovery. Do **not** touch `Quant-agent-sanitized`. Use unique `/tmp/v06-engineering-preview-r1-<pid>/` for transient nonprotected test artifacts; inspect generated files for secrets before stage/commit.

**Mandatory terminal automation:** after passing the requested checks, `git add -- <explicit allowed paths>`, inspect staged `git diff --cached --name-status`, commit to the **task branch** (optional evidence-only second commit), proactively `git push -u <VERIFIED_REMOTE> HEAD:refs/heads/feature/v06-bline-engineering-preview-r1` with **no force**, then fetch/query remote to verify actual branch HEAD, parent and file scope. **Do not wait for user to say 'push'.** If push cannot be verified: `BLOCKED_NOT_PUSHED`, no READY_FOR_CONTROLLER. Never push changes directly to `v0.6`, `v0.6-docs` or original local checkout.

## 2. Exact source provenance and integration rules

Implement via an **explicit file-level integration manifest**. Do not `git merge` / `git cherry-pick` whole R8, WP-A/C/D or Live V1 branches, nor `git restore --source=<SHA> -- .` or bulk copy unknown files. The current v0.6 includes independently accepted MarketWatch plus H41; Live V1 feature ancestry differs and is not fully release-accepted.

**Stage I, source baseline:** enumerate only the files needed from pinned R8 baseline `08e81...`, including small module surfaces:
- `src/btc_quant_agent/{account_watch,approval,decision,execution,live_market,position_supervisor}/**`;
- `src/btc_quant_agent/live_db.py`, `src/btc_quant_agent/live_runtime.py`;
- narrow needed API/CLI/shared data/config imports;
- relevant `tests/test_live_v1*.py` and `tests/test_binance_signed.py`, but do not blindly replace previously accepted Tactical tests;
- `pyproject.toml` only if dependency resolution proves needed, with precise diff and reason.

For each path: source blob SHA, base blob SHA, owning accepted component, whether byte-copied or three-way integrated, reason. Preserve MarketWatch Tactical canonical hashes/semantics, `src/btc_quant_agent/h40/**`, `src/btc_quant_agent/h41/**`, `tests/h41/**` and scientific/forward files byte-identical to `v0.6` START_SHA. Avoid importing unrelated evidence/secret/runtime caches or historic RC2 runner.

**Stage II, accepted WP deltas:** apply WP-A changes from `606f286...` only where `git diff 08e81... 606f286... -- <file>` confirms WP-A ownership: `live_db.py`, `live_runtime.py`, `position_supervisor/supervisor.py`, targeted new operational readiness test. Preserve certified **single canonical Linux/POSIX runtime, Python 3.12.3, serialized initializer, fcntl lock, all eight guards**; do not assert Windows or Python 3.13 certification.

Apply WP-C `72b39...` *only* in `approval/feishu.py`, `decision/{backends,fusion,service}.py`, narrow `config.py`, and accepted new integration tests. Preserve fail-closed provider error/refusal/timeout handling, strict primary/secondary isolation, manual-review triggers, proposal/hash/nonce/TTL/idempotency, model authority = NONE. Mark external OpenAI/Feishu provider smoke **PENDING**, not mock-passed as real.

Apply WP-D `3a83...` *only* in `api.py`, non-secret deployment templates (`.env.example`, `Dockerfile`, `docker-compose.yml`), startup/runbook docs, release-manifest code and its accepted tests. **Do not copy old release manifest as a final bound RC authority**. Keep `source_sha=UNBOUND_PENDING_RC_INTEGRATION` and Python/cert fields pending until Controller accepts a stable integrated implementation SHA. The exact SHA and WP-A evidence-binding verification occur at the later RC gate, not by self-certifying this feature.

**Conflict rule:** new `v0.6` shared config/CLI/data/Tactical files take priority for B-line currently accepted semantics; manually apply only necessary additive Live V1 integration hunks. Any conflict that changes Tactical policy costs, stop/target, allowed actions, score thresholds, risk caps, authorization, position ownership or protected gates must stop with `BLOCKED_SEMANTIC_CONFLICT`. Do not silently accept broad R8 source differences or handwave with compile success.

## 3. Preview safety contract and integration acceptance

- DRY_RUN is a **structurally enforced** runtime mode: no real Binance signed order placement/modify/cancel endpoints reachable even when mocked approval says APPROVE; no Binance API key required; all backend writes go to a separate deterministic in-memory/mock adapter. Test that attempts to select `LIVE` or `TESTNET` without separate authorization fail **before signed client/network creation**. No default mode escalation through environment strings or DI bypass.
- Mock model/Feishu callbacks: validate CasePackage immutable identity/PIT snapshot/case hash, strict `AnalysisResultV1`, deterministic fusion, risk compiler bounded quantity/leverage, manual-review and rejection veto, nonce TTL, duplicate callback, hash mismatch and stale market cases. Provider failure ⇒ no decision/order.
- Simulated fill, stop/protection, restart/replay and reconciliation are deterministic; verify approval-bound order intent lineage, exactly-once processing for the local dummy backend, persisted recovery after restarting preview under certified single-worker semantics. Post-event analysis cannot submit orders.
- No real account stream, Feishu delivery, exchange data download, TESTNET order, paper PnL mislabelled as live or historic protected-market data fetch. Public fixtures already in repo and synthetic data are permitted **only offline**.
- Separate config/output under `evidence/v0.6/b_line/engineering_preview_r1/**` and `/tmp/v06-engineering-preview-r1-<pid>`, never overwrite historic `evidence/v0.5.5/**`, `HOLDOUT_FINAL/**`, or `data/forward/**`.
- Restrict changed source primarily to `src/btc_quant_agent/{account_watch,approval,decision,execution,live_market,position_supervisor}/**`, `src/btc_quant_agent/{api.py,cli.py,config.py,live_db.py,live_runtime.py}`; narrow shared data adapt only if absolutely necessary with exact hunks. Test additions `tests/test_live_v1*.py`, `tests/test_binance_signed.py`, and a new `tests/test_v06_engineering_preview_r1.py`. Deployment/runbook `Dockerfile`, `docker-compose.yml`, `.env.example`, `docs/LIVE_V1_RC1_OPERATIONAL_RUNBOOK.md`; non-secret config and manifest templates when directly justified. The allowed evidence directory is `evidence/v0.6/b_line/engineering_preview_r1/**`.
- **Forbidden:** any edit of `src/btc_quant_agent/h40/**`, `src/btc_quant_agent/h41/**`, `tests/h41/**`, `scripts/rc2/validation/**`, protected sources/outcomes, frozen target seal, `src/btc_quant_agent/market_watch/**` strategy/policy files, existing `v0.5.5` evidence; no write to real Binance/account endpoints. Any dependency on such change requires halt and Controller scope decision.

## 4. Risk-scoped verification, not repetitive full suite

**L0 dev iteration:** compile touched Python, Ruff touched/source, manifest/path checks, fast failing unit tests and hermetic mocks. Reuse accepted immutable proofs where exact inputs and environment match. Do not run full pytest on every commit.

**L1 terminal (one coherent pass):**
1. `git diff --check <START_SHA> HEAD`; explicit `git diff --name-status <START_SHA> HEAD` no forbidden paths; A-line identity `git diff --exit-code <START_SHA> -- src/btc_quant_agent/h40 src/btc_quant_agent/h41 tests/h41`.
2. Ruff, compileall, dependency/install reproducibility under Linux Python **3.12** (if only Python 3.13 available, report unsupported runtime and stop certification); mypy affected package once where material.
3. Focused pytest: WP-A operational/cold-start and restart, WP-C LLM/Feishu negative matrix, WP-D release/startup, core Live V1 decision→approval→DRY_RUN execution→position/outbox safe slices; Tactical integration smoke and R02 mutating-route guard. Prefer one batched test command with `--durations=20` and JUnit; no all-suite default until release L3. If a focused test hangs, diagnose process/async lifecycle with bounded timeout and evidence; never mark timeouts PASS or weaken/delete tests.
4. At least **two E2E fixture paths**: authorized synthetic DRY_RUN fill→protection→reconciliation; refusal/expired/forged approval `NO_EXECUTION`. Separate cold restart after persisted terminal; explicit mock signed-client call count **0** and protected archive read count **0**.
5. Redact secrets from terminal evidence; record Python exact, OS, commands, test counts/passed/failed/skipped, durations, changed file list, known tests **NOT RUN** (do not interpret as PASS), prior accepted WP source blob comparisons, mock-only callback proofs. CI Fast Path must remain functional; don't silently bypass repo-wide `conftest` for operational tests.
6. **Do not** ask Gemini to independently approve strategy PASS, TESTNET or release; those are Controller + fresh L3 checks.

**L2 handoff criteria:** one terminal pushed branch with executable standalone offline DRY_RUN instructions, passed scoped safety negatives, exact provenance, original entry worktree preserved. If core E2E missing or executable mode can reach signed exchange with mock approval, return BLOCKED, not READY.

## 5. Evidence, active push, precise terminal output

Publish **append-only synthetic/nonprotected**:
- `INTEGRATION_PROVENANCE.json`: exact source per file (R8/WP-A/WP-C/WP-D), accepted refs, semantic conflict resolutions, execution mode defaults, A-line diff-zero.
- `PREVIEW_DR Y_RUN_RECEIPT.json` (filename must be `PREVIEW_DRY_RUN_RECEIPT.json`): positive/negative CasePackage→approval→mock order/fill/protection→position event, no external IO, no protected reads.
- `TEST_RECEIPT.json`: observed test results, selected vs omitted suites, Python/OS, timing, CI status.
- `ORIGINAL_WORKTREE_PRESERVATION.json`: original entry branch, HEAD and pre/post changed/untracked file **counts** only; dedicated worktree path; no secrets.

If evidence references implementation SHA, use **implementation commit first**, then append-only **evidence-only commit** to avoid circular SHA. Self-referential source SHA in same commit is not accepted as evidence. Verify all remote commitments.

Push autonomously; `REMOTE_PUSH_VERIFIED=true` only after verifying public branch and SHA. If auth, branch drift or network stops push ⇒ `BLOCKED_NOT_PUSHED` with exact blocker. No direct `v0.6` merge. No protected execution even after successful push.

**Terminal:** `V06_B_LINE_ENGINEERING_PREVIEW_R1_READY_FOR_CONTROLLER` or `V06_B_LINE_ENGINEERING_PREVIEW_R1_BLOCKED`, report:
```text
TASK_ID / CONTROLLER_DISPATCH_SHA
LOCAL_ENTRY_ROOT / ORIGINAL_PRE_POST_IDENTITY / NEW_WORKTREE
START_SHA / SOURCE_R8_SHA / WP_A_SHA / WP_C_SHA / WP_D_SHA
IMPLEMENTATION_SHA / EVIDENCE_SHA / BRANCH / REMOTE_PUSH_VERIFIED
CHANGED_PATHS / SEMANTIC_CONFLICTS / A_LINE_DIFF
OFFLINE_E2E_ACCEPT_REJECT_EXPIRED_REPLAY_RESULTS
SCOPED_TESTS_PASSED_FAILED_SKIPPED_TIMINGS / CI_RUN_URL_AND_STATUS
MARKET_NETWORK_ACCESS=0 / EXCHANGE_WRITE_COUNT=0 / PROTECTED_READS=0
PROVIDER_SMOKE=PENDING / WP_D_RELEASE_BINDING=PENDING / TESTNET=NOT_AUTHORIZED
REAL_FUNDS_WRITE_AUTHORITY=NONE / NEXT_CONTROLLER_ACTION=L2_EXACT_SHA_REVIEW
```

After terminal push the **Controller**, not Gemini, will conduct one L2 acceptance and decide integration. A later independent RC validation and TESTNET authorization remain separate.
