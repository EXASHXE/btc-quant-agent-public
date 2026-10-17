# V065-CODEX-0410 — Long-horizon BTC strategy mechanism diagnostics (READ-ONLY)

Role: Codex 6.1 Sol MAX, independent deep quantitative analysis operator. Approximate dispatch window: October 18 2026 immediately, Asia/Shanghai. Aim for serious multi-hour scientific work where evidence allows. **This is a third READ-ONLY lane; two code writers may still be active. Do not release writer slots or start the held forward cutover.**

Project: /root/workspace/project/quant-0.6.5 on v0.6.5. Owner R4 favors implementation and reproducible decision-changing research, not serial review/audit. Read current git status; 14 Owner role/roadmap files are dirty and must not be modified. Existing Codex P0 offline demo and Agy Binance/OKX acquisition remain owned by their implementers; do not touch their code, data, working state or processes. No git branch, worktree, commit, stash, checkout, clean, reset, push or local task prompt file.

Research mission:
1. Map already-evidenced failed and inconclusive BTCUSDT 4–24h strategy families from repository documents: trend/breakout, microstructure/price-volume, funding/basis, OI/position state, timing/landmarks, maker economics. Treat tests from protected OOS/H39/H40/etc as **off-limits**; do not attempt to reproduce confidential targets or peek at protected market rows.
2. Inspect available *nonprotected* new Binance/OKX expansion manifests and QC (and small allowlisted samples only where clearly appropriate), confirming exact UTC vs OKX UTC+8 naming; instruments BTCUSDT USD-M vs BTC-USDT-SWAP; historical native timestamps are NOT receiver-first-known PIT. Evidence currently includes 210 Binance and 463 OKX QC-PASS objects in first tranche; independently verify current numbers and remaining coverage rather than rely on prior text.
3. Form a shortlist of at most THREE genuinely differentiated BTC 4–24h mechanisms. Prioritize (A) incremental derivatives position-state Z over lagged price/volume controls X, (B) post-impact liquidity recovery from actual timestamped OKX L2/trades, and (C) robust regime/breakout only if it adds an observable not already falsified. Every candidate must specify fixed decision clock, X,Z, economic edge hypothesis, source mapping and falsification; zero truly source-compatible hypotheses is a valid outcome.
4. Create a *source-independent*, executable research protocol for P1: feature timeframe, 4/8/12/24h horizon, no-action population, observed-vs-missing Z count, data leakage and lookahead controls, nested chronological splits/embargo (where appropriate), multiplicity budget, transaction costs including maker/taker/slippage/funding and win-rate vs after-cost utility. Do not invent profitable returns or claim live fills. At most bounded exploratory offline statistical summaries on permissibly obtained historical objects; no retrospective reconstruction of receiver provenance or trial on protected OOS.
5. Use existing analysis tools if read-only; for calculations/test fixtures use ephemeral /tmp scoped scratch only and remove it after; a single **operator report** outside repo is permitted:
   /root/workspace/project-review-output/v065-sol-strategy-readonly-r1/STRATEGY_DIAGNOSTICS.md
Include SHA256, an evidence-tagged mechanism matrix and a machine-executable test plan for the next coding agent. If an active pipeline agent has already implemented portions, reference their live code without modifying or duplicating.
6. Avoid more "review of reviews". A short credible negative conclusion or tested discriminator is more valuable than a generic 10-page methodology memo.

Safety and concurrency:
- READ-ONLY git and dataset reads. No data acquisition, new WebSocket, trade, account, source-QA, systemd actions or active forward-store access.
- No code writes anywhere in the engineering repository or in crypto-data/historical. If another agent is writing, do not interfere.
- This is a personal research project, but historical native exchange data still lacks original receiver PIT. Annotate exploratory information as HISTORICAL_OFFLINE / PIT_UNKNOWN, not source-admitted.
- Do not exceed storage/memory available; keep data scans sampled and bounded and terminate cleanly.

Terminal: RESEARCH_READONLY_COMPLETE with factual report path and SHA256, or RESEARCH_READONLY_BLOCKED. Send Controller a concise handoff indicating useful result, not more process gates.

## Owner latest reasoning & parallel data override (2026-10-18)
- **Model: GPT-6.1 Sol, reasoning effort MAX.** Verified installed codex-cli 0.163.0 model catalog explicitly lists `max` and `xhigh`; installed config also defaults to `max`. Invoke `codex exec -m gpt-6.1-sol -c 'model_reasoning_effort="max"'`. **Only on confirmed max rejection** retry with `xhigh` (Extra High); don't downgrade routinely to `high`. Record actual CLI arguments and startup outcome.
- The Owner explicitly permits Binance/OKX historical data acquisition to run concurrently with Codex engineering in disjoint code/data paths. A data downloader is **not** automatically a blocking engineering-writer slot. Preserve repo ownership isolation, memory/swap headroom, pre-existing unstaged R4 work, and no duplicate writer on any single path. Running live collectors are separate from this authorization.
- If this scheduled occurrence finds an older Agent task completed, don't restart it needlessly. If memory/swap or overlapping code writes make the run unsafe, return HOLD with exact evidence instead of falsely claiming execution.
