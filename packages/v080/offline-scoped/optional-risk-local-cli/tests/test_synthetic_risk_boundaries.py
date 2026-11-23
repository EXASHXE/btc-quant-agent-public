"""Tests for proposed synthetic account-risk boundaries, latches, and Core non-mutation."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from quant_personal_decision_b2.adapter import MarketSnapshotAdapter
from quant_personal_decision_b2.engine import Engine
from quant_personal_decision_b2.fixtures import AFTER_TRIGGER, INITIAL, PULLBACK, FabricatedMarket
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import DEFAULT_POLICY

from quant_optional_risk_cli.config import default_disabled_config, validate_config_mapping
from quant_optional_risk_cli.models import (
    CONFIG_SCHEMA_VERSION,
    POLICY_REFERENCE,
    OptionalRiskBoundaryError,
)
from quant_optional_risk_cli.overlay import LatchStore, evaluate_optional_account_overlay

EVIDENCE_OUT = Path(os.environ["OPT_RISK_EVIDENCE_OUT"])


def _make_config(
    *,
    enabled: bool = True,
    selected_risk: str = "0.02",
    explicit_above_default: bool = False,
    btc_lev: str = "10",
    sol_lev: str = "10",
    explicit_exceptional_lev: bool = False,
):
    return validate_config_mapping(
        {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "config_version": "1.0.0",
            "policy_reference": POLICY_REFERENCE,
            "review_status": "PROPOSED_NOT_PRODUCTION_POLICY",
            "source": (
                "SYNTHETIC_OPT_IN_QA_FIXTURE_ONLY" if enabled else "OWNER_LOCAL_DISABLED_DEFAULT"
            ),
            "layer2_private_user_data": "DISABLED",
            "layer3_trade_execution": "DISABLED",
            "account_risk": {
                "enabled": enabled,
                "per_trade_default": "0.02",
                "per_trade_max": "0.03",
                "selected_per_trade_risk": selected_risk,
                "explicit_above_default_risk_selected": explicit_above_default,
                "btc_eth_default_leverage": "10",
                "btc_eth_normal_band": ["10", "15"],
                "btc_eth_exceptional_max": "20",
                "sol_other_default_leverage": "10",
                "sol_other_max_leverage": "15",
                "selected_leverage_by_symbol": {
                    "BTCUSDT": btc_lev,
                    "ETHUSDT": "10",
                    "SOLUSDT": sol_lev,
                },
                "explicit_exceptional_leverage_selected": explicit_exceptional_lev,
                "daily_stop": "0.06",
                "daily_halt": "0.08",
            },
            "provisional_rules": {
                "day_boundary": {"convention": "00:00_UTC_TO_NEXT_00:00_UTC", "status": "PROPOSED"},
                "cashflow_adjustment": {"formula": "max(0,(E0-(Et-F))/E0)", "status": "PROPOSED"},
                "portfolio_exposure_aggregation": {
                    "rule": "OPEN_POSITIONS_INCREMENTAL_DOWNSIDE_PLUS_CANDIDATE_UNDER_6PCT_HEADROOM",
                    "status": "PROPOSED",
                },
            },
        },
        allow_enabled_opt_in=enabled,
    )


def _make_b2_cards(tmp_path: Path) -> tuple[Path, dict[str, dict[str, object]]]:
    feed = FabricatedMarket(tmp_path / "b1_fixture.sqlite", PULLBACK, "LONG")
    feed.scan(INITIAL)
    db_path = tmp_path / "decision.sqlite"
    journal = Journal(db_path, create=True, policy=DEFAULT_POLICY)
    engine = Engine(MarketSnapshotAdapter(feed.path, "fixture"), journal)
    watch_card = engine.evaluate("BTCUSDT")
    feed.scan(AFTER_TRIGGER)
    exec_card = engine.evaluate("BTCUSDT")
    sampled_inv = feed.scan(AFTER_TRIGGER + 5 * 60_000 + 1000, "invalid")
    inv_card = engine.evaluate(
        "BTCUSDT",
        scan=sampled_inv["scan_id"],
        as_of_ms=sampled_inv["decision_as_of_venue_ms"],
        reprice_minutes=5,
        episode_id=exec_card["episode_id"],
    )
    assert watch_card["market_status"] == "WATCH"
    assert exec_card["market_status"] == "EXECUTABLE"
    assert inv_card["market_status"] == "INVALID"
    return db_path, {"watch": watch_card, "exec": exec_card, "invalid": inv_card}


def _fixture(
    *,
    snap_ms: int,
    e0: str = "10000",
    et: str = "10000",
    flow: str = "0",
    realized: str = "0",
    unrealized: str = "0",
    fees: str = "0",
    funding: str = "0",
    avail_margin: str = "5000",
    margin_mode: str = "ISOLATED",
    positions_verified: bool = True,
    open_positions: list[dict[str, object]] | None = None,
    risk_day_id: str = "2025-01-01",
    offline_gap: bool = False,
) -> dict[str, object]:
    return {
        "fixture_evidence_class": "SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
        "risk_day_id": risk_day_id,
        "equity_currency": "USDT",
        "snapshot_ts_ms": snap_ms,
        "margin_mode": margin_mode,
        "opening_equity": e0,
        "current_equity": et,
        "external_net_cashflow": flow,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "booked_fees": fees,
        "booked_funding": funding,
        "available_margin": avail_margin,
        "positions_verified": positions_verified,
        "open_positions": [] if open_positions is None else open_positions,
        "fee_schedule": {"taker_fee_rate": "0.0005", "maker_fee_rate": "0.0002"},
        "offline_gap_unverified": offline_gap,
    }


def _normalized_exec_card(
    base_card: dict[str, object], *, symbol: str = "BTCUSDT"
) -> dict[str, object]:
    card = copy.deepcopy(base_card)
    card["symbol"] = symbol
    card["plan"]["entry_fill"] = "500"  # type: ignore[index]
    card["plan"]["expected_stop_stress_fill"] = "480"  # type: ignore[index]
    card["plan"]["unit_stop_loss_usdt"] = "20"  # type: ignore[index]
    card["plan"]["fee_rate_each_side"] = "0.0005"  # type: ignore[index]
    return card


def test_disabled_overlay_preserves_b2_bytes_and_frozen_v1_account(tmp_path: Path) -> None:
    db_path, cards = _make_b2_cards(tmp_path)
    db_sha_before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    cfg = default_disabled_config()

    for label in ("watch", "exec", "invalid"):
        card = cards[label]
        orig_json = json.dumps(card, sort_keys=True)
        res = evaluate_optional_account_overlay(card, cfg)
        assert json.dumps(card, sort_keys=True) == orig_json
        assert res["overlay_mode"] == "DISABLED"
        assert res["core_market_status"] == card["market_status"]
        assert res["core_market_status_unchanged"] is True
        assert res["core_frozen_account"]["account_overlay"] == "MANUAL_ACCOUNT_CHECK_REQUIRED"
        assert res["core_frozen_account"]["safe_position_size"] == "UNKNOWN"
        assert res["account_risk_eligibility"] == "UNAVAILABLE_OPTIONAL_OVERLAY_DISABLED"
        assert res["approved_real_position_size"] is None
        assert res["layer2_private_user_data"] == "DISABLED"
        assert res["layer3_trade_execution"] == "DISABLED"

    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == db_sha_before


def test_risk_caps_leverage_margin_separation_and_no_market_promotion(tmp_path: Path) -> None:
    _, cards = _make_b2_cards(tmp_path)
    exec_card = _normalized_exec_card(cards["exec"])
    as_of = int(exec_card["evaluated_ms"])
    fix = _fixture(snap_ms=as_of)

    cfg_2pct_10x = _make_config(enabled=True, selected_risk="0.02", btc_lev="10")
    res_10x = evaluate_optional_account_overlay(
        exec_card, cfg_2pct_10x, synthetic_fixture=fix, as_of_ms=as_of, candidate_qty="10"
    )
    assert res_10x["account_risk_eligibility"] == "SYNTHETIC_FIXTURE_ELIGIBLE_PROPOSED_ONLY"
    m10 = res_10x["modeled_metrics"]
    assert m10["modeled_cash_risk_usdt"] == "200"
    assert m10["modeled_equity_risk_fraction"] == "0.02"
    assert m10["modeled_notional_usdt"] == "5000"
    assert m10["illustrative_initial_margin_usdt"] == "500"
    assert res_10x["approved_real_position_size"] is None

    # Higher leverage reduces illustrative initial margin ONLY; equity cash risk remains 200 (2%).
    cfg_2pct_20x = _make_config(
        enabled=True, selected_risk="0.02", btc_lev="20", explicit_exceptional_lev=True
    )
    res_20x = evaluate_optional_account_overlay(
        exec_card, cfg_2pct_20x, synthetic_fixture=fix, as_of_ms=as_of, candidate_qty="10"
    )
    m20 = res_20x["modeled_metrics"]
    assert m20["modeled_cash_risk_usdt"] == "200"
    assert m20["modeled_equity_risk_fraction"] == "0.02"
    assert m20["illustrative_initial_margin_usdt"] == "250"

    # Reject candidate qty exceeding 2% under default 2% selection (q=10.1 -> 2.02%).
    res_over_2 = evaluate_optional_account_overlay(
        exec_card, cfg_2pct_10x, synthetic_fixture=fix, as_of_ms=as_of, candidate_qty="10.1"
    )
    assert res_over_2["account_risk_eligibility"] == "REJECTED_PER_TRADE_RISK_LIMIT"

    # Exact 3% cap allowed only when explicitly selected; above 3% rejected.
    cfg_3pct = _make_config(
        enabled=True, selected_risk="0.03", explicit_above_default=True, btc_lev="10"
    )
    res_3pct = evaluate_optional_account_overlay(
        exec_card, cfg_3pct, synthetic_fixture=fix, as_of_ms=as_of, candidate_qty="15"
    )
    assert res_3pct["account_risk_eligibility"] == "SYNTHETIC_FIXTURE_ELIGIBLE_PROPOSED_ONLY"
    assert res_3pct["modeled_metrics"]["modeled_equity_risk_fraction"] == "0.03"

    res_over_3 = evaluate_optional_account_overlay(
        exec_card, cfg_3pct, synthetic_fixture=fix, as_of_ms=as_of, candidate_qty="15.05"
    )
    assert res_over_3["account_risk_eligibility"] == "REJECTED_PER_TRADE_RISK_LIMIT"

    # SOLUSDT at 15x succeeds within proposal ceiling.
    sol_card = _normalized_exec_card(cards["exec"], symbol="SOLUSDT")
    cfg_sol_15 = _make_config(enabled=True, sol_lev="15")
    res_sol = evaluate_optional_account_overlay(
        sol_card, cfg_sol_15, synthetic_fixture=fix, as_of_ms=as_of, candidate_qty="10"
    )
    assert res_sol["account_risk_eligibility"] == "SYNTHETIC_FIXTURE_ELIGIBLE_PROPOSED_ONLY"
    assert res_sol["modeled_metrics"]["selected_leverage_x"] == "15"

    # Market WATCH / INVALID must NEVER be promoted by enabled risk config or healthy account.
    for non_exec in (cards["watch"], cards["invalid"]):
        r = evaluate_optional_account_overlay(
            non_exec, cfg_2pct_10x, synthetic_fixture=fix, as_of_ms=as_of
        )
        assert r["core_market_status"] == non_exec["market_status"]
        assert r["account_risk_eligibility"] == "CORE_NOT_EXECUTABLE_NO_SIZING"


def test_daily_loss_boundaries_latch_persistence_withdrawal_and_unverified_cases(
    tmp_path: Path,
) -> None:
    _, cards = _make_b2_cards(tmp_path)
    exec_card = _normalized_exec_card(cards["exec"])
    as_of = int(exec_card["evaluated_ms"])
    cfg = _make_config(enabled=True, selected_risk="0.02")

    # 1. Synthetic withdrawal E0=10000, F=-500, Et=9500 -> day loss MUST be 0 (not trading loss),
    # while post-withdrawal 2% cap on Et=9500 is 190 USDT (qty=9.5 passes; qty=10 exceeds 2% of 9500).
    fix_withdraw = _fixture(snap_ms=as_of, e0="10000", et="9500", flow="-500")
    res_w = evaluate_optional_account_overlay(
        exec_card, cfg, synthetic_fixture=fix_withdraw, as_of_ms=as_of, candidate_qty="9.5"
    )
    assert res_w["account_risk_eligibility"] == "SYNTHETIC_FIXTURE_ELIGIBLE_PROPOSED_ONLY"
    assert res_w["modeled_metrics"]["daily_loss_fraction"] == "0"
    assert res_w["modeled_metrics"]["daily_loss_cash"] == "0"
    assert res_w["modeled_metrics"]["modeled_equity_risk_fraction"] == "0.02"
    assert (
        evaluate_optional_account_overlay(
            exec_card, cfg, synthetic_fixture=fix_withdraw, as_of_ms=as_of, candidate_qty="10"
        )["account_risk_eligibility"]
        == "REJECTED_PER_TRADE_RISK_LIMIT"
    )

    # 2. 5.99% day loss: 1 USDT remaining headroom -> candidate needing 20 USDT is held.
    fix_599 = _fixture(snap_ms=as_of, e0="10000", et="9401", realized="-599")
    res_599 = evaluate_optional_account_overlay(
        exec_card, cfg, synthetic_fixture=fix_599, as_of_ms=as_of, candidate_qty="1"
    )
    assert res_599["modeled_metrics"]["daily_loss_fraction"] == "0.0599"
    assert res_599["account_risk_eligibility"] == "DAILY_HEADROOM_INSUFFICIENT"

    # 3. 6.00% day loss latches DAILY_STOP_6PCT; survives restart & missing evidence on same day.
    stop_db = tmp_path / "stop_latch.sqlite"
    fix_600 = _fixture(snap_ms=as_of, e0="10000", et="9400", realized="-600")
    res_600 = evaluate_optional_account_overlay(
        exec_card,
        cfg,
        synthetic_fixture=fix_600,
        latch_store=LatchStore(stop_db),
        as_of_ms=as_of,
    )
    assert res_600["account_risk_eligibility"] == "DAILY_STOP_SUPPRESSED"
    assert res_600["core_market_status"] == "EXECUTABLE"

    # Simulate restart + missing fixture -> restrictive 6% stop latch retained!
    res_stop_restart = evaluate_optional_account_overlay(
        exec_card, cfg, synthetic_fixture=None, latch_store=LatchStore(stop_db), as_of_ms=as_of
    )
    assert res_stop_restart["account_risk_eligibility"] == "DAILY_STOP_SUPPRESSED"

    # 4. 7.99% day loss remains DAILY_STOP_SUPPRESSED (not 8% halt).
    fix_799 = _fixture(snap_ms=as_of, e0="10000", et="9201", realized="-799")
    res_799 = evaluate_optional_account_overlay(
        exec_card, cfg, synthetic_fixture=fix_799, as_of_ms=as_of
    )
    assert res_799["account_risk_eligibility"] == "DAILY_STOP_SUPPRESSED"

    # 5. 8.00% day loss -> latched DAILY_HALT_8PCT persists across restart, next day, & missing data.
    halt_db = tmp_path / "halt_latch.sqlite"
    fix_800 = _fixture(snap_ms=as_of, e0="10000", et="9200", realized="-800")
    res_800 = evaluate_optional_account_overlay(
        exec_card,
        cfg,
        synthetic_fixture=fix_800,
        latch_store=LatchStore(halt_db),
        as_of_ms=as_of,
    )
    assert res_800["account_risk_eligibility"] == "ACCOUNT_HALTED_LATCHED"

    # Simulated machine restart + new risk day + rebounded equity STILL halted until Owner review!
    restarted_store = LatchStore(halt_db)
    next_day_fix = _fixture(
        snap_ms=as_of + 86_400_000, risk_day_id="2025-01-02", e0="9200", et="9500", realized="300"
    )
    res_after_restart = evaluate_optional_account_overlay(
        exec_card,
        cfg,
        synthetic_fixture=next_day_fix,
        latch_store=restarted_store,
        as_of_ms=as_of + 86_400_000,
    )
    assert res_after_restart["account_risk_eligibility"] == "ACCOUNT_HALTED_LATCHED"

    with pytest.raises(OptionalRiskBoundaryError, match="HALT_RESET_REQUIRES_SUBSEQUENT_RISK_DAY"):
        restarted_store.reset_halt_after_review(
            owner_review_id="rev-same-day",
            new_risk_day_id="2025-01-01",
            reconciled_note="cannot reset same day",
        )
    restarted_store.reset_halt_after_review(
        owner_review_id="rev-next-day-01",
        new_risk_day_id="2025-01-02",
        reconciled_note="owner reconciled synthetic ledger before next day",
    )
    res_post_review = evaluate_optional_account_overlay(
        exec_card,
        cfg,
        synthetic_fixture=next_day_fix,
        latch_store=LatchStore(halt_db),
        as_of_ms=as_of + 86_400_000,
        candidate_qty="5",
    )
    assert res_post_review["account_risk_eligibility"] == "SYNTHETIC_FIXTURE_ELIGIBLE_PROPOSED_ONLY"

    # 6. Missing equity/fees/holdings/margin_mode & inconsistent equity -> UNVERIFIED.
    missing_eq = _fixture(snap_ms=as_of)
    del missing_eq["opening_equity"]
    missing_fees = _fixture(snap_ms=as_of)
    del missing_fees["fee_schedule"]
    missing_hold = _fixture(snap_ms=as_of, positions_verified=False)
    cross_mode = _fixture(snap_ms=as_of, margin_mode="CROSS")
    inconsistent_eq = _fixture(snap_ms=as_of, e0="10000", et="9900", realized="0")
    stale_fix = _fixture(snap_ms=as_of - 200_000)

    for label, bad_fix in (
        ("missing_equity", missing_eq),
        ("missing_fees", missing_fees),
        ("unverified_holdings", missing_hold),
        ("cross_margin_mode", cross_mode),
        ("inconsistent_equity", inconsistent_eq),
        ("stale_fixture", stale_fix),
    ):
        u_res = evaluate_optional_account_overlay(
            exec_card, cfg, synthetic_fixture=bad_fix, as_of_ms=as_of
        )
        assert u_res["account_risk_eligibility"] == "UNVERIFIED", label
        assert u_res["core_market_status"] == "EXECUTABLE"

    EVIDENCE_OUT.mkdir(parents=True, exist_ok=True)
    res_baseline = evaluate_optional_account_overlay(
        exec_card,
        cfg,
        synthetic_fixture=_fixture(snap_ms=as_of),
        as_of_ms=as_of,
        candidate_qty="10",
    )
    (EVIDENCE_OUT / "qa-boundary-evidence.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "two_pct_10x_cash_risk": res_baseline["modeled_metrics"]["modeled_cash_risk_usdt"],
                "withdrawal_day_loss": res_w["modeled_metrics"]["daily_loss_fraction"],
                "stop_6pct_state": res_600["account_risk_eligibility"],
                "halt_8pct_restart_retained": res_after_restart["account_risk_eligibility"],
                "post_review_next_day_state": res_post_review["account_risk_eligibility"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
