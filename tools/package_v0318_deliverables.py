from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write(path: Path, value: str) -> None:
    path.write_text(value.strip() + "\n", encoding="utf-8")


def package(root: Path, artifact: Path) -> None:
    output = root / "deliverables/v0.3.18"
    output.mkdir(parents=True, exist_ok=True)
    archive = _read(artifact / "binance_official_archive_audit.json")
    provenance = _read(artifact / "historical_data_provenance_audit.json")
    search = _read(artifact / "symbolic_search_audit.json")
    forward = _read(artifact / "forward_campaigns_status.json")
    manifest = _read(artifact / "artifact_manifest.json")
    top = search["candidate_results"][0]
    start = forward["start"]["status"]
    end = forward["end"]["status"]
    numeric = {
        "version": "0.3.18",
        "run_id": artifact.name,
        "preregistration_sha": search["preregistration_sha"],
        "formal_implementation_sha": "51681874488216a25564d156e87c65c8afa04109",
        "protocol_sha256": search["protocol_sha256"],
        "artifact_manifest_sha256": _digest(artifact / "artifact_manifest.json"),
        "official_archive_probe": {
            "requests": len(archive["requests"]),
            "available": archive["available"],
            "missing_or_unreachable": archive["missing_or_unreachable"],
            "manifest_sha256": archive["manifest_sha256"],
            "aggtrade_sample_rows_each": 10_000,
            "sample_checksum_matches": all(
                item["official_sha256"] == item["local_sha256"]
                for item in archive["daily_aggtrade_schema_samples"]
            ),
        },
        "historical_dataset": provenance["feature_data_audit"],
        "search": {
            **search["search"]["accounting"],
            "validation_candidates": search["validation_candidates"],
            "top_k_frozen_before_pseudo_forward": search["top_k_frozen_before_pseudo_forward"],
            "pseudo_forward_touches": search["pseudo_forward_touches"],
            "multiple_testing": search["multiple_testing"],
        },
        "top_frozen_candidate": top,
        "candidate_exists": search["candidate_exists"],
        "provisional_shadow_started": search["provisional_shadow_started"],
        "primary_recommendation": search["recommendation"],
        "forward_start": start,
        "forward_end": end,
        "forward_store_historical_writes": forward["historical_writes_to_forward_stores"],
        "raw_data": manifest["raw_data"],
        "safety": manifest["safety"],
    }
    _write_json(output / "V0.3.18_NUMERIC_ANSWERS.json", numeric)
    shutil.copyfile(
        artifact / "historical_data_provenance_audit.json",
        output / "HISTORICAL_DATA_PROVENANCE_AUDIT.json",
    )
    shutil.copyfile(
        artifact / "binance_official_archive_audit.json",
        output / "BINANCE_OFFICIAL_ARCHIVE_AUDIT.json",
    )
    shutil.copyfile(
        artifact / "formula_registry_snapshot.json",
        output / "FORMULA_REGISTRY_SNAPSHOT.json",
    )
    _write_json(
        output / "SYMBOLIC_SEARCH_AUDIT.json",
        {
            "preregistration_sha": search["preregistration_sha"],
            "protocol_sha256": search["protocol_sha256"],
            "proposal_engine": search["proposal_engine"],
            "external_llm_api_used": search["external_llm_api_used"],
            "accounting": search["search"]["accounting"],
            "top_20_discovery": search["search"]["ranked"][:20],
            "validation_candidates": search["validation_candidates"],
            "top_k_frozen_before_pseudo_forward": search["top_k_frozen_before_pseudo_forward"],
            "frozen_formula_hashes": search["frozen_formula_hashes"],
            "pseudo_forward_touches": search["pseudo_forward_touches"],
            "multiple_testing": search["multiple_testing"],
            "candidate_results": search["candidate_results"],
            "candidate_exists": search["candidate_exists"],
            "provisional_shadow_started": search["provisional_shadow_started"],
            "recommendation": search["recommendation"],
            "full_audit_location": str(artifact / "symbolic_search_audit.json"),
            "full_audit_sha256": manifest["artifacts"]["symbolic_search_audit.json"],
        },
    )
    _write_json(output / "FORWARD_CAMPAIGNS_STATUS.json", forward)
    _write(
        output / "README.md",
        f"""
# BTC Quant Agent v0.3.18 Deliverables

本目录集中保存 v0.3.18 Historical Data Acceleration & Causal Symbolic Alpha Factory 的正式交付。

结论：已完成 Binance 官方档案真实路径/checksum/schema/timestamp 审计、严格来源角色、因果 Formula DSL、确定性 VM、512 个唯一公式的冻结 Random Grammar Search、独立 Validation、冻结 Top‑5 后的一次性 Development-internal pseudo-forward、多重检验与 research-only event replay。没有候选通过所有门槛，因此未创建 provisional candidate，也未启动 provisional real-time shadow。

主建议：`{search["recommendation"]}`。

文件：

- `V0.3.18_HISTORICAL_PROXY_SYMBOLIC_ALPHA_REPORT.md`
- `V0.3.18_NUMERIC_ANSWERS.json`
- `V0.3.18_RECOMMENDATION.md`
- `HISTORICAL_DATA_PROVENANCE_AUDIT.json`
- `BINANCE_OFFICIAL_ARCHIVE_AUDIT.json`
- `VENDOR_HISTORICAL_DATA_OPTIONS.md`
- `FORMULA_DSL_AND_VM_AUDIT.md`
- `FORMULA_REGISTRY_SNAPSHOT.json`
- `SYMBOLIC_SEARCH_AUDIT.json`
- `ALPHAGPT_REFERENCE_ADAPTATION.md`
- `FORWARD_CAMPAIGNS_STATUS.json`

大体积原始数据与完整运行 artifact 保持 Git 之外：`{artifact}`。Artifact manifest SHA-256：`{_digest(artifact / "artifact_manifest.json")}`。

Safety：Strategy `EXPERIMENTAL`；Qualified Direction Engine `NONE`；Normal Runtime maximum `OPPORTUNITY_ONLY`；Execution `DISABLED`；Final Holdout `SEALED`；Live trading `NOT AUTHORIZED`。
""",
    )
    _write(
        output / "V0.3.18_RECOMMENDATION.md",
        f"""
# v0.3.18 Recommendation

## Primary recommendation

`{search["recommendation"]}`

不得启动 provisional candidate forward shadow。512 个唯一公式的 best-score permutation 调整后 p 值为 `{search["multiple_testing"]["familywise_adjusted_p_value"]:.6f}`，未达到冻结的 0.05 标准。排名第一的冻结候选在 pseudo-forward 的净 8h 均值为 `{top["pseudo_forward"]["net_mean_return"]:.8f}`，block-bootstrap 95% CI 为 `[{top["pseudo_forward"]["bootstrap_ci_low"]:.8f}, {top["pseudo_forward"]["bootstrap_ci_high"]:.8f}]`，且 LONG fraction 为 `{top["pseudo_forward"]["long_fraction"]:.1f}`，不具备方向平衡性。

## Secondary engineering recommendation

Tier-1 官方历史路径应继续作为免费基线。若下一轮要引入真实历史 OI、liquidations 或可重建 incremental L2，可先获取 Tardis.dev 或 Amberdata 的限定样本并通过现有 vendor contract；付费数据只能标为 `VENDOR_RECORDED_HISTORICAL_PIT_PROXY`，不能保证产生 Alpha，也不能成为当前 Forward campaigns 的回填来源。

现有 H36、Derivatives v0.3.16 与 Microstructure v0.3.15 继续原链积累，不移动起点。
""",
    )
    _write(
        output / "FORMULA_DSL_AND_VM_AUDIT.md",
        """
# Formula DSL and VM Audit

## Implemented surface

实现了 typed postfix formula、canonical JSON、SHA-256 formula hash、静态 stack validation 和静态 total-lookback 计算。算子集覆盖 `ADD/SUB/MUL/DIV/NEG/ABS/SIGN/MIN/MAX/GATE/DELAY_1/DELAY_N/ROLL_SUM_N/ROLL_MEAN_N/ROLL_STD_N/ROLL_Z_N/EMA_N/DECAY_N/CLIP`。

VM 只使用当前及过去输入。rolling/EMA 在完整 startup lookback 前返回 unavailable；`DELAY_N` 使用前缀 `None`，无 wrap-around；不存在 full-series normalization；除零返回 unavailable；NaN/Inf 触发结构化 `NON_FINITE_OUTPUT`；缺失特征返回 `FEATURE_UNAVAILABLE`。未来行 mutation、ms/µs normalization、operator lookback、deterministic hash、duplicate rejection 和 structured failure 均有测试。

## Proposal and evaluation isolation

正式基线是固定 seed/budget 的 `RANDOM_GRAMMAR_SEARCH`。`FormulaProposalEngine` 接口已建立；tiny Transformer 仅保留架构 contract，标记 `LOCAL_FORMULA_POLICY_MODEL / NOT_LLM / NO_EXTERNAL_API / DISCOVERY_PROPOSAL_ONLY`，本轮未训练。Validation 不参与 proposal reward，pseudo-forward 只有冻结 Top-K 可访问。

## Runtime safety

所有 v0.3.18 registry 条目的 `runtime_eligibility=false`。`ExecutionGuard` 对 `PROVISIONAL*`、`NOT_FORWARD_VALIDATED` 与 `NOT_RUNTIME_ACTIONABLE` 明确拒绝。Event replay 只允许决策时间之后的 bar，WAIT 不成交，同 bar 同时触发 stop/target 时按 stop 保守处理。
""",
    )
    _write(
        output / "ALPHAGPT_REFERENCE_ADAPTATION.md",
        """
# AlphaGPT Reference Adaptation

参考项目：[imbue-bit/AlphaGPT](https://github.com/imbue-bit/AlphaGPT)。本实现采用 clean-room 方式，没有复制源代码。

保留的思想是“本地 token proposal → 确定性公式 VM → 外部量化 evaluator”。没有把 AlphaGPT 当作通用 LLM，也没有调用 OpenAI、Gemini、Claude 或其他外部模型 API。

明确拒绝的原实现风险包括：全序列 robust normalization、`torch.roll` 未来标签/环绕语义、best in-sample backtest wins、blanket exception swallowing，以及将 Validation/OOS 反馈给训练奖励。当前正式 baseline 先完成 Random Grammar Search；local tiny Transformer 仅有隔离接口，未进入正式结果。

审计依据包括 AlphaGPT 原始仓库及其 `times.py` 中的 token policy、StackVM、normalization 与 roll-based target 实现。访问日期：2026-09-02。
""",
    )
    _write(
        output / "VENDOR_HISTORICAL_DATA_OPTIONS.md",
        """
# Vendor Historical Data Options

本轮没有购买或导入付费供应商数据。以下均为潜在 `VENDOR_RECORDED_HISTORICAL_PIT_PROXY`，必须通过 exchange timestamp、receive timestamp、instrument mapping、sequence 与许可审计后才能使用。

| Provider | Potential BTCUSDT datasets | Timestamp / reconstruction value | Access / constraints | Assessment |
|---|---|---|---|---|
| Tardis.dev | trades, incremental L2, book snapshots, derivative ticker/OI/funding, liquidations | `timestamp` 与 `local_timestamp` 均为 µs；L2 含 snapshot/reset 语义 | 首月首日样本可用，完整历史通常需付费；不得擅自再分发 | 最适合先做限定样本的 L2/OI receive-time 审计 |
| Amberdata | Binance Futures order-book events/snapshots、funding、OI、liquidations、long/short | 覆盖表显示 Binance Futures 多类历史数据；精确字段仍需样本合同核验 | 商业访问与许可约束 | 适合机构级 OI/liquidation/L2 交叉评估 |
| Kaiko | backdated L2 bids/asks、trades | 提供 `tsExchange`、`tsCollection`、`tsEvent`；历史可通过 CSV/REST | 商业访问与再分发限制 | 适合 exchange-vs-collection timestamp 和 L2 质量审计 |
| CoinGlass | OI、funding、long/short、liquidation 聚合历史 | API 给出时间聚合序列；不是 tick-L2 ground truth | API key/套餐；聚合和 venue mapping 需核验 | 适合作为 derivatives sentiment/positioning proxy，不用于 L2 |

第一方资料：[Tardis data types](https://docs.tardis.dev/downloadable-csv-files/data-types)、[Amberdata CEX coverage](https://docs.amberdata.io/data-dictionary/coverage/exchange-coverage)、[Kaiko L2 bids and asks](https://docs.kaiko.com/cloud-delivery/data-feeds/level-2-tick-level/bids-and-asks)、[CoinGlass endpoint overview](https://docs.coinglass.com/reference/endpoint-overview)。访问日期：2026-09-02。

任何 vendor row 若试图标记为 `TRUE_FORWARD_LOCAL_PIT`，import contract 会拒绝。没有真实 incremental book 时，OFI、microprice、depth imbalance、queue dynamics 保持 `FORWARD_PIT_ONLY`，不会从 OHLCV 合成。
""",
    )
    report = f"""
# BTC Quant Agent v0.3.18 Historical Proxy & Symbolic Alpha Report

## Executive conclusion

v0.3.18 完成了历史数据加速和因果 symbolic alpha factory，但没有发现可进入 provisional real-time shadow 的候选。主建议为 `{search["recommendation"]}`。这不是“继续搜索直到盈利”的许可；下一轮如继续，必须新建并预注册独立、有限预算的假设或数据增量。

## Evidence classes

### Historical discovery result

正式 Random Grammar Search 使用 seed `{search["search"]["accounting"]["attempts"] and 3182026}`，固定 512 个 valid unique formulas。共尝试 `{search["search"]["accounting"]["attempts"]}` 次，拒绝 `{search["search"]["accounting"]["duplicates_rejected"]}` 个 canonical duplicates、`{search["search"]["accounting"]["over_lookback_rejected"]}` 个超 lookback 和 `{search["search"]["accounting"]["over_token_limit_rejected"]}` 个超 token 公式。Discovery 仅覆盖 `[2021-01-01, 2024-01-01)`，8h non-overlapping sampling，proposal/reward 未访问后续窗口。

Empirical best-score circular-block permutation 使用 200 次、168h block，observed best t-stat `{search["multiple_testing"]["observed_best_t_stat"]:.6f}`，null p95 `{search["multiple_testing"]["null_best_t_stat_p95"]:.6f}`，familywise adjusted p `{search["multiple_testing"]["familywise_adjusted_p_value"]:.6f}`，未通过。

### Historical validation result

Discovery Top-20 才能进入 `[2024-02-01, 2025-01-01)` Validation。排名第一的最终冻结候选 Validation 净 8h 均值 `{top["validation"]["net_mean_return"]:.8f}`，95% CI `[{top["validation"]["bootstrap_ci_low"]:.8f}, {top["validation"]["bootstrap_ci_high"]:.8f}]`；事件数 `{top["validation"]["event_count"]}`，低于冻结最小值 500，且 CI 跨零。

### Development-internal pseudo-forward result

Validation 排序完成后先把 5 个 formula hashes 写入 freeze artifact，然后每个仅访问一次 `[2025-02-01, 2026-02-01)`。Top 候选 pseudo-forward 净均值 `{top["pseudo_forward"]["net_mean_return"]:.8f}`，95% CI `[{top["pseudo_forward"]["bootstrap_ci_low"]:.8f}, {top["pseudo_forward"]["bootstrap_ci_high"]:.8f}]`；LONG/SHORT 为 `{top["pseudo_forward"]["long_count"]}/{top["pseudo_forward"]["short_count"]}`。5 个冻结候选全部失败，未生成 `PROVISIONAL_CANDIDATE.json`，未启动 shadow。

### Vendor-proxy result

没有 vendor credentials 或数据进入正式 run。已实现强制 receive timestamp 和 formal-role 的 vendor adapter contract，并审计 Tardis.dev、Amberdata、Kaiko、CoinGlass 的第一方说明。供应商路径是可选的下一步数据扩展，不是当前阻塞项，也不保证 Alpha。

### True Forward campaign status

历史研究写入 Forward stores 的记录数为 0。运行开始到结束：

- Derivatives v0.3.16 expected/full/partial/missing 从 `{start["derivatives_v0316"]["expected_scheduled_slots"]}/{start["derivatives_v0316"]["fully_available_scheduled_slots"]}/{start["derivatives_v0316"]["partial_slots"]}/{start["derivatives_v0316"]["missing_slots"]}` 变为 `{end["derivatives_v0316"]["expected_scheduled_slots"]}/{end["derivatives_v0316"]["fully_available_scheduled_slots"]}/{end["derivatives_v0316"]["partial_slots"]}/{end["derivatives_v0316"]["missing_slots"]}`；terminal=false，scheduler active。
- H36 expected slots 从 `{start["opportunity_h36"]["expected_slots"]}` 到 `{end["opportunity_h36"]["expected_slots"]}`，scan ratio 始终 `{end["opportunity_h36"]["successful_scan_ratio"]:.1f}`，missing=0，max streak=0，opportunity=0。
- Microstructure events trade/depth 从 `{start["microstructure_v0315"]["agg_trade_events"]}/{start["microstructure_v0315"]["depth_events"]}` 到 `{end["microstructure_v0315"]["agg_trade_events"]}/{end["microstructure_v0315"]["depth_events"]}`；rolling 24h depth/sequence/trade coverage 为 `{end["microstructure_v0315"]["rolling_reliability"]["24h"]["depth_coverage_ratio"]:.6f}/{end["microstructure_v0315"]["rolling_reliability"]["24h"]["sequence_valid_coverage_ratio"]:.6f}/{end["microstructure_v0315"]["rolling_reliability"]["24h"]["trade_coverage_ratio"]:.6f}`，partition integrity OK。
- start/end operations health 均为 `{forward["end"]["health"]["state"]}`，exit code 0。

## Official Binance historical audit

对 Spot/perp aggTrades、Spot/perp 1m klines、mark/index/premium 1m klines 和 settled funding 在 2021-01、2024-01、2025-01 共发出 24 个真实 `.CHECKSUM` 请求，24/24 可用。另下载并校验 2024-01-01 Spot 与 USD-M aggTrades；每份解析前 10,000 行，duplicate/out-of-order/invalid 均为 0，官方与本地 SHA-256 一致。

Spot 自 2025-01-01 起的 µs timestamp 规则按 [Binance public-data README](https://github.com/binance/binance-public-data/blob/master/README.md) 独立处理；raw timestamp 保留，normalized milliseconds 为派生字段。现有 canonical 1m 特征构建覆盖 44,568 小时；perp 完整 44,568，Spot 完整 44,547、缺失 21，不填补、不插值、不生成 synthetic rows。Final Holdout rows loaded=0。

## Architecture and safety

DSL/VM、registry、proposal interface、evaluation firewall、provisional signal 与 event-driven replay 均已落地。正式运行不使用外部 LLM API；Tiny Transformer 未训练。Runtime execution guard 对 provisional/non-runtime signals 明确拒绝。

Strategy=`EXPERIMENTAL`; Qualified Direction Engine=`NONE`; Normal Runtime maximum=`OPPORTUNITY_ONLY`; Execution=`DISABLED`; Final Holdout=`SEALED`; Live trading=`NOT AUTHORIZED`。

## Reproducibility

- Preregistration SHA: `{search["preregistration_sha"]}`
- Formal implementation SHA: `51681874488216a25564d156e87c65c8afa04109`
- Protocol SHA-256: `{search["protocol_sha256"]}`
- Artifact directory: `{artifact}`
- Perp manifest SHA-256: `{provenance["perp_manifest_sha256"]}`
- Spot manifest SHA-256: `{provenance["spot_manifest_sha256"]}`
- Official sample raw hashes: `{json.dumps(manifest["raw_data"], sort_keys=True)}`
"""
    _write(output / "V0.3.18_HISTORICAL_PROXY_SYMBOLIC_ALPHA_REPORT.md", report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    package(args.root.resolve(), args.artifact.resolve())


if __name__ == "__main__":
    main()
