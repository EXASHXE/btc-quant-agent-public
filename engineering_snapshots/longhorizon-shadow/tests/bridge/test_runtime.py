from dataclasses import replace

import pytest

from btc_quant_agent.platform.bridge.contracts import Receipt
from btc_quant_agent.platform.bridge.fixtures import OfflineFixtureProvider
from btc_quant_agent.platform.bridge.runtime import BridgeStore, ReadOnlyScanner
from btc_quant_agent.platform.core import UserReportedFill, dec


def candidates(result, symbol="BTCUSDT"):
    return [r for r in result["records"] if r["kind"] == "CANDIDATE" and r["symbol"] == symbol]


@pytest.mark.parametrize("provider", ["binance", "okx"])
def test_full_offline_provider_factor_strategy_risk_lifecycle(config, tmp_path, provider):
    config = config.model_copy(update={"provider": provider})
    source = OfflineFixtureProvider(config)
    store = BridgeStore(tmp_path / "bridge.sqlite")
    scanner = ReadOnlyScanner(config, store)
    watch = scanner.scan(source.snapshot(50))
    eligible = scanner.scan(source.snapshot(51))
    expired = scanner.scan(source.snapshot(57))
    assert candidates(watch)[0]["state"] == "WATCH"
    plan = candidates(eligible)[0]["plan"]
    assert plan["state"] == "ENTRY_ELIGIBLE" and plan["risk"]["modeled_loss"] <= plan["risk"]["budget"]
    assert plan["entry_price"] is not None and plan["risk"]["quantity"] != "0"
    assert candidates(expired)[0]["state"] == "EXPIRED" and candidates(expired)[0]["action"] == "CANCEL"
    assert plan["candidate"]["id"] == candidates(watch)[0]["candidate"]["id"]
    assert len(watch["strategy_evaluations"]) == 9
    assert len({v["evaluated_snapshot"] for v in watch["strategy_evaluations"]}) == 1
    for receipt in eligible["persistence"]:
        assert store.get_notification(receipt["event_id"])["status"] == "PENDING"
    assert store.positions() == []


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("missing_quote", "EXECUTABLE_QUOTE_MISSING"),
        ("stale_quote", "QUOTE_STALE"),
        ("clock_error", "EXECUTABLE_QUOTE_MISSING"),
        ("high_spread", "SPREAD_LIMIT"),
        ("derivative_failure", "FUNDING_MISSING_OR_STALE"),
    ],
)
def test_degraded_sources_preserve_watch_but_veto_entry(config, tmp_path, scenario, expected):
    source = OfflineFixtureProvider(config, scenario)
    scanner = ReadOnlyScanner(config, BridgeStore(tmp_path / "scan.sqlite"))
    watch = scanner.scan(source.snapshot(50))
    later = scanner.scan(source.snapshot(51))
    assert candidates(watch)[0]["state"] == "WATCH"
    assert expected in candidates(later)[0]["veto_reasons"]
    assert all(x.get("state") != "ENTRY_ELIGIBLE" for x in later["records"])


def test_five_minute_manual_response_and_expiry_do_not_reset_the_plan(config, tmp_path):
    config = config.model_copy(
        update={
            "platform": config.platform.model_copy(
                update={"execution": config.platform.execution.model_copy(update={"delay_minutes": 5})}
            )
        }
    )
    source = OfflineFixtureProvider(config)
    scanner = ReadOnlyScanner(config, BridgeStore(tmp_path / "scan.sqlite"))
    scanner.scan(source.snapshot(50))
    armed = scanner.scan(source.snapshot(51))
    ready = scanner.scan(source.snapshot(55))
    expired = scanner.scan(source.snapshot(57))
    assert (
        candidates(armed)[0]["state"] == "ARMED"
        and "MANUAL_DELAY_PENDING" in candidates(armed)[0]["veto_reasons"]
    )
    assert candidates(ready)[0]["state"] == "ENTRY_ELIGIBLE"
    assert candidates(expired)[0]["state"] == "EXPIRED"


def test_snapshot_restart_dedup_and_origin_conflict(config, tmp_path):
    source = OfflineFixtureProvider(config)
    path = tmp_path / "scan.sqlite"
    first = ReadOnlyScanner(config, BridgeStore(path)).scan(source.snapshot(50))
    restarted = ReadOnlyScanner(config, BridgeStore(path)).scan(source.snapshot(50))
    assert first == restarted
    b = source.snapshot(50)
    r = next(r for r in b.receipts if r.channel == "quote")
    d = r.payload
    d["bidPrice"] = str(dec(d["bidPrice"]) - dec(".01"))
    changed = Receipt.make(
        r.provider, r.channel, r.instrument_id, r.received_ts, r.available_ts, d, exposure="SYNTHETIC"
    )
    with pytest.raises(ValueError, match="SNAPSHOT_ORIGIN_CONFLICT"):
        ReadOnlyScanner(config, BridgeStore(path)).scan(
            replace(b, receipts=tuple(changed if x.id == r.id else x for x in b.receipts))
        )


def test_crash_before_preview_repairs_from_frozen_snapshot(config, tmp_path, monkeypatch):
    store = BridgeStore(tmp_path / "scan.sqlite")
    source = OfflineFixtureProvider(config)

    def crash(result):
        raise RuntimeError("FABRICATED_CRASH_AFTER_SNAPSHOT_COMMIT")

    monkeypatch.setattr(store, "preview_receipts", crash)
    with pytest.raises(RuntimeError, match="FABRICATED_CRASH"):
        ReadOnlyScanner(config, store).scan(source.snapshot(50))
    recovered = ReadOnlyScanner(config, BridgeStore(tmp_path / "scan.sqlite")).scan(source.snapshot(50))
    assert candidates(recovered)[0]["state"] == "WATCH" and recovered["persistence"]


def test_liquid_universe_and_multi_strategy_direction_conflicts(config, tmp_path):
    source = OfflineFixtureProvider(config, "illiquid")
    scanner = ReadOnlyScanner(config, BridgeStore(tmp_path / "scan.sqlite"))
    r = scanner.scan(source.snapshot(55))
    assert not candidates(r, "SOLUSDT")
    evaluations = [x for x in r["strategy_evaluations"] if x["symbol"] == "BTCUSDT"]
    assert {x["direction"] for x in evaluations} == {"LONG", "SHORT"}
    assert any("STRATEGY_CONFLICT_OR_LOWER_PRIORITY" in x["reasons"] for x in evaluations)
    assert candidates(r)[0]["candidate"]["direction"] == "LONG"


def test_user_reported_position_risk_survives_missing_quote_and_exit_is_not_close(config, tmp_path):
    source = OfflineFixtureProvider(config)
    store = BridgeStore(tmp_path / "scan.sqlite")
    scanner = ReadOnlyScanner(config, store)
    scanner.scan(source.snapshot(50))
    r = scanner.scan(source.snapshot(51))
    plan = candidates(r)[0]["plan"]
    fill = UserReportedFill(
        "fixture-user-report",
        "fixture-position",
        "BTCUSDT",
        "LONG",
        dec(plan["entry_price"]),
        dec("1"),
        r["decision_ts"] + 1,
        r["decision_ts"] + 2,
    )
    reported = store.report_plan_fill(plan["candidate"]["id"], fill)
    assert reported["position"]["status"] == "OPEN"
    b = OfflineFixtureProvider(config, "missing_quote").snapshot(52)
    stop = dec(plan["candidate"]["stop"])
    receipts = []
    for receipt in b.receipts:
        if (
            receipt.channel == "candles"
            and receipt.instrument_id == "BTCUSDT"
            and receipt.payload[0][6] == source.data["BTCUSDT"][52].candle.close_time_ms
        ):
            rows = receipt.payload
            rows[0][3] = str(stop - dec("1"))
            rows[0][4] = str(stop - dec(".5"))
            receipt = Receipt.make(
                receipt.provider,
                receipt.channel,
                receipt.instrument_id,
                receipt.received_ts,
                receipt.available_ts,
                rows,
                exposure="SYNTHETIC",
            )
        receipts.append(receipt)
    risk = scanner.scan(replace(b, receipts=tuple(receipts)))
    action = next(x for x in risk["records"] if x["kind"] == "POSITION_RISK")
    assert action["severity"] == "RISK" and action["action"]["action"] == "EXIT"
    assert action["action"]["execution_status"] == "EXECUTION_UNKNOWN"
    assert store.position(fill.position_id).status == "OPEN"
    assert not any(x.get("state") == "ENTRY_ELIGIBLE" and x["symbol"] == "BTCUSDT" for x in risk["records"])
    assert any("USER_REPORTED_POSITION_EXISTS" in x.get("veto_reasons", []) for x in risk["records"])
    closed = store.report_plan_fill(
        plan["candidate"]["id"],
        replace(
            fill,
            report_id="user-close",
            operation="CLOSE",
            user_action_ts=b.decision_ts + 1,
            received_ts=b.decision_ts + 2,
        ),
    )
    assert closed["position"]["status"] == "CLOSED"


def test_future_user_report_is_not_visible_to_an_earlier_decision(config, tmp_path):
    source = OfflineFixtureProvider(config)
    store = BridgeStore(tmp_path / "asof.sqlite")
    scanner = ReadOnlyScanner(config, store)
    scanner.scan(source.snapshot(50))
    r = scanner.scan(source.snapshot(51))
    plan = candidates(r)[0]["plan"]
    fill = UserReportedFill(
        "late-receipt",
        "future-position",
        "BTCUSDT",
        "LONG",
        dec(plan["entry_price"]),
        dec("1"),
        r["decision_ts"],
        r["decision_ts"] + 180000,
    )
    store.report_plan_fill(plan["candidate"]["id"], fill)
    assert store.positions(source.snapshot(52).decision_ts) == []
    assert len(store.positions(source.snapshot(54).decision_ts)) == 1


def test_missing_oi_is_optional_for_price_strategy_but_can_be_required(config, tmp_path):
    for required in (False, True):
        c = config.model_copy(
            update={
                "admission": config.admission.model_copy(update={"require_open_interest_for_entry": required})
            }
        )
        source = OfflineFixtureProvider(c, "missing_oi")
        scanner = ReadOnlyScanner(c, BridgeStore(tmp_path / (str(required) + ".sqlite")))
        scanner.scan(source.snapshot(50))
        result = scanner.scan(source.snapshot(51))
        row = candidates(result)[0]
        assert (row["state"] == "ENTRY_ELIGIBLE") is (not required)
        if required:
            assert "OPEN_INTEREST_MISSING_OR_STALE" in row["veto_reasons"]


def test_vote_tie_has_no_winning_direction(config, tmp_path):
    platform = config.platform.model_copy(
        update={
            "strategies": [config.platform.strategies[0], config.platform.strategies[2]],
            "entry": config.platform.entry.model_copy(update={"aggregation": "vote"}),
        }
    )
    c = config.model_copy(update={"platform": platform})
    source = OfflineFixtureProvider(c)
    result = ReadOnlyScanner(c, BridgeStore(tmp_path / "tie.sqlite")).scan(source.snapshot(55))
    assert not candidates(result)
    assert any(
        "STRATEGY_VOTE_TIE" in x["reasons"]
        for x in result["strategy_evaluations"]
        if x["symbol"] == "BTCUSDT"
    )
