# Evidence & Code Reading Catalogue
**Remote-only navigation:** all links below are publicly viewable GitHub resources. Access to private local worktrees, runtime dashboards and large data roots is NOT assumed.

## Current governing product documentation (canonical docs/engineering)
- [Owner mission and scope](https://github.com/EXASHXE/btc-quant-agent-public/blob/docs/engineering/docs/project/V070_ADVISORY_MISSION_AND_SCOPE.md)
- [Current roadmap, to be challenged freely](https://github.com/EXASHXE/btc-quant-agent-public/blob/docs/engineering/docs/project/V070_ADVISORY_ROADMAP.md)
- [Roles and authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/docs/engineering/docs/roles/V070_ADVISORY_AGENT_ROLES.md)
- [Documentation source-of-truth policy](https://github.com/EXASHXE/btc-quant-agent-public/blob/docs/engineering/docs/project/V070_DOCUMENTATION_BRANCH_POLICY.md)
- [Dated engineering handoff](https://github.com/EXASHXE/btc-quant-agent-public/blob/docs/engineering/docs/project/V070_CURRENT_STATE_AND_HANDOFF.md)
- [Current Foundation task specification](https://github.com/EXASHXE/btc-quant-agent-public/blob/docs/engineering/docs/project/V070_ADVISORY_FOUNDATION_TASK.md)

## Full existing historical research reports (inherited on review branch)
- [V070 primary trial results & failure analysis](../../docs/project/V070_PRIMARY_RESULTS_AND_FAILURE_ANALYSIS_20261023.md)
- [Oct 23 V070 research status](../../docs/project/V070_PROJECT_STATUS_AND_RESEARCH_ROADMAP_20261023.md)
- [Astra prior candidate directions](../../docs/project/ASTRA_V070_POST_PRIMARY03_RESEARCH_DIRECTIONS_20261023.md)
- [v0.6.5 R8 Argon research results](../../docs/project/V065_R8_ARGON_RESEARCH_RESULTS_20261022.md)
- [v0.6.5 R6 data source / ML architecture](../../docs/project/V065_R6_NATIVE_DATA_RECOVERY_ML_AND_P3_READINESS_20261020.md)
- [R8-7 priority economics update](../../docs/project/V065_R8_7_X_ONLY_ECONOMICS_PRIORITY_UPDATE_20261021.md)
- [R7 exploratory admission constraints](../../docs/project/V065_R7_OWNER_EXPLORATORY_ADMISSION_AND_ALPHA_FIRST_20261021.md)

The inherited reports preserve their original dates, authorization definitions and (potentially superseded) historical recommendations; do not mistake old queues for the current Owner mission.

## Public implementation source links
- [Code tree at v0.7.0](https://github.com/EXASHXE/btc-quant-agent-public/tree/v0.7.0/src/btc_quant_agent)
- [Market scanning](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/market_watch/scanner.py)
- [Playbooks](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/market_watch/playbooks.py)
- [Entry quality and costs](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/market_watch/entry_quality.py)
- [Price structure and strategy](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/strategies.py)
- [Position supervisor](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/position_supervisor/supervisor.py)
- [Decision service](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/decision/service.py)
- [Economic accounting module](https://github.com/EXASHXE/btc-quant-agent-public/tree/v0.7.0/src/btc_quant_agent/economic)
- [Feishu notifications](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/notify/feishu.py)
- [Binance client](https://github.com/EXASHXE/btc-quant-agent-public/blob/v0.7.0/src/btc_quant_agent/data/binance.py)

## Local-only sources summarized, not accessible to Opus through GitHub
- `/root/workspace/project/quant-0.7.0/t2b-canonical-market-expiry-fix-01/T2B_FINAL_ENGINEERING_DECISION.md`
- `/root/workspace/project/quant-0.7.0/f0-forward-source-health-01/F0_FORWARD_SOURCE_HEALTH_DECISION.md`
- `/root/workspace/project/quant-0.7.0/f0a-forward-current-health-receipt-01/F0A_CURRENT_HEALTH_DECISION.md`
- `/root/workspace/project/quant-0.7.0/f0b-payload-free-health-publisher-01/F0B_FINAL_DECISION.md`
- `/root/workspace/project/quant-0.7.0/power-mde-and-modes-01/FINAL_POWER_DECISION.md`
- `/root/workspace/project/quant-0.7.0/diag-preflight-01/DIAG_FEASIBILITY_DECISION.md`
- `/root/workspace/project/quant-0.7.0/advisory-foundation-01/FOUNDATION_LIMITATIONS_AND_NEXT.md`

Only selected already-reported findings and outcomes are copied into [Engineering Snapshot](ENGINEERING_SNAPSHOT.md) and [Research Evidence](RESEARCH_EVIDENCE.md). No promise of full independent verification from inaccessible local raw files is made.

## Recommended use
First read mission and historical evidence. Inspect any source modules that materially affect a proposed architecture. Write your own hypothesis before reading another reviewer's conclusions. Then decide what the Owner should do, with transparent unknowns and alternative approaches.
