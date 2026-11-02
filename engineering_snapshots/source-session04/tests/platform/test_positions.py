from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal

import pytest

from btc_quant_agent.platform.core import UserReportedFill
from btc_quant_agent.platform.demos import market, notification_demo, position_demo
from btc_quant_agent.platform.position_management import AdvisoryStore, supervise


def new_position(tmp_path):
    e = market(100, 1)
    store = AdvisoryStore(tmp_path / "positions.sqlite")
    f = UserReportedFill(
        "report",
        "position",
        e.spec.symbol,
        "LONG",
        Decimal("100"),
        Decimal("2"),
        e.decision_ts - 1,
        e.decision_ts,
    )
    return store, f, store.report(f, e.spec, stop=Decimal("98")), e


def test_user_fills_are_idempotent_and_conflicts_are_rejected(tmp_path):
    store, fill, p, e = new_position(tmp_path)
    assert store.report(fill, e.spec, stop=Decimal("98")) == p
    with pytest.raises(ValueError, match="CONFLICTING_REPORT_ID"):
        store.report(replace(fill, quantity=Decimal("3")), e.spec, stop=Decimal("98"))
    with pytest.raises(ValueError, match="ACTUAL_FILL"):
        store.report(replace(fill, report_id="sim", source="SIMULATED"), e.spec, stop=Decimal("98"))


def test_partial_close_addition_and_history(tmp_path):
    store, f, p, e = new_position(tmp_path)
    close = replace(
        f, report_id="close", operation="CLOSE", quantity=Decimal(".5"), received_ts=e.decision_ts + 1
    )
    p2 = store.report(close, e.spec)
    assert p2.quantity == Decimal("1.5") and p2.version == 2 and p2.status == "OPEN"
    assert p2.partial_closes == 1
    assert supervise(p2, market(104, 3)).action != "PARTIAL_EXIT"
    addition = replace(
        f, report_id="add", price=Decimal("102"), quantity=Decimal(".5"), received_ts=e.decision_ts + 2
    )
    p3 = store.report(addition, e.spec)
    assert p3.entry == Decimal("100.5") and p3.quantity == 2
    assert store.report(close, e.spec) == p2  # Duplicate report returns its exact historical receipt.
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM platform_position_versions").fetchone()[0] == 3


def test_exit_recommendation_is_not_execution_and_risk_survives_no_quote(tmp_path):
    store, f, p, e = new_position(tmp_path)
    a = supervise(p, market(90, 2, quote=False))
    assert a.action == "EXIT" and a.execution_status == "EXECUTION_UNKNOWN" and "STOP_BREACHED" in a.reason
    assert store.position(p.id).status == "OPEN"
    a = supervise(p, market(101, 3, quote=False))
    assert a.action == "RECONCILE"
    event = market(101, 3)
    assert supervise(p, replace(event, decision_ts=event.decision_ts + 200000)).action == "RECONCILE"


def test_stop_amendment_cannot_loosen_or_overwrite_concurrent_version(tmp_path):
    store, f, p, e = new_position(tmp_path)
    p2 = store.amend_stop(p.id, Decimal("99"), e.spec, e.decision_ts + 1, expected_version=1)
    assert p2.version == 2
    with pytest.raises(ValueError, match="STOP_CANNOT_LOOSEN"):
        store.amend_stop(p.id, Decimal("98"), e.spec, e.decision_ts + 2, expected_version=2)
    with pytest.raises(ValueError, match="POSITION_VERSION_CONFLICT"):
        store.amend_stop(p.id, Decimal("100"), e.spec, e.decision_ts + 2, expected_version=1)


def test_existing_outbox_definite_unknown_and_restart_semantics(tmp_path):
    result = notification_demo(tmp_path)
    assert result["fake_sender_calls"] == 1 and result["after_restart"] == "SENDER_ACCEPTED"


def test_atomic_notification_claim_and_persist_before_sender(tmp_path):
    store = AdvisoryStore(tmp_path / "store.sqlite")
    id = store.commit_decision({"action": "WATCH"}, 100, 100)
    event = store.prepare(id, "BTCUSDT", 100)
    with ThreadPoolExecutor(2) as pool:
        claims = list(
            pool.map(
                lambda _: AdvisoryStore(tmp_path / "store.sqlite").claim_notification(event, 101), range(2)
            )
        )
    assert sorted(claims) == [False, True]
    assert store.get_notification(event)["remote_acceptance_status"] == "UNKNOWN"
    with pytest.raises(ValueError, match="COMMIT_BEFORE_DECISION"):
        store.commit_decision({}, 100, 99)
    with pytest.raises(ValueError, match="DECISION_NOT_COMMITTED"):
        store.prepare("missing", "BTCUSDT", 100)


def test_position_full_demonstration(tmp_path):
    result = position_demo(tmp_path)
    assert result["confirmed_close"]["status"] == "CLOSED"


def test_immutable_origin_cannot_rebind_to_different_evidence(tmp_path):
    store = AdvisoryStore(tmp_path / "origins.sqlite")
    first = store.commit_decision({"action": "WATCH"}, 100, 100, origin="same-observation")
    assert store.commit_decision({"action": "WATCH"}, 100, 101, origin="same-observation") == first
    with pytest.raises(ValueError, match="IMMUTABLE_ORIGIN_CONFLICT"):
        store.commit_decision({"action": "ENTRY_ELIGIBLE"}, 100, 101, origin="same-observation")


def test_user_position_funding_is_chronological_and_idempotent(tmp_path):
    store, fill, p, e = new_position(tmp_path)
    event = market(101, 3)
    event = replace(event, derivatives=replace(event.derivatives, funding_settlement=True))
    settled = store.settle_funding(p.id, event)
    assert settled.funding == pytest.approx(-2 * 101 * 0.0001)
    assert settled.version == 2 and store.settle_funding(p.id, event) == settled
    bad = replace(event, derivatives=replace(event.derivatives, funding_rate=0.001))
    with pytest.raises(ValueError, match="FUNDING_EVENT_CONFLICT"):
        store.settle_funding(p.id, bad)


def test_position_management_obeys_configured_exit_policy(tmp_path):
    from btc_quant_agent.platform.config import ExitConfig

    store, fill, p, e = new_position(tmp_path)
    policy = ExitConfig(partial_at_r=2.5, partial_fraction=0.3, trailing_atr=3)
    tighten = supervise(p, market(104, 3), atr=0.4, policy=policy)
    assert tighten.action == "TIGHTEN_STOP" and tighten.suggested_stop == Decimal("102.79")
    partial = supervise(p, market(106, 4), atr=0.4, policy=policy)
    assert partial.action == "PARTIAL_EXIT" and partial.fraction == 0.3
