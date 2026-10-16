# BTC Quant Research — v0.6.5

Personal, noncommercial BTCUSDT **4–24 hour** strategy research. Current priority: establish usable BTC/ETH source data, causal clocks and realistic costs, then test a genuinely new mechanism. **No independently validated after-cost Alpha; TESTNET/LIVE remain unauthorized.**

[Research dashboard](docs/project/V0.6_PROJECT_STATUS_AND_ROADMAP.md) · [Research operating contract](docs/project/V065_RESEARCH_FIRST_OPERATING_CONTRACT_R2.md) · [Role/chat entrypoints](docs/project/V0.6_NEW_CHAT_HANDOVER_INDEX.md) · [Scientific register](docs/project/V0.6_B_LINE_STRATEGY_VALIDATION_REGISTER.md)

## Source limitations that matter

- Binance D2 and OKX E2 are author deliveries pending independent source/PIT/QC review; checksums do not prove historical receiver-known timing or executable fills.
- R11-Q1 remains a negative consequential gate; Q2 permitted bounded pilots only. Capacity C2 is STOP_UNMEASURED_SOURCE, not a measured storage forecast.
- Exposed DEV samples are not fresh OOS. Historical FAIL/STOP/INCONCLUSIVE and method-only PASS_WITH_LIMITS remain unchanged. No automatic collectors, market downloads, private-account calls or strategy reruns are enabled by this branch.

## Existing offline research commands

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,research]'
quantctl --help

# Only with a separately authorized explicit, versioned job and output path:
quantctl research --job /explicit/path/job.json --output /explicit/path/results
quantctl backtest --job /explicit/path/job.json --output /explicit/path/results
quantctl replay --job /explicit/path/job.json --output /explicit/path/results
```

These commands use the existing formal research facade; this README does not authorize a new experiment or supply an admitted dataset. Jobs require the original protocol, dataset/engine/input and causal/economic evidence. There is no CSV-to-qualified-strategy fallback. Configuration remains `configs/default.toml`; execution defaults stay `disabled`, `auto_execute=false`, `allow_live=false`.

For a docs-only edit use diff/link integrity. For code/data changes use the affected test tier in the operating contract. Existing CI YAML and all tests are preserved; a docs-only green run is not full-test or scientific acceptance.

## Repository navigation

- `v0.6.5`: current research code, source/PIT/scientific status and five role contracts.
- [docs/engineering](https://github.com/EXASHXE/btc-quant-agent-public/tree/docs/engineering): engineering/CI/deployment/maintenance documentation; not scientific authority.
- [legacy/research-archive](https://github.com/EXASHXE/btc-quant-agent-public/tree/legacy/research-archive): original B-line commit ancestry, evidence index and restore ledger; historical instructions are not active tasks.
- [Repository status](docs/project/V065_INTEGRATION_STATUS_R1.md): actual default/pruning limitations. A-line/protected controls remain separately owned.

Necessary existing compatibility docs remain where code/tests/deployment references require them; see [architecture](docs/CURRENT_ARCHITECTURE.md), [registry policy](docs/RESEARCH_REGISTRY.md) and [source clock specification](docs/DERIVATIVES_FORWARD_COLLECTION.md). Protected H39/H40/H41/Forward/Final/OOS data is outside this task. `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
