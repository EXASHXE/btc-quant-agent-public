# v0.7.0 Current State and New-Chat Handoff
Verified reference date: 2026-10-28. This is a point-in-time documentation snapshot; always recheck current files/processes before action.

## Worktree inventory
- R: /root/workspace/project/quant-0.7.0/research-loop-bootstrap, branch codex/research-loop-bootstrap at 40c70c740f352d1b444decb75276196d17a72dd2; 12 pre-existing added paths under scripts/research/research_loop and tests/research/research_loop. New docs edits may appear after this snapshot.
- Q: /root/workspace/project/Quant-agent, branch v0.5-refactor, HEAD 6bd63db96e5b54b9cec27a74cd2f728e19fc5b7d; deployed forward collector points here. Do not touch runtime.
- M: /root/workspace/project/Quant-agent-market-watch, branch feature/b-line-live-v1, HEAD fde61dafb301d5bd5af3dc7eb81e5618f979036c; six modified tracked paths and one untracked test as observed. Preserve exact content.
- Registry: nine event files, three of six PRIMARY trial slots consumed and three unassigned. Hash chain must not change.

## Accepted engineering and scientific status
- T0/T1/T3: completed status/capability/community-inventory packages.
- T2: PARTIAL; sealed original failure remained as evidence.
- T2B: isolated canonical MARKET time-in-force fix validated (118/118 T2, 124/124 affected, 31/31 new); not integrated into R.
- F0: INSUFFICIENT_EVIDENCE for source integrity/safe consumer.
- F0A: PARTIAL_EVIDENCE; current instance-bound producer health not proven.
- F0B: isolated synthetic health publisher validated 51/51; NOT integrated into Q, not deployed.
- Power/MDE: reusable worksheet validated; actual next-study power not estimable with current inputs.
- DIAG-PREFLIGHT: PARTIAL; mainline paired E0/E1/E3 comparisons blocked by entry-clock and ATR provenance.
- H35–H38 prospectively committed opportunity campaigns are terminal/archived; no verified complete current advisory/forward decision→outcome lifecycle.
- PRIMARY-01/02 modeled BASE negative, PRIMARY-03/C1 low support, latest mainline 29 trades exploratory and negative modeled BASE. No independently validated after-cost directional Alpha or native full-net claim.

## Astra Argon 2026-10-28 code review — high-value hypotheses to verify with tests
1. collect_symbol_snapshot derivatives-error path may use uninitialized premium_index_time_ms/next_funding_time_ms.
2. klines available_at_ms is pre-request server timestamp rather than actual response receive time; closed 15m close is not executable quote.
3. stale inputs and cross-symbol benchmark dependency clocks need a fail-closed admissibility rule.
4. scanner sends external alert before storing evidence, and notify=False may mark a selection as already sent.
5. static ATR TP projections can be mislabeled structural; fixed two-period funding assumption is insufficient for dynamic positions.
6. supervisor risk events are not fully wired from live runtime; STOP_NEAR alone misses already crossed stops; management actions lack deterministic compilation.
7. Tick-size precision and dedup fingerprints are inconsistent across low-priced instruments.
These are code-review findings, not proof of a live incident. Validate with targeted synthetic tests.

## Immediate next Owner/Codex action
V070-ADVISORY-FOUNDATION-01, see linked task card. First select a safe integration baseline, then implement only the bounded foundation in isolated code with synthetic tests and a concise patch. Do not merge into current dirty trees, restart services or send real external messages under documentation authority alone.

## New conversation
For the independent ChatGPT advisor role (not a duplicate Controller), read [its role](../roles/V070_CHATGPT_STRATEGIC_ADVISOR.md) and [copy-ready startup prompt](V070_CHATGPT_NEW_CHAT_START.md).
For Controller 0-C, start from this handoff plus Mission, Roles, Roadmap and Task Card. Request a read-only state reconciliation first, then proceed only under an explicit new implementation approval. Do not recite legacy roadmaps as current product goals. Optimize for a useful, honest, read-only advisory vertical slice, not repeated governance paperwork.
