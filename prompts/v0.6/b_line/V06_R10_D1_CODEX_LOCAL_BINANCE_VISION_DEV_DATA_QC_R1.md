# R10-D1 — Codex Local Binance Vision EXPOSED_DEV Data Acquisition and Quality Evidence R1

**Executor:** Local Codex Agent, prefer highest available Codex reasoning (e.g. GPT-6.1 Sol High if actually selectable). Gemini BOOST local is an acceptable alternative, **not a second concurrent author**. Do not use ChatGPT-2-E for this work. No custom child agents. **Class M2, quality/reproducibility sensitive**.

**Mode:** ONE bounded, genuinely executed OFFLINE personal noncommercial NONPRODUCTION historical research dataset pilot. No live trading, no new Alpha, no hypothesis generation/parameter optimization, no protected OOS and no finance/account access. **No second data source**. Budget spend $0, no paid accounts/trials.

## Frozen identity before any work

- Follow immutable R10-D1 dispatch SHA and exact prompt/blob once received from Controller; verify direct parent was author R10-D0 `980a4b6f79de5ad6dbff8d8b674ce3ca2d056c4b`, whose report `docs/project/V06_R10_D0_2E_BINANCE_VISION_OFFLINE_DEV_QC_R1.md` Git blob is `14b993d63195b7970a4b1326ffe03b67212a0a47`.
- R10-D0 terminal `R10_D0_RIGHTS_ENVIRONMENT_STOP` means **ZERO actual downloads/QC/tests**, not negative source evidence. Preserve report immutable; no retry by 2-E.
- Owner-confirmed use: ONLY personal NONCOMMERCIAL NONPRODUCTION research and historical backtesting from archives; no present production feed. Binance Vision Dataset Terms v1.0, dated 2026-08-26, frozen publisher commit `f446ce3812bd4e5521f21faecd4ae3c6460e49fc`, `TERMS_AND_CONDITIONS.md` blob `87d04e216f62c86a2c797fbb7637404d6d602687` expressly describes this use in §4.1, with the §4.2 live execution limitation and all other restrictions unchanged. Check current official terms for relevant newer prohibitions or local access restrictions before downloading. Do not fabricate legal clearance or assume future LIVE rights.
- Data family/lineage metadata from R10-M0 `53e0becd3ba47e383b92d399d0b0f92989e23ada`, blob `b19c01d5103f84642a3af55b544034b9b96fb3d7`. R10-L4 exposed DEV clarification `285149095fc0d9a47ab86248d42fb609555a767d`, blob `8dfa7c93d2d6ad393df587c8eac7a7948afa14b0`.

## First action: confirm isolated local execution authority

**The owner must explicitly choose this task's working directory through the local Agent's own project/workspace selection UI or an exact path in the instruction.** Check only the chosen current workspace and exact allowlisted output subdirectory; do not scan home drives or guess previous paths. If no explicit workspace was selected, **STOP with `LOCAL_WORKSPACE_AUTHORITY_PENDING`**, and provide the minimal one-sentence request for one path. The mere presence of a connected online device is not authorization. Never touch local `Quant-agent/data`, `Quant-agent-sanitized`, private accounts, Final Holdout, H39/H40/H41/Forward, reserved OOS or unrelated repos. Prefer new `r10_d1_dev_data/` within the explicitly selected clean sandbox, and separate `report/` containing sanitized metadata only. Verify no path escapes/symlinks into forbidden directories. Disk availability, git cleanliness, safe write permissions, isolation, permissions and cap budgets must be checked before creating files. No need to enumerate protected holdout masks because the exact date range is already documented as an EXPOSED_DEV research slice.

The agent may implement tiny standalone repeatable tooling **only inside the selected sandbox**: download/QC tool, synthetic fixtures and tests. Pin external deps/versions and provide a minimal reproduction command. If no local shell, disk budget, HTTPS, isolated workspace or rights preconditions, STOP truthfully before fetch. Do not claim downloaded data based on public documentation.

## Fixed scope and strict source budget

Provider: `https://data.binance.vision` **ONLY**, instrument `BTCUSDT` Binance USDⓈ-M (`futures/um`), UTC dates **2022-09-15 through 2022-09-21** inclusive (7 DEV dates, previously exposed in 2021–2023 R2 research). File families:
1. REQUIRED `data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM-DD.zip` (at most 7).
2. OPTIONAL, only if official exact object exists: `data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM-DD.zip` (at most 7).
3. OPTIONAL, only after exact family/path and checksum confirmed: `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip` (at most 7). Never invent `openInterest/` or a `fundingRate/` ZIP if missing.

For each ZIP, verify publisher's paired `.CHECKSUM` before trusting content; if absent, grade `UNVERIFIED` and follow fail-closed result. Allow at most **21 ZIP + 21 checksums**, **100 MiB total compressed**, **300 MiB total expanded**. No unbounded retry: at most 2 retries per object, no redirects outside allowlisted origin, HTTP and ZIP safety checks (path traversal, zip-bomb ratio, UTF-8/CSV shape). No Bybit, HF, Coinalyze, Tardis, Binance market REST/WS, account, exchange key, purchase or trial. Do not perform broad internet search, unrestricted recursive filesystem listing or raw data upload.

## Required local evidence and acceptance tests

- Original file URI identity, fetched-at vs historical event time, bytes/SHA256 and verified publisher checksum algorithm, file schema/column types, instrument/units, exact UTC bounds, row completeness and duplicates. Record missing dates, 1m/5m grid holes, schema drift, any timestamp/duplicate ambiguity. **No raw data or row excerpts in LLM tool output** or remotely shared conversation; local scripts should print aggregate stats only.
- For 5m metrics classify OI **stock** snapshots vs taker-ratio **interval flow**, and distinguish official exchange `create_time`, true observation window close, official publication and first-known receiver. 2026-06-25 time-label-change issue #491 is reporter allegation and this fixed 2022 slice predates it. Never assume an as-of value existed at its labelled start; predeclare three strictly causal source timing proxies **end of period +5m/+10m/+15m** for qualitative robustness, NOT choose one from favorable PnL. A historical ZIP checksum is NOT original exchange receiver-first-known or durable ACK. Always preserve `PIT_UNKNOWN` absent such proof.
- Mandatory reproducible negative tests using local SYNTHETIC fixtures only: wrong publisher checksum, truncated ZIP, path traversal filename, duplicate 1m bar, missing 5m interval, misaligned stock-vs-flow metrics time, shifted start-vs-end label, and refusal to process source data beyond budget/date/host limits. Ensure tests really run. Do not change protected repo code or CI to greenwash unrelated H41 lint.
- Optional existing exact frozen baseline smoke **ONLY** if available data includes ALL contract-required inputs and accounting assumptions, with NO feature selection, threshold grid, profitability/return ranking or evaluation promotion. Otherwise explicitly `SMOKE_SKIPPED_INPUT_INCOMPLETE`. Source QC is successful even when strategy smoke is skipped.
- Clearly separate proven **archive integrity + developmental usability** from unknown **historical receiver PIT / bid-ask size and latency / funding account membership / hypothetical maker ACK/fill / after-cost Alpha**.

## Publication and independent review

Single local Agent author and one isolated git branch. Resolve actual valid source code base by verifying local clean repo and pinned public Git refs; **do not silently merge divergent docs/code branches**. Branch `feature/v06-r10-d1-local-binance-vision-dev-qc-r1` from frozen exact R10-D1 Controller dispatch commit if its code tree is suitable, otherwise report a reproducible base mismatch STOP before modifying shared files. Permitted tracked changes are ONLY a standalone R10-D1 local QC script + synthetic test code under `scripts/research/r10_d1/`, `tests/research/r10_d1/` and one sanitized Markdown execution report under `docs/project/V06_R10_D1_CODEX_LOCAL_BINANCE_VISION_DEV_QC_R1.md`; never include raw ZIP/CSV/Parquet, sample rows, protected data, credentials, private local machine paths or proprietary derivatives. Ignore local raw data, temp, cache and checksum copy files at their outside-repo workspace path. No force push, merge or protected branch edits.

Choose one terminal:
- `R10_D1_LOCAL_DEV_QC_PASS_WITH_LIMITS` — actual official objects downloaded in isolated environment, checksum and required 1m QC passed, negative tests passed; optional unsupported families honestly missing; no source/Alpha promotion.
- `R10_D1_LOCAL_DEV_QC_PARTIAL_STOP` — bounded genuine execution shows missing source file, label/gap or incomplete optional metric field; preserve actual bounded evidence.
- `R10_D1_LOCAL_AUTHORITY_RIGHTS_OR_INTEGRITY_STOP` — missing explicit local workspace or applicable rights, file identity, checksum, memory/size, or safety precondition.

Return the exact task commit, direct parent, author commit, changed path list, official checksum verification counts, byte caps, synthetic test command/passed-failed, CI actual status, scope deviations, recorded provenance and finite next scientific decision. Codex/Gemini authorship is NOT independent audit. After real execution, request ChatGPT-1 independent consequential audit before Controller can authorize any broader data use.

**Always preserve:** `R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE / SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. No trade, live/testnet account operation, source admission or default Alpha scoring from this QC.
