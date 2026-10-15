# R10-D0 | 2-E Binance Vision Offline DEV Pilot

Role: ChatGPT-2-E Direct Execution Operator. One bounded research task. Context: the user confirmed that historical market data will be used ONLY for personal, noncommercial, nonproduction offline strategy testing, not as a live-trading feed or commercial dataset. Budget: USD 0; no purchases. Source: Binance Vision ONLY; do not add Bybit, HF mirrors, Coinalyze or Tardis.

Immutable parent: R10-L4 Controller commit 285149095fc0d9a47ab86248d42fb609555a767d, report blob 8dfa7c93d2d6ad393df587c8eac7a7948afa14b0. Publisher: binance/binance-public-data@f446ce3812bd4e5521f21faecd4ae3c6460e49fc; Vision Dataset Terms blob 87d04e216f62c86a2c797fbb7637404d6d602687, §4.1 personal nonproduction historical backtesting, §4.2 no live use. Verify current applicable restrictions before accessing files; stop if rights/eligibility or isolation are not met.

## Bounded execution

Use an authorized isolated LOCAL computer, never existing protected data directories or production environment. Do not transfer licensed archive bytes, rows, or full tables to ChatGPT/Gemini/Codex or public GitHub.

Fixed EXPOSED_DEV period: UTC 2022-09-15 through 2022-09-21 inclusive. September 2022 is already scored historical development in frozen strategy register, not new OOS. Do not read/enumerate Final Holdout, H39/H40/H41, Forward or reserved OOS; no never-seen-date requirement for this DEV-only pilot.

From official data.binance.vision USD-M BTCUSDT daily archive only, check physical file availability before access. Fetch at most 7 daily files per family: REQUIRED 1m klines; OPTIONAL 1m markPriceKlines and 5m metrics (OI), if exact official paths/objects exist. Verify corresponding published checksums where available. Maximum 21 ZIP and their individual checksum texts, <=100MiB compressed and <=300MiB expanded; respect source limits, safe ZIP extraction, HTTPS, no redirects to other domains, timeouts, no spending, no accounts/API keys, no exchange REST/WS. If official object path or checksum is not independently verifiable, record that family as unavailable rather than guessing.

Perform local deterministic QC: schema, UTC window bounds, 1m and 5m grid gaps, duplicates, checksum and SHA256, fields (mark, sum_open_interest, taker ratio), OI vs 5m flow window semantics, correction and gaps. Treat archive timestamps as retrospective labels, NOT historical original first-receipt. Use an explicit conservative as-of lag for research; compare metric assumed lags of +5/+10/+15 minutes as methodological diagnostics, not selected by PnL. Record uncertain 2026 label-change issue as a separate provenance caveat, not a verified fault within 2022.

OPTIONAL after QC: exactly one already-frozen unchanged existing policy REPLAY SMOKE for parser/order/accounting checks ONLY, when dependencies and costs exist; no new strategy/parameter search, no selection/ranking, no Alpha claim. If funding, executable quotes, private ACK/fills or economic model are absent, mark costs INCOMPLETE and skip unsupported backtest.

## Single deliverable

Publish exactly ONE sanitized Markdown report on a new isolated docs branch rooted DIRECTLY at this dispatch commit:
docs/project/V06_R10_D0_2E_BINANCE_VISION_OFFLINE_DEV_QC_R1.md
Branch: docs/v06-r10-d0-2e-binance-vision-offline-dev-pilot-r1
No raw data, local private file paths, numeric row dumps, secrets or strategy returns in Git. Include source/checksum identities, sizes, day coverage, missing/duplicates, lag contract, source limits, optional smoke diagnostics, actual spend, failures, execution environment, and whether a later broader EXPOSED_DEV research authorization is recommended.

Choose one terminal: R10_D0_DEV_QC_PASS_WITH_LIMITS, R10_D0_DEV_PARTIAL_STOP, or R10_D0_RIGHTS_ENVIRONMENT_STOP. If authorized local execution is unavailable, STOP without fabricated results. Verify remote author commit, direct dispatch parent, blob, one-file diff and actual CI. No automatic successor assignment.

Preserve: SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / G2_ALPHA_NO_GO / TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE. No trading, protected samples, production data or code branch changes.
