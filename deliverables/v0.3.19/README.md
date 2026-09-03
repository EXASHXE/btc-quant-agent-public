# BTC Quant Agent v0.3.19 Deliverables

本目录集中保存 v0.3.19 Official Derivatives Feature Expansion & Candidate Gate Hardening 的正式交付。

主结论：`STOP_OFFICIAL_DERIVATIVES_SYMBOLIC_FAMILY`。366/366 个 Binance 官方月度归档通过 checksum 校验，形成 44,568 个小时和 8 个冻结新特征；512 个新特征约束公式完成全预算评估。经验式家族检验调整后 p 值为 `0.4328358209`，未通过 0.05，5 个冻结候选也均未通过全部公式门槛。因此没有 provisional candidate、没有候选 shadow、没有事件沙盒交易，Runtime 与执行权限均未变化。

文件：

- `V0.3.19_OFFICIAL_DERIVATIVES_SYMBOLIC_REPORT.md`
- `V0.3.19_NUMERIC_ANSWERS.json`
- `V0.3.19_RECOMMENDATION.md`
- `CANDIDATE_GATE_CORRECTNESS_AUDIT.md`
- `OFFICIAL_DERIVATIVES_DATA_AUDIT.json`
- `NEW_FEATURE_FAMILY_AUDIT.json`
- `SYMBOLIC_SEARCH_AUDIT.json`
- `FORMULA_REGISTRY_UPDATE.json`
- `FORWARD_CAMPAIGNS_STATUS.json`

完整大体积运行证据保留于 Git 之外：`artifacts/research/v0.3.19_official_derivatives_symbolic_20260903T013312Z/`。Artifact manifest SHA-256：`e06695f6ebcab55acb5f7d83e1d4c23fbbc0c05c63b5c16124e4d2bbae4c64e2`。

安全状态：Strategy `EXPERIMENTAL`；Qualified Direction Engine `NONE`；Runtime maximum `OPPORTUNITY_ONLY`；Execution `DISABLED`；`auto_execute=false`；Final Holdout `SEALED`；Live trading `NOT AUTHORIZED`。
