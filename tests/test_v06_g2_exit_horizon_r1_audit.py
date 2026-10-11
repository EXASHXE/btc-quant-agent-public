"""Synthetic-only integration witnesses for independent Decimal source audit."""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.strategy_research.g2_exit_horizon_r1 import audit
from scripts.strategy_research.g2_exit_horizon_r1.account import mark_curve
from scripts.strategy_research.g2_exit_horizon_r1.book import position
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import MINUTE, STRESS, _proposed

CANDIDATES = (
    ("W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H", 2.0),
    ("W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H", 2.5),
)


def _archive(base: Path, name: str, member: str, text: str) -> str:
    base.mkdir(parents=True, exist_ok=True)
    path = base / name
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv(rows: list[list[object]], header: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


def _clocks():
    current = datetime(2021, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, tzinfo=UTC)
    while current < end:
        for hour in (0, 8, 16):
            yield int(current.replace(hour=hour).timestamp() * 1000)
        current += timedelta(days=1)


def synthetic_audit_bundle(tmp_path: Path, monkeypatch):
    """36 fake monthly Funding ZIPs, 2 Mark ZIPs, 8 typed partial episodes."""
    old = tmp_path / "r3-public-synthetic"
    scratch = tmp_path / "exit-synthetic-curves"
    old.mkdir()
    scratch.mkdir()
    monkeypatch.setattr(audit, "OLD", old)
    monkeypatch.setattr(audit, "SCRATCH", scratch)
    funding_by_month: dict[tuple[int, int], list[list[object]]] = {
        (year, month): [] for year in (2021, 2022, 2023) for month in range(1, 13)
    }
    funding_events: list[dict] = []
    for clock in _clocks():
        date = datetime.fromtimestamp(clock / 1000, UTC)
        # Signed fractions change direction. Eight selected 08:00 episodes are
        # deliberately near a TP1 at the preceding minute close.
        rate = "-0.00020" if date.day % 2 else "0.00030"
        funding_by_month[date.year, date.month].append([clock, rate])
        funding_events.append({"settlement_at": clock, "rate": rate})
    assert len(funding_events) == 3285
    refs = []
    for (year, month), rows in funding_by_month.items():
        stem = f"BTCUSDT-fundingRate-{year}-{month:02d}"
        sha = _archive(old, f"funding-{stem}.zip", stem + ".csv",
                       _csv(rows, ["calc_time", "last_funding_rate"]))
        refs.append({"kind": "funding", "year": year, "month": month, "zip_sha256": sha})

    marks_by_year: dict[int, list[list[object]]] = {2022: [], 2023: []}
    trades = []
    for year in (2022, 2023):
        for offset, (candidate_id, target_r) in enumerate(CANDIDATES):
            for side_idx, side in enumerate((1, -1)):
                day = 2 + 2 * offset + side_idx
                start = int(datetime(year, 1, day, tzinfo=UTC).timestamp() * 1000)
                n = 13 * 60 + 5
                last = np.empty((n, 5), dtype=float)
                last[:, 0] = start + np.arange(n) * MINUTE
                last[:, 1:] = 100.0
                mark = last.copy()
                event = {
                    "event_time": start, "decision_at": start + MINUTE,
                    "entry_at": start + 2 * MINUTE, "decision_close": 100.0,
                    "atr_hour": 20.0, "stop": 90.0 if side == 1 else 110.0,
                    "side": side, "event_id": f"synthetic-{year}-{candidate_id}-{side}",
                }
                candidate = {"id": candidate_id, "horizon_hours": 12,
                             "target_R": target_r, "cooldown_hours": 6}
                proposal = _proposed(last, event, candidate, STRESS)
                target1 = proposal["effective_entry"] + side * proposal["initial_risk"]
                # Floating tick safety: one extra tick beyond the 1R limit.
                if side == 1:
                    last[479, 2] = target1 + 0.2
                else:
                    last[479, 3] = target1 - 0.2
                trade = position(last, mark, funding_events, event, candidate, STRESS,
                                 "E1", 0.2)
                assert any(tier["reason"] == "TP1" for tier in trade["tiers"])
                assert trade["funding_settlements"]
                assert trade["funding_settlements"][0]["quantity"] == "0.1"
                assert abs(trade["tiers"][0]["exit_at"] - (start + 8 * 3600_000)) <= 60_000
                curve = mark_curve([trade], mark, start, start + n * MINUTE, 1000.0, STRESS)
                curve_path = scratch / f"curve-{year}-{offset}-{side_idx}.npz"
                np.savez_compressed(curve_path, curve=curve["curve"])
                trade.update({"cost": "STRESS", "cash_before_entry": 1000.0,
                              "curve_path": str(curve_path),
                              "curve_sha256": hashlib.sha256(curve_path.read_bytes()).hexdigest()})
                trades.append(trade)
                for row in mark:
                    tick = int(row[0])
                    marks_by_year[year].append([tick, 100.0, 100.0, 100.0, 100.0,
                                                0, tick + MINUTE - 1])
    for year, rows in marks_by_year.items():
        stem = f"BTCUSDT-1m-{year}-01"
        sha = _archive(old, f"mark-{stem}.zip", stem + ".csv",
                       _csv(rows, ["open_time", "open", "high", "low", "close",
                                   "volume", "close_time"]))
        refs.append({"kind": "mark", "year": year, "month": 1, "zip_sha256": sha})
    return trades, {"successful_sources": refs, "daily_receipts": []}


def test_eight_group_decimal_audit_and_settlement_boundary(tmp_path, monkeypatch):
    trades, source = synthetic_audit_bundle(tmp_path, monkeypatch)
    receipt = audit.independent_audit(trades, source)
    assert receipt["status"] == "PASS"
    assert receipt["n"] == 8
    assert receipt["per_cost_n"] == {"STRESS": 8, "BASE": 0}
    assert receipt["rate_events"] == 3285
    assert receipt["actual_TP1_within_60sec_supported"]
    assert receipt["actual_TP1_nearest_settlement"]["distance_ms"] == 1
    assert {(row["candidate"], row["side"], row["year"]) for row in receipt["episodes"]} == {
        (candidate_id, side, year) for candidate_id, _ in CANDIDATES
        for side in (-1, 1) for year in (2022, 2023)
    }
    assert all(row["status"] == "PASS" and row["stage_cash_quantity_Mark_checks"]
               for row in receipt["episodes"])


def test_audit_rejects_signed_funding_cash_drift(tmp_path, monkeypatch):
    trades, source = synthetic_audit_bundle(tmp_path, monkeypatch)
    trades[0]["funding_cash_usdt"] = "0"
    with pytest.raises(ValueError, match="funding drift|net/funding drift"):
        audit.independent_audit(trades, source)


def test_audit_rejects_tier_fee_drift(tmp_path, monkeypatch):
    trades, source = synthetic_audit_bundle(tmp_path, monkeypatch)
    trades[0]["tiers"][0]["fee_exit"] += 1
    with pytest.raises(ValueError, match="tier fill/fee mismatch"):
        audit.independent_audit(trades, source)


def test_audit_rejects_archive_sha_drift(tmp_path, monkeypatch):
    trades, source = synthetic_audit_bundle(tmp_path, monkeypatch)
    source["successful_sources"][0]["zip_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="archive SHA mismatch"):
        audit.independent_audit(trades, source)
