# Formula DSL and VM Audit

## Implemented surface

实现了 typed postfix formula、canonical JSON、SHA-256 formula hash、静态 stack validation 和静态 total-lookback 计算。算子集覆盖 `ADD/SUB/MUL/DIV/NEG/ABS/SIGN/MIN/MAX/GATE/DELAY_1/DELAY_N/ROLL_SUM_N/ROLL_MEAN_N/ROLL_STD_N/ROLL_Z_N/EMA_N/DECAY_N/CLIP`。

VM 只使用当前及过去输入。rolling/EMA 在完整 startup lookback 前返回 unavailable；`DELAY_N` 使用前缀 `None`，无 wrap-around；不存在 full-series normalization；除零返回 unavailable；NaN/Inf 触发结构化 `NON_FINITE_OUTPUT`；缺失特征返回 `FEATURE_UNAVAILABLE`。未来行 mutation、ms/µs normalization、operator lookback、deterministic hash、duplicate rejection 和 structured failure 均有测试。

## Proposal and evaluation isolation

正式基线是固定 seed/budget 的 `RANDOM_GRAMMAR_SEARCH`。`FormulaProposalEngine` 接口已建立；tiny Transformer 仅保留架构 contract，标记 `LOCAL_FORMULA_POLICY_MODEL / NOT_LLM / NO_EXTERNAL_API / DISCOVERY_PROPOSAL_ONLY`，本轮未训练。Validation 不参与 proposal reward，pseudo-forward 只有冻结 Top-K 可访问。

## Runtime safety

所有 v0.3.18 registry 条目的 `runtime_eligibility=false`。`ExecutionGuard` 对 `PROVISIONAL*`、`NOT_FORWARD_VALIDATED` 与 `NOT_RUNTIME_ACTIONABLE` 明确拒绝。Event replay 只允许决策时间之后的 bar，WAIT 不成交，同 bar 同时触发 stop/target 时按 stop 保守处理。
