# quant v0.6.5 — Shared Agent Operating Rules

Owner-selected default effective 2026-10-17. Apply to Codex, Gemini/Astra, ChatGPT Controller and other local agents that use this checkout. **Owner's explicit task-specific overrides have priority.**

## Single shared integration home and Git discipline

- Work in `/root/workspace/project/quant-0.6.5`, the working checkout of the public repository `EXASHXE/btc-quant-agent-public`, branch `v0.6.5`. Refresh the remote HEAD before consequential edits. Never assume a cached SHA is current.
- **Default: operate directly on `v0.6.5`**. Do **not** create a new Git branch, worktree, detached development checkout, pull request or CI workflow for each task by habit. Only do so if Controller/Owner explicitly selects an exception.
- This is a **single-writer shared workspace**. Parallel agents may read, analyze, or prepare separately named reports, but **must not concurrently edit, stage, reset, cherry-pick, commit, pull or push** this checkout. Serialize each write batch with the shared lock `/tmp/v065-main-worktree-writer.lock` (use `flock` where supported); a tool/agent unable to honor the lock must remain read-only.
- Before editing: check `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, and fresh remote `v0.6.5`. If any unrelated dirty state or unexpected branch/SHA exists, **STOP**, do not overwrite another agent's work. Never auto-stash, auto-reset, force-push, discard unknown files, or silently change authorship.
- For approved routine changes, implement and test only the bounded paths on main. Stage only explicit files; show `git diff --check`, scoped tests and exact commit/tree/changed files. Use the **true authorized author identity**. Direct commits/pushes on `v0.6.5` require task-specific Controller/Owner approval, check exact upstream SHA, and use only **non-force** push. A user asking for analysis does not implicitly authorize GitHub writes. Independent review can use a read-only checkout or an external report without a review branch.
- No simultaneous "multiple writers on main"; parallel work is read-only, or local draft artifacts outside Git, followed by serialized integration one change-set at a time. Never claim that branch avoidance allows competing writes.

## Data roots, migration and protected assets

- Owner-approved receiver host: `hyz-laptop`. Owner-approved **data root**: `/root/workspace/project/crypto-data`, sibling of (not inside) the Git checkout. The new SOURCE_QA prospective subdirectory is `/root/workspace/project/crypto-data/prospective/source-qa`.
- Downloaded historical pilot files R10/R11-D2 were moved into `crypto-data/historical/`. Old pilot `data` paths are compatibility symlinks, verified by migration receipt `crypto-data/_control/HISTORICAL_RELOCATION_RECEIPT_R1.json`. Preserve both the target and links. Raw data and receipts must never be added to Git, chat, external LLM prompts or PRs.
- **Continuous/periodic acquisition has not been cut over.** The existing `btc-quant-forward-derivatives.timer` operates on the original `/root/workspace/project/Quant-agent/data/forward/...` and other timer-based jobs may exist. Do not stop, change, move, symlink, delete, or redirect these active/legacy stores without a separately verified quiesce → transactional snapshot → WAL/integrity/hash check → atomic cutover → rollback plan and specific Controller approval.
- Never search, edit, migrate, replay or expose data in `/root/workspace/project/Quant-agent`, `Quant-agent-sanitized`, `history`, protected A-line H39/H40/H41/Forward/Final/OOS, private archives, private accounts or credentials merely because they exist. Named read-only scheduler metadata is not permission to touch their data.
- Do not relax existing raw/queue/disk caps, overwrite immutable receipts, assume filesystem symlink safety, or allow a data tool to recursively follow links into prohibited roots.

## Source-QA and scientific gates

- Owner has declared personal/noncommercial `SOURCE_QA_ONLY` and selected host/root; **this does not itself grant Binance or vendor feed/retention rights**. The Owner has not yet fixed the UTC 15-minute T0/T1 or produced a qualified <=10ms clock/durable receiver proof. No real SOURCE_QA REST/WS connection or collection until these are independently cleared and Controller grants one exact bounded START.
- Accepted R3 causal-clock result `CLAIMED_TIMING_ELIGIBLE` means internal arithmetic consistency of caller-supplied claims, not proven original source receipts, native byte lineage or fsync.
- Hard retained gates: `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
- No real trading, testnet, credentials/funds changes, new strategy trials, A-line or protected datasets, source downloads/collectors, production deployment, CI/workflow changes, or legal entitlement assumptions absent explicit separate permission.

## Output and handoff

- State actual host, repo SHA, modified paths, tests, status and evidence limitations. Put bounded local receipts under `crypto-data/_control` for data migration/receiver readiness, or a task-specific external report directory; do not indiscriminately publish sensitive paths or raw data.
- Prefer one useful finite task and STOP on missing rights, source identity, clock/durability evidence, active-writer ambiguity, unexpected Git state or unsafe move. Avoid repeated architecture/review cycles that cannot close a real gate.
