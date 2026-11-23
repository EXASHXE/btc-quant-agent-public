"""Model-free deterministic renderers for QUANT V1 SignalSnapshots and Feishu chat replies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .contract import (
    EVIDENCE_SYNTHETIC,
    EVIDENCE_UNKNOWN,
    HETEROGENEOUS_BANNER,
    SYNTHETIC_BANNER,
    UNKNOWN_EVIDENCE_BANNER,
)

HKT = timezone(timedelta(hours=8), "HKT")


def format_utc_hkt(ms: int | None) -> str:
    if ms is None:
        return "UNKNOWN (null)"
    dt = datetime.fromtimestamp(ms / 1000, tz=HKT)
    return f"{dt.isoformat(timespec='seconds')} (ms={ms})"


def _evidence_header(source_evidence_class: str, banner: str | None = None) -> str:
    if source_evidence_class == EVIDENCE_SYNTHETIC:
        return f"[警告] {banner or SYNTHETIC_BANNER} (合成测试卡，非真实交易信号)"
    if source_evidence_class == EVIDENCE_UNKNOWN:
        return f"[提示] {banner or UNKNOWN_EVIDENCE_BANNER} (未认证或异构集合，禁止作为真实/统一确认推送)"
    return f"[{source_evidence_class}] 仅市场侧信息 (非交易指令)"


def render_signal_alert(
    snapshot: dict[str, Any],
    *,
    duplicate_risk_note: str | None = None,
) -> str:
    """Render a deterministic, model-free immediate market alert / detail card."""
    lines: list[str] = [
        _evidence_header(snapshot["source_evidence_class"], snapshot.get("source_banner")),
        f"标的: {snapshot['symbol']} | 方向: {snapshot['direction']} | 策略族: {snapshot['strategy_family']}",
        f"核心状态 (market_status): {snapshot['market_status']}",
        f"原始原因码 (reasons): {', '.join(snapshot['status_reason_codes']) if snapshot['status_reason_codes'] else 'NONE'}",
        f"Episode ID: {snapshot['episode_id'] or 'NONE'}",
        f"Card ID: {snapshot['card_id']}",
        f"Card Version: {snapshot['card_version']}",
        f"数据源时间 (source_as_of): {format_utc_hkt(snapshot['source_as_of_ms'])}",
        f"核心评估时间 (evaluated_at): {format_utc_hkt(snapshot['evaluated_at_ms'])}",
        f"新鲜度 (freshness_state): {snapshot['freshness_state']}",
        (
            f"绝对过期时间 (absolute_expiry): {format_utc_hkt(snapshot['absolute_expiry_ms'])}"
            if snapshot["absolute_expiry_ms"] is not None
            else f"绝对过期时间 (absolute_expiry): null ({snapshot['expiry_status']})"
        ),
        (
            f"账户上下文: {snapshot['account_context_status']} / {snapshot['account_overlay']} | "
            f"敞口上限: {snapshot['portfolio_exposure_limits']} | 安全仓位: {snapshot['safe_position_size']}"
        ),
    ]

    plan = snapshot.get("plan")
    if isinstance(plan, dict):
        lines.append(
            f"计划入场区: {plan.get('entry_low', 'UNKNOWN')} - {plan.get('entry_high', 'UNKNOWN')} USDT | "
            f"硬止损 (Hard SL): {plan.get('hard_stop', 'UNKNOWN')} USDT"
        )
        if plan.get("no_chase_boundary") is not None:
            lines.append(f"不追价边界 (no_chase_boundary): {plan['no_chase_boundary']} USDT")
        targets = plan.get("targets") or []
        for t in targets:
            if t.get("price") is not None:
                net_r = t.get("net_r")
                if net_r is not None:
                    r_preview = f"{Decimal(str(net_r)):.3f}"
                    lines.append(
                        f"  {t['label']}: {t['price']} USDT | 净盈亏比 net R = {net_r} (~{r_preview}R)"
                    )
                else:
                    lines.append(f"  {t['label']}: {t['price']} USDT")
            else:
                lines.append(f"  {t['label']}: {t.get('status', 'UNESTABLISHED')} ({t.get('reason')})")
        if plan.get("first_obstacle_after_cost_r") is not None:
            lines.append(f"第一障碍物扣费净 R: {plan['first_obstacle_after_cost_r']}")
        if plan.get("unit_stop_loss_usdt") is not None:
            lines.append(
                f"单位止损风险: {plan['unit_stop_loss_usdt']} USDT | "
                f"费率(单边): {plan.get('fee_rate_each_side', 'UNKNOWN')} | "
                f"滑点(单边bps): {plan.get('slippage_bps_each_side', 'UNKNOWN')} | "
                f"价差: {plan.get('spread_usdt', 'UNKNOWN')} USDT"
            )
        funding = plan.get("funding")
        if isinstance(funding, dict):
            lines.append(
                f"资金费率参考: rate={funding.get('indicated_rate', 'UNKNOWN')} | "
                f"预计跨越次数={funding.get('modeled_crossings', 'UNKNOWN')}"
            )

    latest_reprice = snapshot.get("latest_reprice")
    if isinstance(latest_reprice, dict) and isinstance(latest_reprice.get("reprice"), dict):
        rp = latest_reprice["reprice"]
        lines.append(
            f"最近复价 (+{rp.get('requested_delay_minutes')}m): "
            f"observed={format_utc_hkt(rp.get('observed_venue_ms'))}, lateness={rp.get('lateness_ms')}ms"
        )

    if snapshot.get("human_action"):
        lines.append(f"提示操作: {snapshot['human_action']}")
    if duplicate_risk_note:
        lines.append(f"[投递状态说明] {duplicate_risk_note}")
    return "\n".join(lines)


def render_suppressed_notice(
    snapshot: dict[str, Any],
    *,
    suppression_reason: str,
    latest_snapshot: dict[str, Any] | None = None,
) -> str:
    """Render a non-affirmative suppression notice when a card became stale/expired/superseded/invalid."""
    current = latest_snapshot or snapshot
    return "\n".join([
        _evidence_header(current["source_evidence_class"], current.get("source_banner")),
        f"[已抑制旧通知 / SUPPRESSED] 原因: {suppression_reason}",
        f"标的: {current['symbol']} | Episode: {current['episode_id'] or 'NONE'}",
        f"当前最新状态 (market_status): {current['market_status']} | 原因码: {', '.join(current['status_reason_codes'])}",
        f"当前 Card ID: {current['card_id']} | Version: {current['card_version']}",
        f"新鲜度: {current['freshness_state']} | 过期状态: {current['expiry_status']}",
        f"账户上下文: {current['account_context_status']} / {current['account_overlay']}",
        "本消息不包含入场建议，请以最新核心状态与原因码为准。",
    ])


def render_active_signals_list(list_data: dict[str, Any]) -> str:
    signals = list_data.get("signals") or []
    ev_cls = str(list_data.get("source_evidence_class") or EVIDENCE_UNKNOWN)
    lines = [
        _evidence_header(ev_cls, list_data.get("source_banner")),
        f"当前已验证未过期信号列表 (as_of={format_utc_hkt(list_data.get('as_of_ms'))}, 账户={list_data.get('account_context_status')}):",
    ]
    if list_data.get("heterogeneous_evidence"):
        lines.append(f"[警告] {HETEROGENEOUS_BANNER}")
    if not signals:
        lines.append("当前无未过期的 EXECUTABLE / WATCH 信号。")
        return "\n".join(lines)
    for idx, s in enumerate(signals, start=1):
        ep_short = str(s.get("episode_id") or "")[:12]
        ps = s.get("plan_summary") or {}
        plan_txt = (
            f"入场 {ps.get('entry_low')}-{ps.get('entry_high')} / SL {ps.get('hard_stop')}"
            if ps
            else "无完整计划"
        )
        lines.append(
            f"{idx}. [{s.get('source_evidence_class')}] {s['symbol']} {s['direction']} [{s['strategy_family']}] "
            f"状态={s['market_status']} 原因={','.join(s.get('status_reason_codes') or [])} "
            f"新鲜度={s['freshness_state']} ep={ep_short}... ({plan_txt})"
        )
    return "\n".join(lines)


def render_reprice_result(reprice_data: dict[str, Any]) -> str:
    snap = reprice_data.get("snapshot")
    status = reprice_data.get("status")
    ev_cls = str(
        reprice_data.get("source_evidence_class")
        or (snap or {}).get("source_evidence_class")
        or EVIDENCE_UNKNOWN
    )
    lines = [_evidence_header(ev_cls, reprice_data.get("source_banner"))]
    if status != "AVAILABLE" or not reprice_data.get("latest_reprice"):
        lines.append(
            f"Episode {reprice_data.get('episode_id')}: 当前无已落盘 +5/+10 复价记录 (NOT_AVAILABLE)。"
            "只读查询不会触发新的行情采集。"
        )
        if snap:
            lines.append(f"当前最新核心状态: {snap['market_status']} ({', '.join(snap['status_reason_codes'])})")
        return "\n".join(lines)
    rp_wrap = reprice_data["latest_reprice"]
    rp = rp_wrap.get("reprice") or {}
    lines.append(
        f"已记录只读复价回执 (+{rp.get('requested_delay_minutes')}m): "
        f"event_id={rp_wrap.get('reprice_event_id')} | seq={rp_wrap.get('reprice_seq')}"
    )
    lines.append(
        f"计划复价时间: {format_utc_hkt(rp.get('scheduled_venue_ms'))} | "
        f"实际观测: {format_utc_hkt(rp.get('observed_venue_ms'))} | 延迟={rp.get('lateness_ms')}ms"
    )
    if snap:
        lines.append(render_signal_alert(snap))
    return "\n".join(lines)


def render_history_list(history_data: dict[str, Any]) -> str:
    items = history_data.get("history") or []
    ev_cls = str(history_data.get("source_evidence_class") or EVIDENCE_UNKNOWN)
    lines = [
        _evidence_header(ev_cls, history_data.get("source_banner")),
        f"不可变信号日志历史 (共 {history_data.get('total_matching', len(items))} 条, 本页 {len(items)} 条, 账户={history_data.get('account_context_status')}):",
    ]
    for item in items:
        rp_tag = (
            f" [复价+{item['reprice']['requested_delay_minutes']}m]"
            if isinstance(item.get("reprice"), dict)
            else ""
        )
        diag_tag = " [诊断/无Episode]" if item.get("diagnostic_only") or item.get("episode_id") is None else ""
        lines.append(
            f"- seq={item['pub_seq']} [{item.get('source_evidence_class')}] {item['symbol']} {item['direction']} "
            f"状态={item['market_status']}{diag_tag}{rp_tag} 原因={','.join(item.get('status_reason_codes') or [])} "
            f"时间={format_utc_hkt(item['evaluated_at_ms'])} card={item['card_id'][:10]}"
        )
    return "\n".join(lines)


def render_strategy_summary(summary_data: dict[str, Any]) -> str:
    ev_cls = str(summary_data.get("source_evidence_class") or EVIDENCE_UNKNOWN)
    lines = [
        _evidence_header(ev_cls, summary_data.get("source_banner")),
        f"策略定义: {summary_data.get('strategy_id')} (特征: {summary_data.get('features_id')}, 周期: {','.join(summary_data.get('timeframes') or [])})",
    ]
    for fam, desc in (summary_data.get("family_definitions") or {}).items():
        lines.append(f"- {fam}: {desc}")
    counts = summary_data.get("recorded_counts") or {}
    lines.append(
        f"已记录统计: 卡片={counts.get('cards', 0)}, Episodes={counts.get('episodes', 0)}, "
        f"诊断卡={counts.get('diagnostic_cards', 0)}, 复价卡={counts.get('reprice_cards', 0)}, "
        f"状态分布={counts.get('by_market_status', {})}"
    )
    lines.append(
        f"盈利性声明: profitability_claim={summary_data.get('profitability_claim')} "
        f"({summary_data.get('economic_validation_status')})"
    )
    lines.append(f"说明: {summary_data.get('disclaimer')}")
    lines.append(f"账户上下文: {summary_data.get('account_context_status')}")
    return "\n".join(lines)
