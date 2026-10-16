# R11 Conditional Implementation — B-line Research-Only CI Trigger Narrow Edit

**STATUS: NOT DISPATCHABLE UNTIL FULL BRANCH-PROTECTION VERIFICATION AND OWNER/CONTROLLER ACTIVATION.** Executor: ChatGPT-2-E (narrow deterministic config edit) OR Gemini NORMAL, ONE isolated session, not both concurrently. No custom subagents.

## Frozen basis
- Controller decision: `reviews/v0.6/b_line/V06_R11_CI_RESEARCH_ONLY_CONTROLLER_L2_DECISION_20261016.md` in the Controller's isolated R11 CI docs branch; verify its final exact SHA/blob before relying on it.
- **Target code start SHA**: `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32` on `v0.6`, workflow blob `0cf87687216b475f338f637fb968af2f670ace67`. If either changes, STOP for a new Controller exact-SHA task; do not guess or rebase silently.
- **ONLY mutable path**: `.github/workflows/ci.yml`, on a NEW isolated B-line implementation branch based exactly on the target code start SHA. No other files or commits, no merge or force push.

## Mandatory preflight and fail-closed controls
1. Owner/admin provides verifiable complete protection/ruleset/required-check coverage for `v0.6`, implementation target, default `v0.5-refactor`, and potentially impacted PR branches. Confirm no required status check will be silently stranded. A ruleset list empty and `protected:false` summary alone is NOT sufficient; direct protection API was 403.
2. If a required PR context exists, change plan to a minimal REAL PR verification job with the same required check name and scope, approved separately by Controller; otherwise STOP. Do not alter branch protections.
3. Confirm A-line shares repository but never receives this B-line branch edit; do not update default branch or H39/H40/H41 scopes. No global disabling of Actions.
4. Confirm default `.github/workflows/ci.yml` still registers `workflow_dispatch`. Verify a disposable/manual smoke on a separate authorized B-line ref if supported, ensuring the actual `head_sha` matches frozen target and the intended profile; no inference from YAML inspection alone. No unauthorized manual workload.
5. Recognize that a cron listed on nondefault `v0.6` does not represent a running weekly default-branch schedule. Record this nuance.

## Narrow implementation AFTER every gate
Edit ONLY `.github/workflows/ci.yml` on isolated branch, replacing the root trigger declaration with the `workflow_dispatch` event while retaining its choice inputs `focused`, `integration`, `full` exactly. Remove `push`, `pull_request`, and `schedule` from that **B-line branch version** ONLY. Leave all job steps, test planner, compatibility matrix, dependencies, tests, timeout/concurrency, reporting and safety logic unchanged. Do NOT modify default branch, `v0.6-docs`, old feature branches, A-line workflows or other repository files.

Validate YAML with a parser that preserves the special `on` key (for PyYAML use YAML 1.2 or configure boolean resolver), and structurally compare original vs changed YAML: exactly trigger-node delta and zero other semantic tree changes. Check before/after effective events, branch isolation, and workflow_dispatch registered on default. Run tiny focused config checks locally and independent read-only verification on exact SHA. If smoke is permitted, dispatch against the frozen ref and inspect run `head_sha`, job/profile and actual result; hosted result FAIL remains FAIL, not smoke PASS for full suite. Never report CI green without actual passing run.

Publish one bounded implementation receipt (if it can fit within permitted only-path edit, record receipt in author response; no additional Git file), exact branch/parent/commit/workflow blob/diff/actual CI and independent reviewer. This config-only publication **does not** turn off CI across existing other branches; any wider migration requires separate Controller authorization.

## Strict forbidden actions
No deletion/edit of scripts, dependencies, test files/cases, compatibility profiles or H40; no PR/branch-protection mutation; no force push, merge, data acquisition, strategy backtest, TESTNET, LIVE, account or funds. Stop on unverifiable protections, ambiguous branch, missing dispatch, unintended diff or required-check conflict.

Terminal: `RESEARCH_CI_MODE_CONFIG_APPLIED_WITH_LIMITS` only if all prerequisites, edit, smoke/verification and exact-SHA receipt succeed; otherwise `BRANCH_PROTECTION_VERIFICATION_PENDING` or `CI_SCOPE_CONFLICT_STOP`. This terminal never grants independent scientific acceptance.
