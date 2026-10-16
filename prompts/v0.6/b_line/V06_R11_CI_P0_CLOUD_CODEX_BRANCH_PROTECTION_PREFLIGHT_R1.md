# R11-CI-P0 — Cloud Codex Branch-Protection / Required-Check Preflight

Role: Cloud Codex repository engineer. This is ONE bounded, READ-ONLY preflight. Do not edit, commit, push, merge, change branch protection, disable workflows, or modify any repository file.

Repository: EXASHXE/btc-quant-agent-public
B-line target workflow: .github/workflows/ci.yml
Exact B-line code SHA: e0ff8c3473de4bfa3e66fe7928d42992a4d38a32
Default branch: v0.5-refactor
B-line docs: v0.6-docs
Controller decision baseline: a7cab50621bf468d35190ac8cf9e3b0c6894a592
Existing conditional implementation prompt:
https://github.com/EXASHXE/btc-quant-agent-public/blob/a7cab50621bf468d35190ac8cf9e3b0c6894a592/prompts/v0.6/b_line/V06_R11_RESEARCH_ONLY_CI_TRIGGER_IMPLEMENTATION_CONDITIONAL_R1.md

## Objective

Resolve the current Controller gate BRANCH_PROTECTION_VERIFICATION_PENDING using the strongest read-only evidence available to the Cloud Codex environment.

Inspect, independently:

1. Exact HEAD identities for v0.6, v0.6-docs and default v0.5-refactor.
2. The complete .github/workflows/ci.yml on v0.6 and default branch, including effective push, pull_request, schedule and workflow_dispatch triggers and inputs.
3. Repository rulesets, including repository and organization-level rules that can affect the repository if the authenticated token can read them.
4. Branch protection / required status checks for v0.6, v0.6-docs, default v0.5-refactor, and the intended B-line implementation branch pattern.
5. Effective rules for each relevant branch, including required PR reviews, required status checks, bypass actors, push restrictions and ruleset target patterns.
6. Whether A-line and B-line share the workflow path or any trigger configuration.
7. Whether workflow_dispatch is registered on the default branch and whether a manual run against a non-default B-line ref is technically possible. Do NOT actually dispatch a workflow.
8. Whether the weekly schedule declared on non-default v0.6 is operationally effective under GitHub's default-branch rule.

Use GitHub API / gh CLI / repository metadata available to the Cloud Codex environment. Do not request or expose credentials. Never paste tokens.

## Fail-closed rule

If any required protection/ruleset information returns 403, is unavailable, or cannot be proven effective, terminal MUST be:
BRANCH_PROTECTION_VERIFICATION_PENDING

Do not infer "no protection" from protected=false summaries, empty visible rulesets, or an inaccessible endpoint.

Only if complete effective required-check/protection coverage is independently proven may terminal be:
BRANCH_PROTECTION_VERIFIED

This preflight alone does NOT authorize the CI edit.

## Deliverable

Return a concise evidence receipt containing:
- exact repository/default/B-line SHAs
- exact workflow blobs
- protection/ruleset endpoint results and HTTP status
- exact required checks/PR requirements/ruleset patterns
- A-line/B-line CI sharing assessment
- workflow_dispatch/manual-run assessment
- schedule effectiveness assessment
- terminal
- commands/API paths used (without secrets)

No strategy work, data downloads, Alpha scoring, TESTNET, LIVE, account or funds access.