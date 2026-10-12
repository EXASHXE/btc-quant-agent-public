"""Independent Decimal cash oracle and explicit unsafe-port witnesses."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from scripts.g1_offline_preview_r1.__main__ import OfflineLLMAnalysisPort, load_fixture
from scripts.g1_offline_preview_r1.fixtures import make_fixture
from scripts.g1_offline_preview_r1.model import SafetyViolation, digest, initial_state
from scripts.g1_offline_preview_r1.reducer import transition
from tests.test_v06_g1_offline_preview_r1_core import analyzed, ev, fresh, rejected


def reference_journal(side):
    # Independently calculated from the invented fixture's actual price clocks.
    # Values below are not calls into the reducer's execution/fee functions.
    if side == "LONG":
        entry, tp, stop, marks, sign = (
            "30015.0",
            "30284.8",
            "29885.0",
            ["30312", "30207", "30207"],
            D(1),
        )
    else:
        entry, tp, stop, marks, sign = (
            "29985.0",
            "29714.9",
            "30115.1",
            ["29688", "29793", "29793"],
            D(-1),
        )
    entry, tp, stop = map(D, (entry, tp, stop))
    q = D(".01")
    half = D(".005")
    fee = D(".0006")
    cash = D(1000)
    rows = [
        ("ENTRY_FEE", 60004, -q * entry * fee),
        ("FUNDING", 21660001, -sign * half * D(marks[0]) * D(".0001")),
        ("TP1_NET", 21719999, sign * half * (tp - entry) - half * tp * fee),
        ("FUNDING", 28800000, -sign * half * D(marks[1]) * D(".0001")),
        ("FUNDING", 36000000, -sign * half * D(marks[2]) * D("-.0002")),
        ("STOP_NET", 43319999, sign * half * (stop - entry) - half * stop * fee),
    ]
    result = []
    for kind, at, delta in rows:
        cash += delta
        result.append(
            {
                "kind": kind,
                "at": at,
                "cash_delta": format(delta, "f"),
                "cash_after": format(cash, "f"),
            }
        )
    return result


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_complete_24h_independent_decimal_journal(side):
    fixture = make_fixture(side)
    s = initial_state(fixture["trusted_approvals"])
    expected = reference_journal(side)
    seen = 0
    cash = D(1000)
    for event in fixture["events"]:
        before = s
        s = transition(s, event)
        if event["kind"] in ("TP1", "STOP"):
            assert s["cash"] == before["cash"]  # pending proceeds never spendable
        while seen < len(s["journal"]):
            actual = s["journal"][seen]
            want = expected[seen]
            assert actual["kind"] == want["kind"] and actual["at"] == want["at"]
            assert D(actual["cash_delta"]) == D(want["cash_delta"])
            cash += D(want["cash_delta"])
            assert D(s["cash"]) == cash
            seen += 1
    assert seen == 6 and s["phase"] == "CLOSED" and not s["pending_cash"]
    assert D(s["reserved_notional"]) == 0 and all(n == 0 for n in s["counters"].values())
    assert cash == D("1000.33834810" if side == "LONG" else "1000.34054750")


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("hours", [12, 18, 24])
def test_all_event_time_caps_full_workflow(side, hours):
    fixture = make_fixture(side, hours, "TIME_CAP")
    s = initial_state(fixture["trusted_approvals"])
    for event in fixture["events"]:
        s = transition(s, event)
    fills = [x for x in s["trace"] if x["kind"] == "TIME_CAP" and "fill_price" in x]
    assert len(fills) == 1 and s["phase"] == "CLOSED"
    assert 0 <= fills[0]["at"] - (60004 + hours * 3600000) < 60000
    assert not s["required_exit"] and D(s["remaining_qty"]) == 0


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_registered_tp2_capped_execution(side):
    fixture = make_fixture(side, 24, "TP2")
    s = initial_state(fixture["trusted_approvals"])
    for event in fixture["events"]:
        s = transition(s, event)
    fill = next(x for x in s["trace"] if x["kind"] == "TP2" and "fill_price" in x)
    assert D(fill["quantity"]) == D(".005") and s["phase"] == "CLOSED"
    assert D(fill["fill_price"]) == D("30584.7" if side == "LONG" else "29414.7")


@pytest.mark.parametrize(
    "raw",
    ["{", "[]", "null", '{"x":1,"x":2}', '{"as_of":NaN}', '{"risk":"APPROVE","place_order":true}'],
)
def test_malformed_llm_port_has_no_ledger_authority(raw):
    s = analyzed()
    before = digest(s)
    with pytest.raises(SafetyViolation):
        OfflineLLMAnalysisPort().analyze(raw)
    assert digest(s) == before and not s["journal"] and s["order_id"] is None


@pytest.mark.parametrize(
    ("mutation", "at", "code"),
    [
        ({"quantity": "0.03"}, 60002, "APPROVAL_DRIFT"),
        ({"proposal_hash": "different"}, 60002, "APPROVAL_DRIFT"),
        ({"proposal_version": 2}, 60002, "APPROVAL_FIXTURE_INVALID"),
        ({"signal_id": "other"}, 60002, "APPROVAL_DRIFT"),
        ({"issued_at": 60003}, 60002, "APPROVAL_STALE_OR_REORDERED"),
        ({"issued_at": 60000}, 60002, "APPROVAL_STALE_OR_REORDERED"),
        ({"expires_at": 60002}, 60002, "APPROVAL_FIXTURE_INVALID"),
    ],
)
def test_explicit_human_token_drift_or_clock_never_places(mutation, at, code):
    s, b, p = fresh()
    token = next(iter(s["trusted_approvals"].values())) | mutation
    if code == "APPROVAL_FIXTURE_INVALID":
        before = digest(s)
        with pytest.raises(SafetyViolation, match=code):
            initial_state([token])
        assert digest(s) == before and not s["journal"]
        return
    s = initial_state([token])
    s = transition(s, ev("BAR", 59999, b))
    s = transition(s, ev("PROPOSE", 60000, p))
    a = {
        "schema_version": 1,
        "signal_id": "s1",
        "proposal_hash": digest(p),
        "source_hash": digest(b),
        "as_of": 60000,
        "summary": "synthetic",
        "risk": "DESCRIPTIVE_ONLY",
    }
    s = transition(s, ev("ANALYZE", 60001, a))
    rejected(s, ev("APPROVE", at, {"token_id": "human1"}), code)
    assert not s["journal"] and s["order_id"] is None


def test_private_fixture_path_denied_before_filesystem(monkeypatch):
    from pathlib import Path

    def unexpected(*args, **kwargs):
        raise AssertionError("filesystem called before lexical admission")

    monkeypatch.setattr(Path, "stat", unexpected)
    monkeypatch.setattr(Path, "read_bytes", unexpected)
    with pytest.raises(SafetyViolation, match="FIXTURE_PATH_SCOPE"):
        load_fixture("/root/workspace/project/Quant-agent/data/forbidden.json")


def test_mock_redacts_credential_text_before_any_durable_storage():
    a = make_fixture()["events"][2]["payload"]
    a = {**a, "summary": "api_key=secret123 bearer abcdef password=hidden"}
    result = OfflineLLMAnalysisPort().analyze(a)
    assert (
        "secret123" not in result["summary"]
        and "abcdef" not in result["summary"]
        and "hidden" not in result["summary"]
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--unknown=api_key=FAKE_PRIVATE_VALUE"],
        ["--crash-edge", "password=FAKE_PRIVATE_VALUE"],
    ],
)
def test_cli_argument_errors_never_echo_credentials_or_create_state(args, tmp_path, capsys):
    from scripts.g1_offline_preview_r1.__main__ import main

    target = tmp_path / "must-not-exist"
    with pytest.raises(SystemExit) as exc:
        main([*args, "--output", str(target)])
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert "CLI_ARGUMENTS_INVALID" in captured.err
    assert "FAKE_PRIVATE_VALUE" not in captured.err + captured.out
    assert "api_key" not in captured.err + captured.out
    assert not target.exists()
