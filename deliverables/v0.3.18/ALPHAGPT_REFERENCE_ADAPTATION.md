# AlphaGPT Reference Adaptation

参考项目：[imbue-bit/AlphaGPT](https://github.com/imbue-bit/AlphaGPT)。本实现采用 clean-room 方式，没有复制源代码。

保留的思想是“本地 token proposal → 确定性公式 VM → 外部量化 evaluator”。没有把 AlphaGPT 当作通用 LLM，也没有调用 OpenAI、Gemini、Claude 或其他外部模型 API。

明确拒绝的原实现风险包括：全序列 robust normalization、`torch.roll` 未来标签/环绕语义、best in-sample backtest wins、blanket exception swallowing，以及将 Validation/OOS 反馈给训练奖励。当前正式 baseline 先完成 Random Grammar Search；local tiny Transformer 仅有隔离接口，未进入正式结果。

审计依据包括 AlphaGPT 原始仓库及其 `times.py` 中的 token policy、StackVM、normalization 与 roll-based target 实现。访问日期：2026-09-02。
