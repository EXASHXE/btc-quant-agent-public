# BTC Quant Agent v0.3.16 Deliverables

本目录是 v0.3.16 的唯一正式交付目录。大型 SQLite、WAL 与 raw L2 数据未纳入 Git；这里仅保存可审计结论、数值状态、protocol/config provenance 与建议。

## 结论

- 旧 `DERIVATIVES_PIT_EPOCH_V0314_001` 已于 2026-08-31 13:45 UTC 的第 5 个连续失败槽位完成时进入不可恢复终态。
- 18 个连续失败槽位均由 systemd 正常触发，六个 Binance derivatives endpoints 的最终错误均为 HTTP 451；证据最符合代理/出口路径的地区限制，不是 scheduler 漏跑。
- 修复后的自然 scheduled collector 已长时间恢复；新的正式 successor 为 `DERIVATIVES_PIT_EPOCH_V0316_002`，固定从 2026-09-01 09:30 UTC 开始。
- Opportunity 的 28 个 miss 中 22 个为网络、5 个为 market-data insufficient、1 个为 runtime contract；H35 标记为 `H35_DATA_QUALITY_AT_RISK`。
- 微观结构链现在使用 heartbeat/lease、覆盖率完整性、分类型 gap、clock offset 诊断与不可变 finalized partition。
- Direction Candidate 为 `NONE`；Execution 为 `DISABLED`；Final Holdout 为 `SEALED`。

## 文件索引

- `V0.3.16_FORWARD_EVIDENCE_RECOVERY_REPORT.md`：完整工程与实机验收报告。
- `V0.3.16_NUMERIC_ANSWERS.json`：机器可读关键数值。
- `V0.3.16_RECOMMENDATION.md`：受限 recommendation。
- `DERIVATIVES_V0314_TERMINAL_EPOCH_AUDIT.json`：旧 epoch 终态审计。
- `DERIVATIVES_FAILURE_ROOT_CAUSE_AUDIT.json`：18 槽位故障根因与 chronology。
- `DERIVATIVES_SUCCESSOR_EPOCH_STATUS.json`：successor 冻结与生命周期。
- `OPPORTUNITY_MISSED_SLOT_AUDIT.json`：28 个 miss 分类。
- `MICROSTRUCTURE_SESSION_COVERAGE_AUDIT.json`：heartbeat/lease 与 completeness。
- `MICROSTRUCTURE_CLOCK_AUDIT.json`：clock offset 与 latency 语义。
- `MICROSTRUCTURE_PARTITION_INTEGRITY_AUDIT.json`：finalized partition 审计。
- `FORWARD_EVIDENCE_COMBINED_STATUS.json`：三条隔离 evidence 链的统一状态。

## Provenance

- protocol/lifecycle freeze: `72d0f32aa365e369af29c7748e640c2ed6911251`
- implementation base: `d91985d1121792d80d68b0cf0649890da4f2669e`
- formal implementation (including real fast-restart lease fix): `af246d9deb10a2d8dd8f5b340e1b70788313521f`
- operative successor freeze: `e502790a29edd8c064b6352b00efbc785d9525b0`
