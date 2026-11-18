# V065-CODEX-0655 — P1 executable BTC 4–24h cost-aware evaluation engine

Role: Codex 6.1 Sol HIGH, time slot 2026-10-18 06:55 Asia/Shanghai. This is an intended **heavy CODE task** only if a writer slot has been affirmatively released. Owner R4: at most two concurrent nonconflicting writers; never infer slot release merely from an old manifest or files appearing. At scheduled start, check repo state, job receipts and current Codex/Agy processes; if no Controller WRITER_SLOT_RELEASED, DO NOT modify repo and instead issue concise HOLD_NO_WRITER_SLOT. Never disturb another agent or trigger F-R2 production cutover.

Repo /root/workspace/project/quant-0.6.5 (v0.6.5). Confirm remote/local branch HEAD before write; preserve all currently dirty Owner R4 docs/roles/prompts and ongoing P0/data code; no stash/reset/checkout/branch/worktree/commit/push by default. Prompt is published solely in GitHub docs/engineering, no local task prompt copies. Model gpt-6.1-sol, reasoning effort high, do not claim Max unless configured/verified.

If and only if slot ready, own a **new disjoint module**:
scripts/research/strategy_eval/cost_aware_eval.py; tests/research/strategy_eval/test_cost_aware_eval.py; optional strictly scoped tools and tests within the same module. Do not write into scripts/research/r11_d2, tools/data or tests/data (the current P0 and acquisition owners). No unapproved dependencies or repo-wide CI.

Implement an actual reproducible offline strategy testing framework:
- Three baselines: fixed-origin NO_ACTION, a simple preregistered lagged price/volume trend rule, and increment-only hypothetical Z over X. All actions derived exclusively from information eligible before each fixed origin; missing or clock-unknown Z is NO_ACTION, stays in the denominator and cannot be backfilled or reindexed.
- Strategy horizon selectable 4h/8h/12h/24h; frequent simple re-evaluation must model overlapping exposure and avoid fake independent trials. Train/test chronological splits plus purge/embargo boundaries, frozen configs and deterministic seed.
- Maker vs taker fees, bid/ask spread, slippage, adverse selection allowance, funding timestamp events, variable liquidity/cost sensitivity, ATR/volatility risk and return in R units. Explicit ledger for entry/exit, net PnL after all costs, no-action count, frequency and utility; never assume maker fills without a fill model. Synthetic default fixtures and offline historical data labelled PIT_UNKNOWN.
- Real data adapters ONLY for properly mapped read-only existing nonprotected Binance/OKX historical documents where QC compatible; exclude protected OOS; maintain exact timezone and swap/spot distinctions. If uncertain, use synthetic and demonstrate deterministic tests.
- Outputs compact JSON + CSV of baseline/candidate metrics, missing-Z coverage and trial metadata. Include portfolio risk-limits and avoid claims of positive after-cost alpha from trivial synthetic fixtures.

Run focused positive and negative tests (fixed clock, no future leak, fee/funding arithmetic, missing Z, time-split, reproducibility, exposure overlap, data-missing failure). Demonstrate one command:
python3 -m scripts.research.strategy_eval.cost_aware_eval demo --output-dir <new_empty_dir>
Adjust actual entry point only if package layout requires. Separate non-versioned outputs outside Git.

Definition of done: P1_EVAL_DEV_READY = working demo, reproducible after-cost ledger, scoped test results and code diff; P1_EVAL_BLOCKED = exact technical blocker and no partial false claims. This is normal code, no 1-A/2-C chain. If P0 integration not yet done, keep the P1 evaluator standalone.

ALWAYS preserve SOURCE_NOT_ADMITTED, PIT_UNKNOWN, NO_ALPHA_ESTABLISHED, G4_TESTNET_NO_GO, LIVE_NO_GO and REAL_FUNDS_WRITE_NONE. Never change production systemd, start collectors or access user accounts.