# Engineering documentation — docs/engineering

> **CURRENT Q0 HANDOFF — 2026-11-09:** [Start here: Handoff Home](docs/project/V070_HANDOFF_HOME_20261109.md) · [Current Status](docs/project/V070_STATUS_AND_WORKPACKAGES_20261109_Q0.md) · [Q0 Roadmap](docs/project/V070_MULTISYMBOL_MTF_FEISHU_ROADMAP_20261109.md) · [0-C new chat](prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261109_Q0.md) · [1-A new chat](prompts/v0.7/V070_NEW_CHAT_1A_20261109_Q0.md). Old 2026-11-02 snapshots below are historical, not current operational evidence. S is Controller-accepted **offline-only**; Q0B/Q0C await independent Controller acceptance; live Source/Feishu not authorized.\n\n## Current Quant v0.7.0 advisory checkpoint — 2026-11-02

**Read first:** [Session04 receipt discrepancy](docs/project/V070_SESSION04_EVIDENCE_RECONCILIATION_20261102.md) · [Gemini/Claude convergence](docs/project/V070_ARCHITECTURE_AND_RESEARCH_CONVERGENCE_20261102.md) · [Status](docs/project/V070_SOURCE_TO_ADVISORY_CLOSURE_STATUS_20261102.md) · [Roadmap](docs/project/V070_ADVISORY_ROADMAP.md) · [Handoff](docs/project/V070_CURRENT_STATE_AND_HANDOFF.md).

Owner reports a completed Session04 authorization/native diagnostic; latest independently inspected local 11:37 record is non-authorizing `READY_FOR_OWNER_SIGNING` with zero native requests. A superseding signed native receipt has not been verified. Next: Controller 0-C first reconciles actual evidence, then plans/allocates an offline Route B unified Source→L23→Shadow vertical-slice task, not an automatic live run.

[Start independent 1-A](prompts/v0.7/V070_NEW_CHAT_1A.md) · [Start Controller 0-C](prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C.md).

---


## Latest v0.7.0 status (2026-11-02)

- **Current controlling summary:** [Source-to-Advisory closure](docs/project/V070_SOURCE_TO_ADVISORY_CLOSURE_STATUS_20261102.md), [Roadmap](docs/project/V070_ADVISORY_ROADMAP.md) and [Current Handoff](docs/project/V070_CURRENT_STATE_AND_HANDOFF.md).
- Session03 genuine BBO capture was consumed/sealed `PARTIAL/BACKPRESSURE_BLOCKED` (9,153 frames, 5,246 short-clock-qualified quotes); Source/Shadow qualification remains false. Source runtime telemetry is delivered but the original native stall cause remains unresolved.
- Session04 plus LONG V2 handoff is `READY_OFFLINE_HANDOFF` according to 2026-11-02 10:19 local report, and reused Dashboard is READY_OFFLINE. New diagnostic-only native Session04 and <=48h Source+Shadow each require separate exact Owner authorization; there is no implied service deployment or economic Alpha.
- Controller 0-C owns the only engineering delivery queue. Full history remains below, but dated recent closure evidence controls the next operational gate.


## Remote-only external review packs

- [Independent Opus v0.7.0 review pack — 2026-10-28](https://github.com/EXASHXE/btc-quant-agent-public/tree/review/opus-v070-independent-20261028/reviews/opus-v070-20261028) — dated public project brief, research evidence summary, implementation snapshot, source catalogue, and unconstrained strategy/architecture review prompt. This branch is **only a reviewer snapshot**; current canonical docs stay on docs/engineering. Raw protected data and uncommitted local patches are not published.

## Latest research-priority update

- [M1 liquidation-shock reversion with 1–5 minute manual response: causal latency, source feasibility, and revised research order](docs/project/V070_M1_MANUAL_DELAY_RESEARCH_PRIORITIES_20261028.md) — **conditional research candidate, no strategy validation or experiment authorization**. Risk copilot and immutable plan/notification lifecycle remain the independent product track.

## Current v0.7.0 Advisory documentation — canonical (2026-10-28)

**The Owner designates this `docs/engineering` branch as the ONLY future source of project, role, roadmap, task-card, handoff and new-chat documentation.** `v0.7.0` is the executable code/research branch; any matching older documentation there is non-authoritative. Documentation updates must remain on docs/engineering.

Start with [Documentation Branch Policy](docs/project/V070_DOCUMENTATION_BRANCH_POLICY.md) and [AGENTS.md](AGENTS.md).

- [Advisory mission](docs/project/V070_ADVISORY_MISSION_AND_SCOPE.md)
- [Roles and permissions](docs/roles/V070_ADVISORY_AGENT_ROLES.md)
- [ChatGPT strategic advisor role](docs/roles/V070_CHATGPT_STRATEGIC_ADVISOR.md)
- [Current advisory roadmap](docs/project/V070_ADVISORY_ROADMAP.md)
- [Verified state and handoff](docs/project/V070_CURRENT_STATE_AND_HANDOFF.md)
- [Historical Foundation task](docs/project/V070_ADVISORY_FOUNDATION_TASK.md)
- [Current Source-to-Advisory closure](docs/project/V070_SOURCE_TO_ADVISORY_CLOSURE_STATUS_20261102.md)
- [New ChatGPT strategic-advisor prompt](docs/project/V070_CHATGPT_NEW_CHAT_START.md)
- [New Controller 0-C prompt](prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C.md)

**Mandatory chat prompt UX:** display a functional **Copy Full Prompt** button copying the entire prompt when interactive controls exist. Otherwise provide one full code block. See the [policy](docs/project/V070_DOCUMENTATION_BRANCH_POLICY.md).

Earlier Controller B, v0.6.5 and 2026-10-23 v0.7.0 research documents below are retained as historical evidence, not the current Advisory execution plan.

---

This is a documentation-only branch descending from a new root with no research/runtime history. It contains no src/, tests/, configs/ or GitHub Actions workflow. Executable v0.7.0 code/research belongs on [v0.7.0](https://github.com/EXASHXE/btc-quant-agent-public/tree/v0.7.0); earlier v0.6.5 material is historical.

- [Research execution / CI process R2](ci/RESEARCH_EXECUTION_ROUTING_AND_LIGHTWEIGHT_TESTING_R2.md) — full PR #6 engineering page; main keeps a short research-facing pointer.
- [M1 archive/pruning runbook](repository-maintenance/V065_BRANCH_LIFECYCLE_ARCHIVE_AND_DELETE_RUNBOOK_R1.md) and [exact owner task](repository-maintenance/V065_M1_CODEX_CLEAN_MAIN_DOCS_LEGACY_BRANCH_PRUNE_R1.md).
- [Path disposition / exact source provenance](repository-maintenance/PATH_DISPOSITION.json).
- [M0 full branch manifest](repository-maintenance/m0/V065_BRANCH_CONSOLIDATION_MANIFEST_R1.md), DAG inventory and verification receipts: historical engineering, not daily research instructions.
- infrastructure/ — deployment and offline G3 operational notes; historical-engineering/ — retired process notes; ci/ — CI maintenance context.

Some runtime/test-referenced compatibility documents remain unchanged on main. No protected payload was copied. Historical files preserve their original wording and exact source blobs; their old READY/NOT EXECUTED labels are historical, not the current M1 execution state. [M1 actual execution receipt](repository-maintenance/V065_M1_EXECUTION_RECEIPT_R1.md) records published main/docs/archive, verified backup/reachability, actual CI, 0 deletions and explicit admin holds. The topology is not finished. This branch creates no independent source/science/Alpha/release authority.

## Active Controller B documentation (English, R5)

- [Controller B role](docs/roles/V0.6_CHATGPT_0_PRIMARY_CONTROLLER.md) — default Codex/Agy-first routing and on-demand audit threshold.
- [B-line project status and roadmap](docs/project/V0.6_PROJECT_STATUS_AND_ROADMAP.md) — R1 engineering completion, sample sufficiency and R2 expansion priorities.
- [Execution-first dispatch policy R5](docs/project/V065_EXECUTION_FIRST_CONTROLLER_POLICY_R5.md) — lightweight verification ladder, Chinese owner-facing conversation, and copy-button-only task cards.
- [R4 compatibility pointer](docs/project/V065_EXECUTION_FIRST_CONTROLLER_POLICY_R4.md) — superseded; retained only for old links.
- [New Controller B chat bootstrap](prompts/v0.6/chat_handover/V065_NEW_CHAT_B_LINE_CONTROLLER_R3.md) — current English R5 start prompt.

These are published on the independent **docs/engineering** branch. They do not modify executable main **v0.6.5** or the owner's uncommitted local research checkout.

## Latest R6 research architecture (2026-10-20)

- [Native 2022 Binance data-gap forensics, P1-R2 ML engineering plan, multi-asset result and P3 outcome readiness](docs/project/V065_R6_NATIVE_DATA_RECOVERY_ML_AND_P3_READINESS_20261020.md) — authoritative R6 status; older R5/R2 assignments below it are historical.


## Historical V0.7.0 strategy research status (2026-10-23)

The V0.7.0 price-primary campaign has completed three one-shot historical trials. No positive after-cost strategy is established; the three remaining PRIMARY slots are intentionally unassigned. These current reports supersede the old V0.6.5/R8 queue for V0.7.0 strategy decisions, while preserving R8 artifacts as separate historical evidence.

- [V070 project status and research roadmap](docs/project/V070_PROJECT_STATUS_AND_RESEARCH_ROADMAP_20261023.md) — current branch/registry state, terminal decisions, research queue and ML/DL gates.
- [PRIMARY-01 to PRIMARY-03 results and failure analysis](docs/project/V070_PRIMARY_RESULTS_AND_FAILURE_ANALYSIS_20261023.md) — exact economic/support findings and lessons across the three registered trials.
- [Astra research directions after PRIMARY-03](docs/project/ASTRA_V070_POST_PRIMARY03_RESEARCH_DIRECTIONS_20261023.md) — constraints for independent mechanism discovery and next research decision.
- [Astra independent mechanism discovery prompt](prompts/v0.7/ASTRA_V070_INDEPENDENT_MECHANISM_DISCOVERY_20261023.md) — one research-only prompt; no data reads, backtest, model fit, registration or trial execution.

These updates are documentation-only commits on docs/engineering. They do not alter the executable v0.7.0 branch, the local dirty research worktree, the active registry, any frozen trial, or any source/experiment authorization. The old V0.6.5/R8 status remains historical context and is not merged with the V0.7.0 PRIMARY ledger.
