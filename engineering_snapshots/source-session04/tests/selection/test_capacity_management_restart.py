import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from btc_quant_agent.market_watch.alerting import NotificationNotSent
from btc_quant_agent.platform.backtest import manage_episode
from btc_quant_agent.platform.core import PositionState, dec, primitive
from btc_quant_agent.platform.position_management import supervise
from btc_quant_agent.platform.selection.fixtures import market_event, monitor
from btc_quant_agent.platform.selection.management import ExitPolicy
from btc_quant_agent.platform.selection.store import Capital, SelectorStore


LIMITS = {"total_risk": 0.005, "cluster_risk": 0.005, "gross": 2, "symbol": 0.5, "net_beta": 0.5}


def exposure(id="one", side=1, beta=1, risk=40, symbol="ETHUSDT"):
    return {
        "episode_id": id,
        "symbol": symbol,
        "side": side,
        "beta": beta,
        "risk": risk,
        "notional": 1000,
        "margin": 1000,
        "cluster": "COMMON_CRYPTO",
    }


def test_reservations_use_equity_signed_beta_and_pending_unknown(store):
    cap = Capital(10000, 10000, 100)
    store.reserve(exposure(), cap, 100, LIMITS)
    store.reservation_status("one", "EXECUTION_UNKNOWN")
    with pytest.raises(ValueError, match="TOTAL_RISK_CAPACITY"):
        store.reserve(exposure("two"), cap, 100, LIMITS)
    with pytest.raises(ValueError, match="CANNOT_BE_RELEASED"):
        store.reservation_status("one", "RELEASED_CONFIRMED")
    store.reservation_status("one", "RELEASED_CONFIRMED", execution_confirmed=True)
    assert store.reserve(exposure("two"), cap, 100, LIMITS)
    with pytest.raises(ValueError, match="EQUITY_UNAVAILABLE"):
        store.reserve(exposure("three"), cap, 100000, LIMITS)


def test_opposing_negative_beta_exposure_concentrates_not_offsets(store):
    limits = {**LIMITS, "total_risk": 0.01, "cluster_risk": 0.01, "net_beta": 0.15}
    cap = Capital(10000, 10000, 100)
    store.reserve(exposure(risk=10), cap, 100, limits)
    with pytest.raises(ValueError, match="SIGNED_BETA_CAPACITY"):
        store.reserve(exposure("opposite", side=-1, beta=-1, risk=10, symbol="ALTUSDT"), cap, 100, limits)


def test_first_position_requires_beta_and_existing_pending_evidence(store):
    with pytest.raises(ValueError, match="INCOMPLETE_ESSENTIAL"):
        store.reserve(exposure(beta=None), Capital(10000, 10000, 100), 100, LIMITS)
    with pytest.raises(ValueError, match="INCOMPLETE_ESSENTIAL"):
        store.reserve(
            exposure(),
            Capital(10000, 10000, 100),
            100,
            LIMITS,
            exposures=(exposure("unbound-position", beta=None),),
        )


@pytest.mark.parametrize("case", ["hold", "trail", "partial", "mean", "gap", "missing_quote", "funding"])
def test_replay_and_user_supervisor_exit_parity(setup, case):
    a = setup.anchors
    m = monitor(a, 4, mode="gap" if case == "gap" else "normal", quote=case != "missing_quote")
    position = PositionState(
        "actual",
        a["symbol"],
        a["side"],
        dec(a["anchor"]),
        dec(1),
        dec(a["stop"]),
        dec(a["stop"]),
        1,
        "ISOLATED",
        1,
        "OPEN",
        "USER_REPORTED",
        m.now,
    )
    policy = ExitPolicy(atr=100)
    if case == "trail":
        policy = ExitPolicy(atr=0.1)
    if case == "partial":
        policy = ExitPolicy(atr=100, partial_at_r=0.01)
    if case == "mean":
        policy = ExitPolicy(target=dec(a["anchor"]))
    if case == "funding":
        policy = ExitPolicy(funding_review_due=True, funding_source_known=False)
    event = market_event(m)
    replay = manage_episode(position, event, policy)
    user = supervise(position, event, episode_policy=policy)
    assert primitive(replay) == primitive(user)
    assert (
        user.action
        == {
            "hold": "HOLD",
            "trail": "TIGHTEN_STOP",
            "partial": "PARTIAL_EXIT",
            "mean": "EXIT",
            "gap": "EXIT",
            "missing_quote": "RECONCILE",
            "funding": "RECONCILE",
        }[case]
    )
    if case == "gap":
        assert user.reason == "STOP_GAP" and user.execution_status == "EXECUTION_UNKNOWN"
    assert position.status == "OPEN"  # Recommendations do not mutate execution facts.


def test_confirmed_partial_not_recommended_partial_suppresses_repeat(setup):
    a = setup.anchors
    m = monitor(a, 4)
    p = PositionState(
        "p",
        a["symbol"],
        "LONG",
        dec(a["anchor"]),
        dec(1),
        dec(a["stop"]),
        dec(a["stop"]),
        1,
        "ISOLATED",
        1,
        "OPEN",
        "USER_REPORTED",
        m.now,
    )
    event, policy = market_event(m), ExitPolicy(partial_at_r=0.01)
    assert supervise(p, event, episode_policy=policy).action == "PARTIAL_EXIT"
    assert supervise(p, event, episode_policy=policy).action == "PARTIAL_EXIT"
    assert supervise(replace(p, partial_closes=1), event, episode_policy=policy).action == "HOLD"


def run_worker(path, mode, *args):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(Path.cwd() / "src")}
    return subprocess.run(
        [sys.executable, "tools/selector_worker.py", str(path), mode, *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_genuine_process_restart_dedup_and_unknown_delivery(tmp_path):
    db, wire = tmp_path / "restart.sqlite", tmp_path / "wire.jsonl"
    one = run_worker(db, "notify", wire)
    assert one.returncode == 0, one.stderr
    two = run_worker(db, "notify", wire)
    assert two.returncode == 0, two.stderr
    assert len(wire.read_text().splitlines()) == 1
    assert json.loads(one.stdout) == json.loads(two.stdout)
    crash = run_worker(tmp_path / "crash.sqlite", "crash_send", wire)
    assert crash.returncode == 23
    resume = run_worker(tmp_path / "crash.sqlite", "resume_send", wire)
    assert resume.returncode == 0 and json.loads(resume.stdout)["status"] == "SENDING"
    assert len(wire.read_text().splitlines()) == 2  # Crash send may have escaped; never resend automatically.
    # SENDING after a process crash is explicitly interpreted as unknown delivery, not success.
    assert json.loads(resume.stdout)["delivery"] == "UNKNOWN"


def test_two_processes_cannot_reuse_same_risk_capital(tmp_path):
    path = tmp_path / "race.sqlite"
    SelectorStore(path)  # Initialize schema before the concurrent claims.
    env = {**os.environ, "PYTHONPATH": str(Path.cwd() / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    processes = [
        subprocess.Popen(
            [sys.executable, "tools/selector_worker.py", str(path), "reserve", str(i)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for i in (1, 2)
    ]
    results = [p.communicate(timeout=30) for p in processes]
    assert all(p.returncode == 0 for p in processes), results
    statuses = [json.loads(out)["status"] for out, err in results]
    assert sorted(statuses) == ["REJECTED", "RESERVED"]
    assert len(SelectorStore(path).reservations()) == 1


def test_regime_restart_parity_in_separate_processes(tmp_path):
    db = tmp_path / "regimes.sqlite"
    one = run_worker(db, "regime", 1)
    two = run_worker(db, "regime", 2)
    again = run_worker(db, "regime", 2)
    assert one.returncode == two.returncode == again.returncode == 0
    assert json.loads(one.stdout)["state"] == "UNKNOWN"
    assert json.loads(two.stdout)["state"] == "TREND_UP"
    assert json.loads(two.stdout) == json.loads(again.stdout)


def test_episode_crash_between_prepare_and_state_binding_is_recoverable(tmp_path):
    db, wire = tmp_path / "episode.sqlite", tmp_path / "episode-wire.jsonl"
    crash = run_worker(db, "episode_crash_after_prepare", wire)
    assert crash.returncode == 24
    resume = run_worker(db, "episode_resume", wire)
    repeat = run_worker(db, "episode_resume", wire)
    assert resume.returncode == repeat.returncode == 0, (resume.stderr, repeat.stderr)
    assert json.loads(resume.stdout) == json.loads(repeat.stdout)
    assert len(wire.read_text().splitlines()) == 1


@pytest.mark.parametrize("failure,expected", [("definite", "FAILED"), ("unknown", "UNKNOWN")])
def test_sender_failures_remain_distinct_and_replay_safe(store, failure, expected):
    id = store.commit_decision({"risk": "EXIT", "fixture": failure}, 100, 101)
    event = store.prepare(id, "BTCUSDT", 101)

    def sender(wire):
        if failure == "definite":
            raise NotificationNotSent("OFFLINE_DEFINITE_FAILURE")
        raise RuntimeError("OFFLINE_UNKNOWN_DELIVERY")

    assert store.dispatch(event, sender, 102) == expected
    calls = []
    status = store.dispatch(event, lambda x: calls.append(x), 103)
    assert len(calls) == (1 if failure == "definite" else 0)
    assert status == ("SENDER_ACCEPTED" if failure == "definite" else "UNKNOWN")


def test_position_report_is_not_available_to_a_past_observation(setup):
    a = setup.anchors
    m = monitor(a, 4)
    p = PositionState(
        "future-report",
        a["symbol"],
        "LONG",
        dec(a["anchor"]),
        dec(1),
        dec(a["stop"]),
        dec(a["stop"]),
        1,
        "ISOLATED",
        1,
        "OPEN",
        "USER_REPORTED",
        m.now + 1,
    )
    result = supervise(p, market_event(m), episode_policy=ExitPolicy(atr=a["atr"]))
    assert result.action == "RECONCILE" and result.reason == "POSITION_REPORT_AFTER_OBSERVATION"
