# v0.6.5 — Research-First Operating Contract R2

**State:** owner-directed operating policy, selectively reconciled under V065-M1; independent source/Alpha/release acceptance remains pending. **Observed source:** `v0.6.5@065d62965373627c4887e52f482d1dcb984af860` (2026-10-16). This document changes coordination and documentation priorities, **not GitHub Actions code/triggers, branch protections, source rights, protected data or release authorization**.

**Owner clarification (2026-10-18; Controller dispatch guidance only):** When Controller assigns tasks or writes prompts, prefer the existing `/root/workspace/project/quant-0.6.5` checkout and `v0.6.5` main branch; **do not routinely require new branches/worktrees**. If concurrent tasks would conflict, schedule their write phases sequentially or explicitly authorize another approach. This is a **prompt-writing and task-dispatch preference**, not a locally enforced Codex/Gemini rule, lock requirement, or permission to publish without authorization. Do not create `AGENTS.md` or `GEMINI.md` for this preference. Owner-approved data root is `/root/workspace/project/crypto-data`; its active legacy stores still require verified cutover. Scientific and trading gates are unchanged.

## 1. One current objective, one active repository home

- **Main objective:** find and independently establish a genuinely differentiated, after-cost, executable **BTCUSDT 4–24h** opportunity. BTC/ETH historical data collection, QA and source/clock understanding are enablers, not Alpha by themselves.
- **Research-first, private/noncommercial/nonproduction:** optimize time-to-next-informative-result. Stop accumulating speculative architecture, CI refactors, cross-branch status snapshots and repeat review cycles that do not resolve a named blocker.
- **Single integration home:** `v0.6.5` is the current B-line development/integration target, **not yet an independently accepted scientific or release baseline**. Verify its moving HEAD before work. Controller task prompts should select the latest verified `v0.6.5` snapshot and the existing main checkout by default, without automatically requesting task branches/worktrees. Where two tasks need to write overlapping files, Controller must sequence their execution or document a specifically approved alternative; this is not enforced by additional local agent configuration. Historical docs/feature/proof/repair branches are reference-only unless Controller selects exact patches. `v0.6`, `v0.6-docs` and `v0.6.1` are no longer competing active homes. M1 completed the verified GitHub default switch: the 2026-10-17 observed default is `v0.6.5@941f24af8f1e12c1f314e2d970e7af8f97293b21`. The docs-only orphan `docs/engineering` and archival `legacy/research-archive` are separate. Moving HEADs must still be refreshed; this does not establish scientific or release acceptance.
- **A-line is separate.** No automatic H39/H40/H41/Forward/Final/OOS, private data or A-line merges.

## 2. Current facts and gate order (do not infer more)

| Track | Evidence as observed at v0.6.5 checkpoint | Immediate bounded decision |
|---|---|---|
| Consolidation | M0 candidate `065d62965373627c4887e52f482d1dcb984af860`; docs-focused integration and local validation, independent integration review not evidenced | Independent integration verification; no blanket source/strategy promotion |
| Source/data | R11-Q1 `8c3e53f8fe37d9a8acd340944b843e04f05d2fdc` BLOCKED consequential; R11-Q2 `c07c60385479f0d595352ad751c1c49150b4cbbc` allowed bounded data pilots | Review new source evidence separately; do not erase earlier Q1 |
| Binance D2 | `803a4173717ace9c03ff97051b7696210e183bef` author DELIVERED | Focused independent code/data/rights/PIT review, not auto-accept |
| OKX E2 | `7f8c6acadead47dccdeba80b2ae27c2497ee8cdf` author DELIVERED | Portal-specific rights and per-object QC review, not auto-accept |
| Capacity C2 | `9dbb0ce7d266c0d6731775a7a53170bf34400520` STOP_UNMEASURED_SOURCE | Obtain owner-designated measured free space/sample bytes; owner may add disk; no speculative arithmetic loop |
| Research/Trading | G2_ALPHA_NO_GO, TESTNET/LIVE NO_GO | Data/source/PIT/cost first; no fresh Alpha claims or money writes |

**Near-term critical path:** independent finite D2/E2 assessment → Controller R11-Q3 decision separating *offline DEV engineering usability* from *scientific source/PIT admissibility* → measurable capacity and minimal ingestion path if still needed → 2-R novelty/source-qualified hypothesis → 2-C targeted challenge → independently authorized non-exposed test **only after** prerequisites. A failed source route triggers a cheaper alternative or STOP, not endless paper repairs.

## 3. Controller's mandatory owner-facing interface (UI first)

Default one-screen response: **(a)** phase + `v0.6.5@SHA` + priority objective; **(b)** 4–7-row dashboard of Data, Strategy, Engineering, next gate, blocker and TESTNET/LIVE; **(c)** clear Controller decision (`GO_FOR_BOUNDED_TASK`, `WAIT_FOR_EVIDENCE`, `STOP`) with a reason; **(d)** parallel-ready task cards and exact dependencies; **(e)** one concise “what changes the decision” condition.

Each **task card**: ID + short title + `READY/RUNNING/DELIVERED/BLOCKED/CONDITIONAL`; executor **plus actual model mode if observable**; one-line goal; exact SHA/path ownership and write boundary; original **immutable GitHub prompt URL**; a **one-click copy** action when the host supports it, otherwise one copyable block or link; expected deliverable and completion gate. **Do not print full prompts in the primary narrative**, do not repeat already-completed prompts, and never invent a saved prompt URL or copy button. For a real full prompt, prefer a task-specific external local report/prompt file and a verified checksum or an inline copyable block; only publish the prompt directly on v0.6.5 under separate Controller Git-write authorization. Do not create a dispatch branch by default, and never claim an unpublished path is a GitHub URL.

Controller should proactively present a **small dispatch pack** of independent READY jobs plus conditional successor cards (marked **NOT DISPATCHED**), not serially request the owner's permission for every obvious dependent document. Prefer parallel read-only analysis and nonconflicting task deliverables; Controller should sequence overlapping write tasks in dispatched prompts rather than impose a host-wide mandatory lock; **one substantial task per chat**. Distinguish owner choice from true missing jurisdiction/path/license or high-stakes permission.

**After results:** show delivered/independently-reviewed/Controller-adjudicated statuses separately. Change only the status and next action; evidence remains at exact Git SHA. A task author cannot mark own scientific claim accepted. One owner-facing card should never turn a negative finding into a green “success”.

## 4. Assign work by value and independence — no custom subagents

| Role / executor | Dispatch when | Do not dispatch when |
|---|---|---|
| **0 Controller** | critical path, task packets, ownership and sequencing, scoped decisions, R11-Q3 integration/data L2, stop/replan, owner dashboard | routine content rewriting, repeated checking of static receipts, large duplicated audit reports |
| **1 Auditor** | **consequential** independent source/rights/PIT/execution cost/causal-contract validation; selected release or major integration acceptance | every README typo, boilerplate checklist, tiny deterministic patch, every ordinary DEV ingestion |
| **2-R Researcher** | source-qualified, novelty crosswalk, at most a small number of falsifiable BTC hypothesis families, meaningful information-gain design | generic indicator brainstorming, reparameterized old failures, unfrozen outcome fishing |
| **2-C Challenger** | challenge a concrete material 2-R hypothesis/novelty/causal assumption or conflicting scientific claim, optionally concurrently with unrelated tasks | mandatory ceremony for every research note or docs-only change |
| **2-E Direct Executor** | short bounded docs, links, deterministic test fixture, exact metadata and small low-risk code edits | multi-file ingest implementation, source-rights interpretation, cross-module PIT/accounting or independent acceptance |
| **Codex High/Sol** | high-correctness repo integration, local source QC, data pipeline, consequential coding and bounded reproducible tests | as a reflex for plain docs or trivial text updates |
| **Gemini NORMAL / BOOST** | NORMAL for bounded deterministic implementation; BOOST for genuinely cross-module/state/economics architecture when justified | costly BOOST for mechanical edits or uncontrolled recursive agents |

Use one writer per path; a different role must independently accept material source/Alpha conclusions. The Controller may combine ordinary engineering planning/review steps without invoking every chat. Do not invent user-defined subagents or rely on assumed app/model entitlement.

## 5. Risk-weighted verification instead of all-tests-always

**T0 — Docs/links/status/dispatch:** verify target ref, changed file/path, Markdown link destinations if readily checkable and `git diff --check`. **No mandatory pytest, full Ruff, mypy, compatibility matrix, safety-suite rerun, or hosted full CI** for documentation-only changes. Existing automatic CI may still fire; record the actual result; changing triggers requires separate authority.

**T1 — Low-risk research utility / known parser presentation:** run new/changed-module targeted tests, minimal Ruff/compile/import sanity as relevant. No project-wide suite by default. Historical inherited lint debt should be reported, not repeatedly repaired as a prerequisite for unrelated research. Avoid duplicating local and remote full-suite runs.

**T2 — Source bytes, timestamps, PIT/Mark/Funding/OI, contract units, costs, accounting, ledger, order-boundary:** run deterministic focused *positive and negative* evidence for **the changed invariant**, publisher integrity/rights where applicable, and one independent technical or consequential review **only if the change is used as source/science/financial authority**. Do not require full unrelated H39/H40/H41 suite or every historical scientific challenge for an EXPOSED_DEV data-QC report. Clearly label author-only receipts and unverified clocks.

**T3 — Cross-module executable promotion, real integrations, TESTNET/LIVE, financial write capability, release:** restore/use full relevant suites, required exact-SHA CI/protection checks, negative trading/funds tests and genuine independent go/no-go. Engineering success != Alpha. No lowering of these gates by relabeling work as “research”.

**CI resource policy:** keep existing tests and manual recovery path intact. Simplify schedules/automatic triggers *only through a separate verified branch-protection/CI task*. While `BRANCH_PROTECTION_VERIFICATION_PENDING`, do **not** edit workflow or claim it is disabled. Skipped tests must be described as `NOT_RUN_BY_SCOPE`, never `PASS`. Track task time, spend, bytes and the **next uncertainty removed**, not percentage of checklists completed.

## 6. Minimum durable evidence, not receipts for receipt's sake

Every substantive published task returns: **task ID / author SHA / parent / actual branch (normally v0.6.5) / changed paths / report or code blob / one-line terminal / tests actually executed or NOT_RUN / residual blocker**. Long per-file ledgers only for changed causal/source/financial invariants; proofs may be stored in Git, linked once in the owner UI. Documentation-only work needs exact main SHA/diff and link integrity, not a new branch or 3 layers of independent review. Work should stop when the prescribed material question is answered, if STOP reached, or further data would not change the decision.

## 7. Unchanged boundaries and revision mechanics

Retain distinct labels: `source exists` ≠ `lawfully permitted` ≠ `checksum verified` ≠ `historically known-at` ≠ `financially executable` ≠ `Alpha`. Keep UTC and native contract units, original clocks/versions, exposed DEV vs protected OOS, account/NO_ACTION and real-funds separation. At present `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

**Authority order:** explicit current owner decision → exact-SHA Controller scope and independently verified evidence → current `v0.6.5` integrated snapshot → dated legacy roles/roadmaps. A new owner-directed R2 operating contract may streamline *documentation and engineering review cadence*; it does not retroactively rewrite frozen independent audits, license data, authorize protected samples, trades, or release. Historical 2026-10-16 role/status originals remain available unchanged at `v0.6.5@065d62965373627c4887e52f482d1dcb984af860`.

**Integration:** V065-M1 selectively reconciles PR #6 at exact source `9ec13bb44dc674c45c7099db1ff2177ea60393ff`. Current research contracts stay on main; the full CI/model engineering process lives on docs/engineering. This is documentation adoption only, not independent source, Alpha or release acceptance. Verify actual moving refs before new work.

## 2026-10-17 R3 research-strategy review addendum

M1 pruned 173 remote refs (222→49). Three desired long-term branches now exist; 42 A-line/control and four PR #3/#5 references remain governance HOLD rather than B-line blockers. M1 main `941f24af8f1e12c1f314e2d970e7af8f97293b21` scoped CI #38918484549 SUCCESS does not mean complete research or deploy PASS. The weekly cron was removed; push/PR/manual CI retained.

The owner's current priority is an **independent read-only whole-repository review** of BTCUSDT perpetual 4–24h strategy-discovery and scientific testing defects. [Frozen external review dispatch](../../prompts/v0.6/review/V065_BLINE_FULL_REPOSITORY_STRATEGY_REVIEW_SOL_ASTRA_R1.md). Do not overbuild CI, speculative source infra or repeat failed Alpha ideas without new mechanism/source/regime witness. The reviewer gives evidence-tagged diagnosis, up to two falsifiable mechanisms (zero allowed), and a finite 1–2-week DAG; Controller 0 makes the research decision and 1/2-C independently validate consequential claims. Research/testnet/live/funds gates remain unchanged.
