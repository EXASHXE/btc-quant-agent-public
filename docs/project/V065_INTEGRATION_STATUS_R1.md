# v0.6.5 — Current Branch Separation and B-line Integration State

| Branch | Verified 2026-10-17 HEAD | Primary purpose |
|---|---|---|
| `v0.6.5` | `941f24af8f1e12c1f314e2d970e7af8f97293b21` | **GitHub default** B-line code and owner-facing research docs |
| `docs/engineering` | `84955be4cd947cf6a92a9e09c036daf4b948f3fb` | Separate docs-only orphan tree, with `ci/`, `infrastructure/`, `historical-engineering/`, `repository-maintenance/`; no `src/` or `tests/` |
| `legacy/research-archive` | `0176cdde836a660420e5e4b5693591cb8108a4f6` | Historical evidence and original commit ancestry, not active Alpha |

Structural layout is complete but branch retirement is **not**: M1 deleted 173 refs (222→49), leaving 42 A-line/control/old-default holds and four PR #3/#5 head/base dependencies. PR #3/#5 **KEEP, OPEN/DRAFT**. Do not delete governed refs from stale metadata or infer authority from GitHub admin permissions.

**CI boundary:** M1 main `941f24af8f1e12c1f314e2d970e7af8f97293b21` had actual scoped CI [#38918484549](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38918484549) SUCCESS; full compatibility/scientific tests SKIPPED. Weekly scheduled CI removed; push/PR/manual remain. M2–M4 docs-only receipts have no inherited main CI PASS.

**Research boundary:** D2/E2 author-delivered pending independent source/PIT/rights acceptance; R11-Q1 blocked; no validated after-cost BTC Alpha. The repo's next worthwhile task is [read-only full strategy/source/testing assessment](../../prompts/v0.6/review/V065_BLINE_FULL_REPOSITORY_STRATEGY_REVIEW_SOL_ASTRA_R1.md), not another branch-cleanup loop. Main/document layout completion does **not** approve G2/TESTNET/LIVE.

[Current research dashboard](V0.6_PROJECT_STATUS_AND_ROADMAP.md) · [Operating contract](V065_RESEARCH_FIRST_OPERATING_CONTRACT_R2.md) · [Role index](V0.6_NEW_CHAT_HANDOVER_INDEX.md) · [M1 receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/3f8edc26d95d93991a8b9a526c18f683d1be3dd1/repository-maintenance/V065_M1_REMOTE_PRUNE_EXECUTION_R2.md).

The owner-named local `~/workspace/project/quant-0.6.5` did not exist under the current connected root agent HOME; other local host/home environments may differ. Do not substitute protected original data paths; reviewer must validate workspace identity.
