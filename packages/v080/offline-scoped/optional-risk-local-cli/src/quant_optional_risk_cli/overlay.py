"""Optional account-risk overlay evaluation, proposed daily-loss rules, and durable latch store."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
from decimal import ROUND_DOWN, Decimal, localcontext
from pathlib import Path
from typing import Any

from .config import OptionalAccountRiskConfig
from .models import (
    APPROVED_SYMBOLS,
    DECIMAL_CTX,
    MAJOR_SYMBOLS,
    SHA256_HEX_RE,
    ZERO,
    D,
    OptionalRiskBoundaryError,
    canonical_encode,
    canonical_sha256,
    parse_strict_decimal_string,
    parse_strict_int,
    scan_forbidden_live_or_secret_fields,
)

LATCH_APP_ID = 0x514F524C
REQUIRED_FIXTURE_KEYS = frozenset(
    {
        "fixture_evidence_class",
        "risk_day_id",
        "equity_currency",
        "snapshot_ts_ms",
        "margin_mode",
        "opening_equity",
        "current_equity",
        "external_net_cashflow",
        "realized_pnl",
        "unrealized_pnl",
        "booked_fees",
        "booked_funding",
        "available_margin",
        "positions_verified",
        "open_positions",
        "fee_schedule",
        "offline_gap_unverified",
    }
)


def _dstr(val: Decimal | None) -> str | None:
    return None if val is None else format(val, "f")


class LatchStore:
    """Append-only local SQLite ledger for proposed 6% daily stop & 8% halt latches."""

    def __init__(self, path: Path) -> None:
        if path.is_symlink():
            raise OptionalRiskBoundaryError("LATCH_SYMLINK_FORBIDDEN", str(path))
        self.path = path.resolve()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        existed = self.path.exists()
        conn = self._connect(write=True)
        try:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if app_id == 0:
                if conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone():
                    raise OptionalRiskBoundaryError("LATCH_WRONG_SCHEMA")
                conn.execute(
                    """CREATE TABLE latch_events (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_kind TEXT NOT NULL,
                        risk_day_id TEXT NOT NULL,
                        loss_fraction TEXT,
                        payload TEXT NOT NULL,
                        prior_sha TEXT,
                        sha TEXT NOT NULL
                    )"""
                )
                for op in ("UPDATE", "DELETE"):
                    conn.execute(
                        f"CREATE TRIGGER lock_latch_{op} BEFORE {op} ON latch_events "
                        "BEGIN SELECT RAISE(ABORT,'LATCH_APPEND_ONLY'); END"
                    )
                conn.execute(f"PRAGMA application_id={LATCH_APP_ID}")
                conn.execute("PRAGMA user_version=1")
            elif app_id != LATCH_APP_ID or conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise OptionalRiskBoundaryError("LATCH_WRONG_SCHEMA")
            conn.commit()
        finally:
            conn.close()
        if not existed:
            os.chmod(self.path, 0o600)

    def _connect(self, *, write: bool = False) -> sqlite3.Connection:
        target = str(self.path) if write else self.path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(target, uri=not write, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        if write:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
        else:
            conn.execute("PRAGMA query_only=ON")
        return conn

    def events(self) -> list[dict[str, Any]]:
        conn = self._connect(write=False)
        try:
            prior: str | None = None
            out: list[dict[str, Any]] = []
            for row in conn.execute("SELECT * FROM latch_events ORDER BY seq ASC"):
                payload = json.loads(row["payload"])
                body = {
                    "event_kind": row["event_kind"],
                    "risk_day_id": row["risk_day_id"],
                    "loss_fraction": row["loss_fraction"],
                    "payload": payload,
                    "prior_sha": row["prior_sha"],
                }
                if row["prior_sha"] != prior or canonical_sha256(body) != row["sha"]:
                    raise OptionalRiskBoundaryError("LATCH_CHAIN_TAMPERED", f"seq={row['seq']}")
                prior = str(row["sha"])
                out.append({**body, "seq": row["seq"], "sha256": prior})
            return out
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OptionalRiskBoundaryError("LATCH_CHAIN_TAMPERED", str(exc)) from exc
        finally:
            conn.close()

    def _append(
        self,
        *,
        event_kind: str,
        risk_day_id: str,
        loss_fraction: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        conn = self._connect(write=True)
        try:
            conn.execute("BEGIN IMMEDIATE")
            prior_row = conn.execute(
                "SELECT sha FROM latch_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prior = str(prior_row["sha"]) if prior_row else None
            body = {
                "event_kind": event_kind,
                "risk_day_id": risk_day_id,
                "loss_fraction": loss_fraction,
                "payload": payload,
                "prior_sha": prior,
            }
            sha = canonical_sha256(body)
            conn.execute(
                "INSERT INTO latch_events (event_kind, risk_day_id, loss_fraction, payload, prior_sha, sha) "
                "VALUES (?,?,?,?,?,?)",
                (event_kind, risk_day_id, loss_fraction, canonical_encode(payload), prior, sha),
            )
            conn.commit()
            return {**body, "sha256": sha}
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_daily_stop(
        self, *, risk_day_id: str, loss_fraction: str, reason: str
    ) -> dict[str, Any]:
        active = self.active_restriction(risk_day_id=risk_day_id)
        if active and active["kind"] in ("DAILY_HALT_8PCT", "DAILY_STOP_6PCT"):
            return active
        return self._append(
            event_kind="DAILY_STOP_6PCT",
            risk_day_id=risk_day_id,
            loss_fraction=loss_fraction,
            payload={"reason": reason, "status": "PROPOSED_DAILY_STOP"},
        )

    def record_daily_halt(
        self, *, risk_day_id: str, loss_fraction: str, reason: str
    ) -> dict[str, Any]:
        active = self.active_restriction(risk_day_id=risk_day_id)
        if active and active["kind"] == "DAILY_HALT_8PCT":
            return active
        return self._append(
            event_kind="DAILY_HALT_8PCT",
            risk_day_id=risk_day_id,
            loss_fraction=loss_fraction,
            payload={
                "reason": reason,
                "requires_owner_review": True,
                "status": "PROPOSED_LATCHED_HALT",
            },
        )

    def reset_halt_after_review(
        self,
        *,
        owner_review_id: str,
        new_risk_day_id: str,
        reconciled_note: str,
    ) -> dict[str, Any]:
        if not owner_review_id or len(owner_review_id) > 120:
            raise OptionalRiskBoundaryError("INVALID_OWNER_REVIEW_ID")
        active = self.active_restriction(risk_day_id=new_risk_day_id)
        if not active or active["kind"] != "DAILY_HALT_8PCT":
            raise OptionalRiskBoundaryError("NO_ACTIVE_HALT_TO_RESET")
        if new_risk_day_id == active["risk_day_id"]:
            raise OptionalRiskBoundaryError("HALT_RESET_REQUIRES_SUBSEQUENT_RISK_DAY")
        return self._append(
            event_kind="OWNER_REVIEW_HALT_RESET",
            risk_day_id=new_risk_day_id,
            loss_fraction=None,
            payload={
                "owner_review_id": owner_review_id,
                "cleared_halt_sha256": active["sha256"],
                "note": reconciled_note,
            },
        )

    def active_restriction(self, *, risk_day_id: str | None = None) -> dict[str, Any] | None:
        halt_event: dict[str, Any] | None = None
        stop_event: dict[str, Any] | None = None
        for ev in self.events():
            kind = ev["event_kind"]
            if kind == "DAILY_HALT_8PCT":
                halt_event = ev
            elif kind == "OWNER_REVIEW_HALT_RESET" and halt_event is not None:
                if ev["payload"].get("cleared_halt_sha256") == halt_event["sha256"]:
                    halt_event = None
            elif kind == "DAILY_STOP_6PCT":
                if stop_event is None or ev["risk_day_id"] >= stop_event["risk_day_id"]:
                    stop_event = ev

        if halt_event is not None:
            return {
                "kind": "DAILY_HALT_8PCT",
                "risk_day_id": halt_event["risk_day_id"],
                "loss_fraction": halt_event["loss_fraction"],
                "sha256": halt_event["sha256"],
                "requires_owner_review": True,
            }
        if stop_event is not None and (
            risk_day_id is None or risk_day_id <= stop_event["risk_day_id"]
        ):
            return {
                "kind": "DAILY_STOP_6PCT",
                "risk_day_id": stop_event["risk_day_id"],
                "loss_fraction": stop_event["loss_fraction"],
                "sha256": stop_event["sha256"],
                "requires_owner_review": False,
            }
        return None


def _base_result(
    card: dict[str, Any],
    config: OptionalAccountRiskConfig,
    *,
    overlay_mode: str,
    account_risk_eligibility: str,
    reasons: list[str],
    fixture_evidence_class: str | None = None,
    latch_state: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "overlay_mode": overlay_mode,
        "policy_status": "PROPOSED_NOT_ACTIVE_PRODUCTION_POLICY",
        "config_schema_version": config.schema_version,
        "config_version": config.config_version,
        "config_sha256": config.config_sha256,
        "config_review_status": config.review_status,
        "config_source": config.source,
        "core_card_id": card["card_id"],
        "core_symbol": card["symbol"],
        "core_market_status": card["market_status"],
        "core_market_status_unchanged": True,
        "core_frozen_account": {
            "account_context_status": card.get("account_context_status", "UNAVAILABLE"),
            "account_overlay": card.get("account_overlay", "MANUAL_ACCOUNT_CHECK_REQUIRED"),
            "safe_position_size": card.get("safe_position_size", "UNKNOWN"),
        },
        "account_risk_eligibility": account_risk_eligibility,
        "fixture_evidence_class": fixture_evidence_class,
        "approved_real_position_size": None,
        "real_safe_position_size": "UNKNOWN",
        "layer2_private_user_data": "DISABLED",
        "layer3_trade_execution": "DISABLED",
        "latch_state": latch_state,
        "modeled_metrics": metrics,
        "reasons": reasons,
        "provisional_rules": config.provisional_rules.to_dict(),
    }


def _parse_synthetic_fixture(
    fixture: dict[str, Any],
    *,
    as_of_ms: int | None,
    max_fixture_age_ms: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Strictly parse synthetic account fixture; return (parsed_values, unverified_reasons)."""
    scan_forbidden_live_or_secret_fields(fixture)
    if fixture.get("fixture_evidence_class") != "SYNTHETIC_ACCOUNT_FIXTURE_ONLY":
        raise OptionalRiskBoundaryError(
            "SYNTHETIC_FIXTURE_REQUIRED",
            f"fixture_evidence_class={fixture.get('fixture_evidence_class')}",
        )

    reasons: list[str] = []
    missing = sorted(REQUIRED_FIXTURE_KEYS - set(fixture.keys()))
    if missing:
        reasons.extend([f"MISSING_{k.upper()}" for k in missing])
        return None, reasons

    if fixture["margin_mode"] != "ISOLATED":
        reasons.append(f"UNSUPPORTED_OR_MISSING_MARGIN_MODE:{fixture['margin_mode']}")
        return None, reasons

    if fixture["positions_verified"] is not True or not isinstance(fixture["open_positions"], list):
        reasons.append("OPEN_POSITIONS_UNVERIFIED")
        return None, reasons

    if fixture["offline_gap_unverified"] is not False:
        reasons.append("OFFLINE_GAP_PNL_UNVERIFIED")
        return None, reasons

    snap_ms = parse_strict_int(
        fixture["snapshot_ts_ms"], "snapshot_ts_ms", minimum=1, err_cls=OptionalRiskBoundaryError
    )
    if as_of_ms is not None and (as_of_ms - snap_ms > max_fixture_age_ms or as_of_ms < snap_ms):
        reasons.append("STALE_OR_FUTURE_ACCOUNT_FIXTURE")
        return None, reasons

    fee_sched = fixture["fee_schedule"]
    if not isinstance(fee_sched, dict) or "taker_fee_rate" not in fee_sched:
        reasons.append("MISSING_FEE_SCHEDULE")
        return None, reasons

    e0 = parse_strict_decimal_string(
        fixture["opening_equity"],
        "opening_equity",
        positive=True,
        err_cls=OptionalRiskBoundaryError,
    )
    et = parse_strict_decimal_string(
        fixture["current_equity"],
        "current_equity",
        positive=True,
        err_cls=OptionalRiskBoundaryError,
    )
    flow = parse_strict_decimal_string(
        fixture["external_net_cashflow"], "external_net_cashflow", err_cls=OptionalRiskBoundaryError
    )
    realized = parse_strict_decimal_string(
        fixture["realized_pnl"], "realized_pnl", err_cls=OptionalRiskBoundaryError
    )
    unrealized = parse_strict_decimal_string(
        fixture["unrealized_pnl"], "unrealized_pnl", err_cls=OptionalRiskBoundaryError
    )
    booked_fees = parse_strict_decimal_string(
        fixture["booked_fees"], "booked_fees", non_negative=True, err_cls=OptionalRiskBoundaryError
    )
    booked_funding = parse_strict_decimal_string(
        fixture["booked_funding"], "booked_funding", err_cls=OptionalRiskBoundaryError
    )
    avail_margin = parse_strict_decimal_string(
        fixture["available_margin"],
        "available_margin",
        non_negative=True,
        err_cls=OptionalRiskBoundaryError,
    )
    taker_fee = parse_strict_decimal_string(
        fee_sched["taker_fee_rate"],
        "fee_schedule.taker_fee_rate",
        non_negative=True,
        err_cls=OptionalRiskBoundaryError,
    )

    with localcontext(DECIMAL_CTX):
        expected_et = e0 + flow + realized + unrealized - booked_fees + booked_funding
        if expected_et != et:
            reasons.append("EQUITY_CONSISTENCY_MISMATCH")
            return None, reasons

    open_downside = ZERO
    for idx, pos in enumerate(fixture["open_positions"]):
        if not isinstance(pos, dict) or pos.get("symbol") not in APPROVED_SYMBOLS:
            reasons.append(f"OPEN_POSITION_INVALID_{idx}")
            return None, reasons
        if pos.get("stop_covered") is not True or "incremental_downside_usdt" not in pos:
            reasons.append(f"OPEN_POSITION_UNPROTECTED_OR_DOWNSIDE_MISSING_{idx}")
            return None, reasons
        open_downside += parse_strict_decimal_string(
            pos["incremental_downside_usdt"],
            f"open_positions[{idx}].incremental_downside_usdt",
            non_negative=True,
            err_cls=OptionalRiskBoundaryError,
        )

    risk_day = str(fixture["risk_day_id"])
    if not risk_day:
        reasons.append("MISSING_RISK_DAY_ID")
        return None, reasons

    return {
        "risk_day_id": risk_day,
        "equity_currency": str(fixture["equity_currency"]),
        "e0": e0,
        "et": et,
        "flow": flow,
        "booked_fees": booked_fees,
        "booked_funding": booked_funding,
        "available_margin": avail_margin,
        "taker_fee": taker_fee,
        "open_downside": open_downside,
    }, []


def evaluate_optional_account_overlay(
    card: dict[str, Any],
    config: OptionalAccountRiskConfig,
    *,
    synthetic_fixture: dict[str, Any] | None = None,
    latch_store: LatchStore | None = None,
    as_of_ms: int | None = None,
    max_fixture_age_ms: int = 120_000,
    candidate_qty: str | None = None,
) -> dict[str, Any]:
    """Evaluate optional account-risk overlay strictly offline without modifying the Core card."""
    snapshot_card = copy.deepcopy(card)
    before_sha = canonical_sha256(snapshot_card)

    if not config.account_risk.enabled:
        out = _base_result(
            snapshot_card,
            config,
            overlay_mode="DISABLED",
            account_risk_eligibility="UNAVAILABLE_OPTIONAL_OVERLAY_DISABLED",
            reasons=["OPTIONAL_ACCOUNT_RISK_DISABLED", "MANUAL_ACCOUNT_CHECK_REQUIRED"],
        )
        assert canonical_sha256(snapshot_card) == before_sha
        return out

    prior_latch: dict[str, Any] | None = None
    if latch_store is not None:
        try:
            prior_latch = latch_store.active_restriction(risk_day_id=None)
        except OptionalRiskBoundaryError as exc:
            return _base_result(
                snapshot_card,
                config,
                overlay_mode="SYNTHETIC_OPT_IN_UNVERIFIED",
                account_risk_eligibility="UNVERIFIED",
                reasons=[exc.code],
            )

    if prior_latch is not None and prior_latch["kind"] == "DAILY_HALT_8PCT":
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_LATCHED_HALT",
            account_risk_eligibility="ACCOUNT_HALTED_LATCHED",
            reasons=["LATCHED_8PCT_HALT_REQUIRES_OWNER_REVIEW"],
            fixture_evidence_class=(
                str(synthetic_fixture.get("fixture_evidence_class"))
                if isinstance(synthetic_fixture, dict)
                else None
            ),
            latch_state=prior_latch,
        )

    if synthetic_fixture is None:
        if prior_latch is not None:
            return _base_result(
                snapshot_card,
                config,
                overlay_mode="SYNTHETIC_OPT_IN_LATCHED_STOP",
                account_risk_eligibility="DAILY_STOP_SUPPRESSED",
                reasons=["PRIOR_6PCT_STOP_RETAINED_WITH_MISSING_FIXTURE"],
                latch_state=prior_latch,
            )
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_UNVERIFIED",
            account_risk_eligibility="UNVERIFIED",
            reasons=["NO_SYNTHETIC_ACCOUNT_FIXTURE_PROVIDED"],
        )

    try:
        parsed, unverified_reasons = _parse_synthetic_fixture(
            synthetic_fixture, as_of_ms=as_of_ms, max_fixture_age_ms=max_fixture_age_ms
        )
    except OptionalRiskBoundaryError as exc:
        if prior_latch is not None:
            return _base_result(
                snapshot_card,
                config,
                overlay_mode="SYNTHETIC_OPT_IN_LATCHED_STOP",
                account_risk_eligibility="DAILY_STOP_SUPPRESSED",
                reasons=["PRIOR_RESTRICTIVE_LATCH_RETAINED", exc.code],
                latch_state=prior_latch,
            )
        raise

    if parsed is None:
        if prior_latch is not None:
            return _base_result(
                snapshot_card,
                config,
                overlay_mode="SYNTHETIC_OPT_IN_LATCHED_STOP",
                account_risk_eligibility="DAILY_STOP_SUPPRESSED",
                reasons=["PRIOR_RESTRICTIVE_LATCH_RETAINED", *unverified_reasons],
                fixture_evidence_class=str(synthetic_fixture.get("fixture_evidence_class")),
                latch_state=prior_latch,
            )
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_UNVERIFIED",
            account_risk_eligibility="UNVERIFIED",
            reasons=unverified_reasons,
            fixture_evidence_class=str(synthetic_fixture.get("fixture_evidence_class")),
        )

    with localcontext(DECIMAL_CTX):
        adjusted_equity = parsed["et"] - parsed["flow"]
        daily_loss_cash = max(ZERO, parsed["e0"] - adjusted_equity)
        daily_loss_fraction = daily_loss_cash / parsed["e0"]

    risk_cfg = config.account_risk
    base_metrics = {
        "risk_day_id": parsed["risk_day_id"],
        "opening_equity": _dstr(parsed["e0"]),
        "current_equity": _dstr(parsed["et"]),
        "external_net_cashflow": _dstr(parsed["flow"]),
        "cashflow_adjusted_equity": _dstr(adjusted_equity),
        "daily_loss_cash": _dstr(daily_loss_cash),
        "daily_loss_fraction": _dstr(daily_loss_fraction),
    }

    if daily_loss_fraction >= risk_cfg.daily_halt:
        new_halt = (
            latch_store.record_daily_halt(
                risk_day_id=parsed["risk_day_id"],
                loss_fraction=format(daily_loss_fraction, "f"),
                reason="SYNTHETIC_DAILY_LOSS_REACHED_8PCT",
            )
            if latch_store is not None
            else {"kind": "DAILY_HALT_8PCT", "risk_day_id": parsed["risk_day_id"]}
        )
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_LATCHED_HALT",
            account_risk_eligibility="ACCOUNT_HALTED_LATCHED",
            reasons=["PROPOSED_8PCT_DAILY_HALT_LATCHED"],
            fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
            latch_state=new_halt,
            metrics=base_metrics,
        )

    same_day_latch = (
        latch_store.active_restriction(risk_day_id=parsed["risk_day_id"])
        if latch_store is not None
        else None
    )
    if daily_loss_fraction >= risk_cfg.daily_stop or (
        same_day_latch is not None and same_day_latch["kind"] == "DAILY_STOP_6PCT"
    ):
        new_stop = (
            latch_store.record_daily_stop(
                risk_day_id=parsed["risk_day_id"],
                loss_fraction=format(daily_loss_fraction, "f"),
                reason="SYNTHETIC_DAILY_LOSS_REACHED_6PCT",
            )
            if latch_store is not None
            else {"kind": "DAILY_STOP_6PCT", "risk_day_id": parsed["risk_day_id"]}
        )
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_LATCHED_STOP",
            account_risk_eligibility="DAILY_STOP_SUPPRESSED",
            reasons=["PROPOSED_6PCT_DAILY_STOP_ACTIVE"],
            fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
            latch_state=new_stop,
            metrics=base_metrics,
        )

    if snapshot_card["market_status"] != "EXECUTABLE":
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_ACTIVE",
            account_risk_eligibility="CORE_NOT_EXECUTABLE_NO_SIZING",
            reasons=[f"CORE_MARKET_STATUS_{snapshot_card['market_status']}"],
            fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
            metrics=base_metrics,
        )

    plan = snapshot_card.get("plan")
    if (
        not isinstance(plan, dict)
        or plan.get("unit_stop_loss_usdt") is None
        or plan.get("entry_fill") is None
    ):
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_UNVERIFIED",
            account_risk_eligibility="UNVERIFIED",
            reasons=["CORE_EXECUTABLE_PLAN_OR_UNIT_LOSS_MISSING"],
            fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
            metrics=base_metrics,
        )

    symbol = str(snapshot_card["symbol"])
    leverage = risk_cfg.leverage_for(symbol)
    entry_fill = D(str(plan["entry_fill"]))
    stop_fill = D(str(plan["expected_stop_stress_fill"]))
    unit_loss = D(str(plan["unit_stop_loss_usdt"]))
    core_fee = D(str(plan.get("fee_rate_each_side", "0")))
    if parsed["taker_fee"] > core_fee:
        with localcontext(DECIMAL_CTX):
            unit_loss += (entry_fill + stop_fill) * (parsed["taker_fee"] - core_fee)

    with localcontext(DECIMAL_CTX):
        equity_loss_budget = parsed["et"] * risk_cfg.selected_per_trade_risk
        daily_stop_limit_cash = parsed["e0"] * risk_cfg.daily_stop
        remaining_headroom_cash = daily_stop_limit_cash - daily_loss_cash - parsed["open_downside"]

        if candidate_qty is not None:
            qty = parse_strict_decimal_string(
                candidate_qty, "candidate_qty", positive=True, err_cls=OptionalRiskBoundaryError
            )
            qty_source = "EXPLICIT_CANDIDATE_QTY"
        else:
            qty = (equity_loss_budget / unit_loss).quantize(D("0.001"), rounding=ROUND_DOWN)
            qty_source = "MODELED_MAX_SYNTHETIC_QTY"

        modeled_cash_risk = qty * unit_loss
        modeled_risk_fraction = modeled_cash_risk / parsed["et"]
        notional = qty * entry_fill
        illustrative_initial_margin = notional / leverage

    detail_metrics = {
        **base_metrics,
        "symbol": symbol,
        "symbol_group": "BTC_ETH" if symbol in MAJOR_SYMBOLS else "SOL_OTHER",
        "selected_per_trade_risk_cap": _dstr(risk_cfg.selected_per_trade_risk),
        "selected_leverage_x": _dstr(leverage),
        "effective_unit_stop_loss_usdt": _dstr(unit_loss),
        "qty_source": qty_source,
        "modeled_candidate_qty": _dstr(qty),
        "modeled_cash_risk_usdt": _dstr(modeled_cash_risk),
        "modeled_equity_risk_fraction": _dstr(modeled_risk_fraction),
        "modeled_notional_usdt": _dstr(notional),
        "illustrative_initial_margin_usdt": _dstr(illustrative_initial_margin),
        "available_margin_usdt": _dstr(parsed["available_margin"]),
        "remaining_6pct_headroom_cash": _dstr(remaining_headroom_cash),
    }

    if modeled_risk_fraction > risk_cfg.selected_per_trade_risk:
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_REJECTED",
            account_risk_eligibility="REJECTED_PER_TRADE_RISK_LIMIT",
            reasons=["MODELED_RISK_EXCEEDS_SELECTED_PER_TRADE_CAP"],
            fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
            metrics=detail_metrics,
        )

    if remaining_headroom_cash <= ZERO or modeled_cash_risk >= remaining_headroom_cash:
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_HEADROOM_HOLD",
            account_risk_eligibility="DAILY_HEADROOM_INSUFFICIENT",
            reasons=["PROPOSED_6PCT_HEADROOM_REACHED_OR_EXCEEDED"],
            fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
            metrics=detail_metrics,
        )

    if illustrative_initial_margin > parsed["available_margin"]:
        return _base_result(
            snapshot_card,
            config,
            overlay_mode="SYNTHETIC_OPT_IN_MARGIN_HOLD",
            account_risk_eligibility="INSUFFICIENT_SYNTHETIC_ISOLATED_MARGIN",
            reasons=["ILLUSTRATIVE_INITIAL_MARGIN_EXCEEDS_AVAILABLE_MARGIN"],
            fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
            metrics=detail_metrics,
        )

    pub_sha_valid = SHA256_HEX_RE.fullmatch(
        str((snapshot_card.get("evaluation_receipt") or {}).get("source_publication_sha256", ""))
    )
    _ = pub_sha_valid
    assert canonical_sha256(snapshot_card) == before_sha
    return _base_result(
        snapshot_card,
        config,
        overlay_mode="SYNTHETIC_OPT_IN_MODELED_PASS",
        account_risk_eligibility="SYNTHETIC_FIXTURE_ELIGIBLE_PROPOSED_ONLY",
        reasons=["SYNTHETIC_FIXTURE_ONLY_NOT_APPROVED_REAL_TRADE"],
        fixture_evidence_class="SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
        metrics=detail_metrics,
    )
