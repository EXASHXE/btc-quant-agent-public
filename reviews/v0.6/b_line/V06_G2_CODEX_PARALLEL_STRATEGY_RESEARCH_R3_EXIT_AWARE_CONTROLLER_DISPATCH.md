# v0.6 B-line Controller — Codex Strategy-First Parallel R3 Dispatch

Date: 2026-10-13 (Asia/Shanghai). Authority: ChatGPT-0 Primary Controller, only B-line/G2 public-data exploratory research.

## 1. Why parallel now

Existing G2 BTC public empirical series: Codex R1 ended NO_STRATEGY_CLEARS_COST_AND_SUPPORT_GATE; independently frozen Codex flow/regime R2 final source head 3df7a9a490a06c398d20da57bf19fc48d3b1c74e; [R2 experimental development report](https://github.com/EXASHXE/btc-quant-agent-public/blob/3df7a9a490a06c398d20da57bf19fc48d3b1c74e/docs/strategy_research/g2_r3/flow_regime_r2/BTC_FLOW_REGIME_DEVELOPMENT_REPORT.md) and [promotion receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/3df7a9a490a06c398d20da57bf19fc48d3b1c74e/evidence/v0.6/b_line/g2_btc_flow_regime_r2/DEVELOPMENT_PROMOTION.json) show 6 hypotheses, no 2021–2023 development promotion; **2024–2025 R2 reserved February/June/September/December outcome files remain untouched**. R2 exit engine **already used actual stop/take-profit/time cap**, not a simple fixed-N-hour sell. New innovation is event-driven scale-out, stop transition and extended max hold, not rebranding a 2R fixed target.

Current separate engineering efforts:
- Gemini NORMAL fast-path: feature/v06-bline-gemini-normal-ci-riskmap-fastpath-r1
- Gemini BOOST lean architecture: feature/v06-bline-gemini-boost-architecture-lean-test-r1
Both at separate R3 B-line source base 97f4040b9380f2069575a989c066d1daeef15194 and have no permission to modify G2 strategy branch. The research Codex does not need Gemini CI or Clashed live L2 before conducting offline *public trade-price-only developmental* R3 tests.

## 2. Exact authorization

New code branch created **feature/v06-bline-g2-codex-btc-exit-aware-research-r3** at exact R2 final code SHA **3df7a9a490a06c398d20da57bf19fc48d3b1c74e**. Independent worktree /root/workspace/project/quant-v0.6/g2-codex-exit-aware-r3. Allowed to WRITE ONLY:
- scripts/strategy_research/g2_btc_exit_aware_r3/**
- tests/test_v06_g2_btc_exit_aware_r3_*.py
- docs/strategy_research/g2_r3/exit_aware_r3/**
- evidence/v0.6/b_line/g2_btc_exit_aware_r3/**
Can read original public G2 R1/R2 source & code and their **development-only** outcome reports/source manifests as explicitly exposed in old results; NO modifications to legacy G2 modules, prior FROZEN results or test files. No modifying .github/workflows, scripts/ci, Gemini A/C/R3, performance, A-line or src/**. No merges or force-push. No direct v0.6 main mutation.

Public data allowance: user-authorized Binance Vision USDⓈ-M BTCUSDT 1m **historical only, scoring 2021–2023 developer-exposed months** (R2 Feb/Jun/Sep/Dec, including registered warmups; publicly exposed R1 April only if explicitly versioned), with exact raw SHA256, stream temporal availability assumptions disclosed. Do not fetch/stat/read the *reserved 2024–2025 R2 Feb/Jun/Sep/Dec scoring months* or protected forward/old holdout; never touch user's Quant-agent/data, Quant-agent-sanitized, protected H39/H40/H41/Forward including filesystem metadata. Do not access private account/orders, API keys, credentials, user real balances, real trades, TESTNET/LIVE, LLM/Feishu external calls; no real funds. No automatic geographic proxy rotation or TLS disabling to access provider-blocked sources. Use only authorized fixed public route if needed; skip public data acquisition and report SOURCE_UNAVAILABLE if explicitly disallowed.

Publication: source hashes, methodology, aggregate monthly/yearly and hypothetical example trades ONLY. Do not commit huge raw market data or leakage of private/local proxy IP/node/credentials.

## 3. Exact research objectives

R3 tests bounded ENTRY × EXIT × MAX_HOLD hypothesis **4–24h BTC short swing**:
- At most three precisely specified (<=2 new + >=1 R2 baseline comparator) independently causal entry mechanisms, all using known historical Last/volume/taker-buy rows. OI, mark, funding, ten-level order book, slippage or historical true fees are UNKNOWN, must never be fabricated.
- Exactly three independently specified Exit Policies: (E0) legacy full close target2R + structural/ATR stop and bounded time; (E1) scale-out 40% at1R, 30% at1.8R, 30% at3R + move residual stop no better than legal next-minute observation; (E2) 50% at1.5R plus trailing 1hATR-based residual capped 3R, fail-closed when ATR missing. Sign/price/tick/collision ordering precise.
- Three max-hold caps 8h/18h/24h. Other early exit times allowed before cap; never use 24h full hold as a required PnL definition. 4h early exit distribution observed, no forced 4h minimum. Registered roster max **27 economic hypotheses** (3 entry × 3 exit × 3 horizon); base22bp/stress44bp cost replay are two cost scenarios per hypothesis, not extra free options. If an exit policy is incompatible with R2 engine it must be implemented under new R3 namespace, not by mutating existing frozen 2R methods.
- Reference economics: same-entry paired replay for exit delta, signal-only no-entry control, signed Decimal per partial leg, maker fill not guaranteed (baseline taker), volume dust/lot-round, stop-first when same minute stop and TP touched, unfavorable gaps, acknowledge latency, cooldown, independent monthly 1000USDT books, fees/slip/spread each actual executed quantity once, not multiplied incorrectly by partial-fill count. Funding historic realized price UNKNOWN; report adverse financing sensitivity explicitly, not zero-fee cash completion.
- Reject spurious return improvements due trade-count collapse: minimum opportunity and support thresholds predeclare, per-side/trade counts, active months/years, per-trade net bps, signed netR, PF, paired exit improvement, max close+dense MTM DD, turnover, fee/funding sensitivity, time-at-risk, stop vs partial exit legs, financial arithmetic auditable.
- Development only on 2021–2023 known historical source. Freeze all entry/exit rules and costing prior to evaluating new outputs; register all 27 alternatives, any excluded alternative counts in multiplicity; record each trial and false-discovery/multiple comparison adjustment. Positive development result can be named HYPOTHESIS_READY_FOR_INDEPENDENT_FUTURE_VALIDATION only, NOT Alpha, NOT TRUE OOS, and never permission to inspect reserved source. Negative result measured DEVELOPMENT_NO_GO, stop without unrestricted trials.
- A truly independent future confirmation requires another Controller-approved freeze, separate independent Agent, and heretofore unexposed properly admitted source. No precommitted R2 2024–25 reserved access automatically granted.

## 4. Efficiency / deliverables

Use Codex GPT-6.1 Sol (High if user menu supports, otherwise actual effective effort UNKNOWN; never invent). This is high-reasoning quant research, unlike mechanical Gemini NORMAL map. No endless "until profitable": maximum 27 predefined combinations, 2 cost scenarios, never tweak thresholds mid-run, at most 3 linear nonforce commits (freeze first pushed BEFORE dev output scoring; code+tests/evidence after; optional final report), one final heavy GitHub CI for changed executable code. Local focused tests 30+ with 5 independent manual Decimal trade reconciliations, no repeated 3454 test local+remote on every change. Old R2 complete code read-only.

Mandatory:
- OUTCOME_BLIND_R3_ROSTER.json + FREEZE_RECEIPT.json, exact SHA pre-outcome;
- public source manifest with 2021–2023 admitted periods and static permissions; lineage to R1/R2;
- entry/exit simulator under own namespace (no work on user data);
- month/year and per-side strategy performance with all 27 alternatives, including zero trades;
- partial TP/SL ledger raw synthetic witness and conservative same-minute fills;
- paired baseline vs exit-policy comparison;
- separate flag for invalid/no-source/nonfinite cost and PIT;
- exact-SHA CI report distinguishing local/remote, no docs-only tests falsely green.

Terminal: R3_DEV_HYPOTHESIS_ELIGIBLE_FOR_LATER_INDEPENDENT_VALIDATION, R3_DEV_NO_GO, or R3_SOURCE_OR_SCIENCE_BLOCKED. **Never** G2_ALPHA_PASS, G3 live provider or G4 TESTNET/LIVE approval. Controller L2 review required before any future independent validation.
