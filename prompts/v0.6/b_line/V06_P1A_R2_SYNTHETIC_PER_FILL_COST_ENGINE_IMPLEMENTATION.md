# Controller Dispatch — P1A-R2 BTC Synthetic Execution-Cost Engine (Finite 24-Case Contract)

**Owner:** ChatGPT-0 B-line Controller. **Executor:** Codex Sol High (preferred) or Gemini NORMAL for strictly bounded isolated engineering; independent Codex Sol/ChatGPT-1 for consequential finance review.
**DISPATCH_ID:** V06_P1A_R2_SYNTHETIC_PER_FILL_COST_ENGINE.
**DISPATCH_SHA:** immutable Git commit containing THIS file, passed as exact link in the task handoff. Read the complete immutable P1A R1 plan at a68eeef973a178a68005f7eca247ec15bc9bf2a2 and prior Controller L2 at efa2df62c02d21b20ce07846c7ca30901716e773.
**EXECUTION BASE:** exact tested R3 engineering source 3af438490da4497132a5c32c786752ca527e0d99, NOT the frozen R3 measured result commit. Separate worktree branch feature/v06-p1a-r2-btc-synthetic-per-fill-cost-engine. No implicit cherry-pick/merge and no new historical trial.

## Scope principle

The frozen R3 execution-cost policy (BASE22/STRESS44) must remain unchanged and reproducible. DO NOT rewrite old engine.py or portfolio.py and DO NOT reprice or replay historic R3/W1/W2/Goal-B returns. Build an isolated NEW synthetic-only Decimal cost-contract module whose output is NOT wired to old experiment scoring or live orders.

## Exact write allowlist

- scripts/strategy_research/g2_btc_exit_aware_r3/cost_contract_synthetic_r2.py (new)
- tests/test_v06_btc_cost_contract_synthetic_r2.py (new)
- reviews/v0.6/b_line/V06_P1A_R2_SYNTHETIC_COST_CONTRACT_REPORT.md (new)
- evidence/v0.6/b_line/p1a_r2_synthetic_cost_contract/SYNTHETIC_TEST_RECEIPT.json (new)

Read-only frozen comparators: R3 engine.py and portfolio.py at 3af438490da4497132a5c32c786752ca527e0d99 and P1A R1 design report at a68eeef973a178a68005f7eca247ec15bc9bf2a2. No source collectors, secrets, historical datasets, brokerage adapters, funding source adapters, dependency edits, configuration changes or machine-outcome files.

## Required implementation

1. Signed Decimal ledger for LONG/SHORT, fee by each **actual filled leg** (not LIMIT/MARKET label), notional-specific maker/taker rate and fee currency assumption. Reference fee cases M/M 4bp, M/T 7bp, T/T 10bp, explicitly only fee-only abstractions.
2. Fill-versus-arrival-mid drag, correct half-spread and no additional spread deduction if bid/ask already drives fill; separate impact only if not in actual VWAP.
3. Partial fills and partial exits with conserved BTC quantity, never fee unfilled portion, appropriate residual inventory/MTM, idempotent fill and settlement event identity. Explicit tick/step/min-notional/signed rounding and conservation.
4. Funding is signed at observed **economic settlement exposure** times Mark and rate, with receiver-known-at never backdated. For absent Mark/rate/source chronology mark COST_INCOMPLETE, never synthetic realized cash zero. Stop-market gap versus stop-limit unfilled, and ACK-delayed BE protection are distinct paths.
5. Unit invariance: BTC notional bps unaffected by leverage, while margin ROI is a separate contract.
6. Include the complete 24 named synthetic cases in the P1A report, plus negative cases for duplicate/conflicting IDs, nonfinite, crossed/stale quote, same-clock ambiguity, unfilled maker entry, rounding quantization and short signed funding.
7. Verify reported exact invented-ledger net USDT LONG 8.834600; SHORT 9.044600; partial LONG 6.875760; partial SHORT 7.003760; flat-mid crossed spread -1.040000; adverse LONG 8.694600; stop gap LONG -11.055000; mixed-role 9.067006. Keep exact Decimal expected strings.

Run targeted pytest and Ruff first. Preserve unknown-executable full CI if called; existing H41 lint debt can block docs CI and must not be suppressed or patched under this task. Commit source+tests+receipt on the isolated branch with exact parent/HEAD and actual CI step outcomes. Enforce reviewer independence; no self-issued release permission.

**PASS:** synthetics exercise 24 finite cases and sound cash/known-at invariants under L2 independent source review. **HARD STOP:** unexpected dependency/extra path, need for real exchange source/fill evidence, any backward reinterpretation of R3 results, incomplete signed conservation. **TERMINAL:** SYNTHETIC_COST_ENGINE_ACCEPTED_PENDING_MEASURED_SOURCE or CONTRACT_BLOCKED. This is NOT actual execution-cost calibration, PIT source acceptance or G2 Alpha.
