# RESTORE_ENGINEERING_CI — Conditional B-line CI Restoration Task

**NOT ACTIVE / PREWRITTEN ONLY.** Executor: Gemini NORMAL or ChatGPT-2-E for exactly bounded workflow edits; additional independent ChatGPT-1 review for consequential safety/integration. Controller owns final gate; one task per chat, no custom subagents.

## Trigger to restore
Start before ANY of:
1. Substantial B-line cross-module engineering integration resumes.
2. Independently validated Alpha enters operational engineering.
3. Controller authorizes G1/G3 integrated readiness.
4. TESTNET or release gate requires production/full regression.
5. Consequential safety defect needs broad verification immediately.
A standalone green CI can NEVER promote source validity, PIT or net strategy profitability.

## Preflight
Read current Controller decision, restoration need, effective rulesets/protection/required check names, and the EXACT workflow/blob and code SHA then active. Verify default branch still has the manual registration file and distinguish A-line from B-line. Do not assume the workflow edit actually happened; if conditional Research-Only mode never activated, document that restoration is not required and STOP. Owner explicitly approves any impact to PR protections and workflow schedules.

## Scope
Restore B-line-specific `push` and `pull_request` triggers as appropriate to the intended branch patterns, reinstating a genuine required minimal check when protections require it. Restore full/integration runs and Python compatibility checks, and a reviewed schedule only if genuinely needed and effective on default branch (nondefault cron does not run by itself). Keep `workflow_dispatch` and focused/integration/full manual selection, all original test assets, scripts and safety checks intact. No default/A-line workflow edits without separate A-line authorization. No broad refactor or CI planner rewrite.

## Acceptance
- Exact SHA and path allowlist, original-vs-restored trigger table, YAML parser validation, branch effective rule coverage and full diff.
- Truly executed required PR/Push checks where applicable, manual `focused/integration/full` and Python-version compatibility on the exact frozen candidate SHA, real results and artifacts. If required checks remain unavailable or fail, fail closed. A skipped/unrun full suite is not PASS.
- Independent consequential audit when safety/account/causal code is touched; Controller L2 decides whether G1/G3 engineering can proceed.
- No Alpha promotion, TESTNET/LIVE, protected data/funds authority from workflow changes.

Publish exact commit/blob/parent/actual CI. State `RESTORE_ENGINEERING_CI_VERIFIED` only after real verification; otherwise `RESTORE_ENGINEERING_CI_BLOCKED`.
