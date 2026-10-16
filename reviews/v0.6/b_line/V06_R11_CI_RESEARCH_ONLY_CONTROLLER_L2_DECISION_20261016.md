# R11 Controller — B-line Research-First CI Allocation and Protection Preflight

Date: 2026-10-16 Asia/Shanghai. Role: ChatGPT-0 B-line Primary Controller / L2.
**Binding terminal decision: BRANCH_PROTECTION_VERIFICATION_PENDING.**
**Owner research-first prioritization: ACCEPTED AS POLICY. CI trigger change: NOT AUTHORIZED TO EXECUTE YET; NOT APPLIED.**
Exact documentary parent: 2f1e4b340c56448bfa0207ee2d6fc6dded797cfd. This document does not grant data, Alpha, merge, TESTNET, LIVE, financial or protected-source access.

## 1. Observed repository identities and workflow configuration

Repository: EXASHXE/btc-quant-agent-public; default branch `v0.5-refactor` HEAD `8ecff4ec4b25bf73a35309689fd3ecfacc0d3399`; B-line code `v0.6` HEAD `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`; B-line documents `v0.6-docs` HEAD `2f1e4b340c56448bfa0207ee2d6fc6dded797cfd` (observed before this isolated publication).

All have `.github/workflows/ci.yml` but at different blob identities:
- `v0.6` blob `0cf87687216b475f338f637fb968af2f670ace67`: bare `push` and `pull_request`, `workflow_dispatch` with `focused/integration/full` choice, `schedule` cron `21 3 * * 1`. Planner uses scripts/ci/test_plan.py. The manual `full` profile includes Python 3.11/3.13 compatibility, in addition to Python 3.12 quality.
- `v0.6-docs` blob `2335031f3a32fd5eeb82b538043ffc3092bedbe2`: `push` and `pull_request` with paths-ignore for prompts/**, reviews/** and REFACTOR_DOCS_BRANCH.md; `workflow_dispatch` without profiles; no `schedule`. Some docs additions outside those path patterns still trigger the full docs-branch safety job.
- Default `v0.5-refactor` blob `5634dcc1efee75819cd8a8bdf17df79f0a02927e`: `push`, `pull_request`, `workflow_dispatch`; no schedule; manual quality/coverage and compatibility 3.11/3.12. This branch is NOT in the B-line edit allowlist.

GitHub scheduled workflows execute only from the **default branch**. The cron present solely on the nondefault `v0.6` workflow does NOT, by itself, establish a currently executing weekly full regression; no default-branch cron was observed. Remove that dormant definition only in an approved future B-line edit, not by claiming an active schedule was stopped. Reference: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule .

GitHub manual dispatch requires a `workflow_dispatch` workflow available on the default branch. That condition appears present for `ci.yml`, but manual exact B-line ref execution has NOT been live-smoke verified. Dispatch target is a branch/tag, not a free-form commit SHA. Freeze the target branch at the candidate commit; verify run `head_sha` equals the exact candidate SHA and correct workflow/profile and result. Reference: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow .

## 2. Branch-protection and shared-CI assessment

- REST branch summaries for `v0.6`, `v0.6-docs` and default `v0.5-refactor` return `protected:false` and summary `required_status_checks.enforcement_level=off`, empty `checks/contexts`.
- GET `.../branches/{branch}/protection` on ALL three returns HTTP 403 `Resource not accessible by integration`. Hence full protection configurations and required checks could NOT be independently inspected.
- GET repository rulesets including parents returned an empty list, but this does not cure the unavailable full branch-protection detail or any possible effective restrictions not returned to this integration.
- Therefore: **BRANCH_PROTECTION_VERIFICATION_PENDING**, fail closed on workflow trigger edits; no PR/check could be stranded by this documentary action.
- A-line H39/H40/H41/Forward and B-line share a repository and the workflow path; there is no demonstrated independently enforceable line-specific CI config. The different branch versions are not independent repositories or global switches.
- Editing one branch's YAML affects that ref/descendants only, NOT every already-existing B-line feature/docs branch. No claim of a repository-global CI suspension. Default branch and A-line must remain untouched.

Required external precondition: owner/admin independently inspect GitHub Settings → Rules → Rulesets, branch protection for `v0.6`, `v0.6-docs`, default and implementation target, PR policies, any required `CI / quality` check and organizational rules. Provide dated screenshot/export or authenticated read receipt of effective rules and branch patterns. If ANY required check would be removed, retain a minimal real PR check with the identical required context on affected branches, or STOP and request separate authorization for protection adjustment; never silently change requirements. Re-check immediately before editing.

## 3. Research-first Controller decision (not workflow enablement)

Priority: legally usable, provenance-bound BTC/ETH source bytes; source/PIT clock and contract semantics; correct scientific design and independent Alpha validation. Defer broad CI optimization, speculative compatibility/infrastructure and release refinements while no strategy Alpha is independently validated, unless a current research dependency or consequential safety issue requires them.

The owner requests **RESEARCH_ONLY_CI_MODE** as a *temporary B-line execution policy*. Conditional implementation design on `v0.6` is manual `workflow_dispatch` ONLY: remove push, PR and nondefault dormant schedule, preserve profiles, scripts, tests and compatibility. But the trigger change is NOT approved for execution until branch-protection verification and safe exact-ref manual-dispatch evidence. For docs branch or existing feature branches, issue separate branch-specific scope once necessity and protection are demonstrated. No CI deletion, fake check, H40 repair or A-line waiver.

Routine documentation-only work may rely on exact SHA/blob/diff review; source parsers, provenance, PIT, causal features, order fills, funding, accounting and other consequential changes require bounded local tests with reproducible receipt and independent scientific/consequential scrutiny even during this mode. Failure or absence of hosted CI remains explicitly recorded as such. An independently tested method is not automatically admitted source or profitable Alpha.

## 4. R11 deliveries and scope impact

- Frozen Controller R11-Q2: `c07c60385479f0d595352ad751c1c49150b4cbbc`; consequential independent R11-Q1 BLOCKED: `8c3e53f8fe37d9a8acd340944b843e04f05d2fdc`.
- C2 branch head `9dbb0ce7d266c0d6731775a7a53170bf34400520` = `R11_C2_CAPACITY_STOP_UNMEASURED_SOURCE` (no path authorization/measurement, parent is historical C report SHA, not Q2).
- D2 head `803a4173717ace9c03ff97051b7696210e183bef` = author-reported `R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS`; requires independent inventory/PIT/QC review, not blanket admission.
- E2 head `7f8c6acadead47dccdeba80b2ae27c2497ee8cdf` = author-reported `R11_E2_OKX_PORTAL_PILOT_ACCEPTED_WITH_LIMITS`; L2 partial-slice and exchange-specific timestamp/confirm and product semantics still subject to independent review.
- Exact-source hosted CI runs C2 `38849861983`, D2 `38852084293`, E2 `38852426013` were FAIL (inherited H41 Ruff; E2 also two EXE001 from new source/tests). Later job steps skipped, not PASS. This documentary decision retroactively changes NONE of these observed results.
- No C2 authority/path bypass, no D2/E2 automatic successor, no source admission, Alpha scoring/backfill expansion or protected data access.

## 5. Ready-but-blocked dispatch and restoration

Conditional narrow implementation prompt:
`prompts/v0.6/b_line/V06_R11_RESEARCH_ONLY_CI_TRIGGER_IMPLEMENTATION_CONDITIONAL_R1.md`.
Conditional restoration:
`prompts/v0.6/b_line/V06_R11_RESTORE_ENGINEERING_CI_CONDITIONAL_R1.md`.
Neither is self-executing; Controller checks dependencies, then owner chooses activation. One substantive task per chat; prepare independent work in parallel without double-writing same path. No custom subagents.

## 6. Exact change scope / release gates

This isolated Controller documentation branch changes only the Controller L2 decision report, permanent Controller role, two bounded prompts and a roadmap pointer. It does NOT edit workflows, code, tests, CI planner, branch protections, branch refs outside this isolated docs ref, A-line or protected datasets. The final author commit, changed paths, report blob, actual CI and ahead/behind must be verified **after publication** and externally recorded; this report does not embed unverifiable self-SHAs.

Gates unchanged: `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. Before G1/G3 substantial integration, Alpha operational engineering, TESTNET or release: restore appropriate automatic checks, run full/integration/compatibility on exact frozen code and obtain independent release review.
