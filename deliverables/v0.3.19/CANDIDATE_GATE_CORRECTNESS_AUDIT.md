# Candidate Gate Correctness Audit

Gate 链路已统一为 `protocol -> CandidateGateConfig.from_dict -> evaluate_candidate_gates -> machine-readable results`。冻结的 28 个 key 对每个 Top-5 候选均恰好消费；重复、未知或未使用 key 会使正式运行失败。

`candidate_must_pass_all=true`。公式门槛覆盖 Discovery/Validation/pseudo-forward 事件数、方向平衡、成本后收益、bootstrap CI、时间折、familywise pass 和候选相关性。沙盒门槛覆盖最少交易、PF、MDD R、连败、正收益折、fee/slippage/funding、2x cost stress。

Top-5 失败 gate 数依次为 7、8、10、7、7。没有任何公式通过全部上游门槛，因此沙盒项严格标记为 `NOT_APPLICABLE`，原因固定为 `UPSTREAM_FORMULA_GATE_FAILED`。`sandbox_trade_results.json` 为空且不会被解释为通过。

关键修复与测试：

- 168 block hours / 8 sample hours 明确转换为 21 block events；v0.3.18 历史指标不重写。
- 未知 protocol gate 注入测试证明 fail closed。
- `net_r = gross_r - fees_r - slippage_r - funding_r`。
- decision object 只保存 planned reference，不保存未来 next-open。
- executed entry 为 decision 后第一个 eligible 1m open，风险分母使用 actual entry 到冻结 stop 的距离。
- gap-through-stop、同 bar stop/target 保守选择及 LONG/SHORT funding/cost 对称性均有直接测试。
- provisional status 的 runtime eligibility 为 false，执行 guard 拒绝 provisional signal。

覆盖率：evaluate 97%、gates 97%、registry 98%、sandbox 94%、search 91%、VM 88%。421 项测试全部通过。
