"""Independent runtime witnesses, not engine acceptance or A receipt assertions.

Tests named ``capture`` deliberately record a reproduced contract violation.
A passing verifier test is evidence that its negative witness was reproduced,
never a PASS verdict for the target engine.
"""

import dataclasses
import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def audit():
    path = Path(__file__).resolve().parents[1] / "scripts/strategy_research/r3_alt_verification/final_audit.py"
    spec = importlib.util.spec_from_file_location("independent_final_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = os.environ.get("P1_FINAL_TARGET_ROOT")
    if not target:
        pytest.skip("Exact A archive required via P1_FINAL_TARGET_ROOT; no installed-source fallback or network fetch")
    modules, proof = module.load_target(target)
    return module, modules, proof


def setup_state(audit, **kwargs):
    _, modules, _ = audit
    m = modules["model"]
    key = m.OwnerKey("BASE", "BTC_OWNER")
    owner_args = {"owner_key": key, "candidate_id": "STRUCTURAL_CONTINUATION_LONG_04H",
                  "symbol": "BTCUSDT", "direction": m.Direction.LONG,
                  "phase": m.OwnerPhase.CLOSED_UNSETTLED, "cash_settled": Decimal(1000)}
    owner_args.update(kwargs)
    owner = m.OwnerLedger(**owner_args)
    state = m.EngineState(1699999200000, 1699999200000, owner_ledgers={key: owner},
                          opening_equity_posted={"BASE": True})
    return key, owner, state


def test_exact_archive_import_identity(audit):
    _, _, proof = audit
    root = Path(os.environ["P1_FINAL_TARGET_ROOT"]).resolve()
    assert len(proof) == 4
    assert all(Path(p["file"]).is_relative_to(root / "src") for p in proof.values())


def test_normalized_funding_projection(audit):
    _, modules, _ = audit
    m, money = modules["model"], modules["money"]
    key, btc, state = setup_state(audit, enc_exit_fee=Decimal(7), funding_payable=Decimal(1),
                                  enc_funding_dedicated=Decimal(".4"), enc_shortfall=Decimal(".6"))
    ethkey = m.OwnerKey("BASE", "ETH_WITNESS")
    eth = dataclasses.replace(btc, owner_key=ethkey, symbol="ETHUSDT", cash_settled=Decimal(0),
                              enc_exit_fee=Decimal(0), funding_payable=Decimal(0),
                              enc_funding_dedicated=Decimal(0), enc_shortfall=Decimal(0),
                              enc_funding_future=Decimal(2))
    state = dataclasses.replace(state, owner_ledgers={key: btc, ethkey: eth})
    p = money.project_as_of("BASE", state, state.clock_ms)
    assert p.A == Decimal(940)
    assert p.E_d == Decimal(1000)
    assert p.E_r == Decimal(999)


def test_normalized_pending_loss_proof_floor(audit):
    _, modules, _ = audit
    m = modules["model"]
    key, owner, state = setup_state(audit, phase=m.OwnerPhase.EXIT_PENDING)
    loss = m.PendingExitSlice("LOSS", Decimal(1), Decimal(100), Decimal(100),
                             -Decimal("169.336545"), Decimal(0), state.clock_ms - 1,
                             state.clock_ms + 60000, m.ExitReason.STOP_LOSS, True)
    owner = dataclasses.replace(owner, pending_exit_slices=(loss,), trade_payable=Decimal("169.336545"))
    state = dataclasses.replace(state, owner_ledgers={key: owner})
    before = modules["money"].project_as_of("BASE", state, state.clock_ms)
    after = modules["money"].project_as_of("BASE", state, state.clock_ms + 60000)
    assert before.E_r == Decimal(1000)
    assert after.E_r == Decimal("830.663455")
    assert after.killed and after.A == 0


def test_acknowledged_live_profit_formula(audit):
    _, modules, _ = audit
    m = modules["model"]
    _, _, state = setup_state(audit, phase=m.OwnerPhase.ACKED_OPEN,
                                quantity=Decimal(".006"), entry_price=Decimal(50000),
                                initial_stop=Decimal(49000), target=Decimal(52000),
                                funding_payable=Decimal(".1"), enc_funding_dedicated=Decimal(".1"))
    state = dataclasses.replace(state, latest_marks={"BTCUSDT": Decimal(50500)})
    p = modules["money"].project_as_of("BASE", state, state.clock_ms)
    assert p.E_d == Decimal(1003)
    assert p.E_c == Decimal(1003)
    assert p.E_r == Decimal("1002.9")
    assert p.A == Decimal("952.75")
    assert not p.killed


def test_capture_missing_shortfall_accepted(audit):
    _, modules, _ = audit
    _, _, state = setup_state(audit, funding_payable=Decimal(1), enc_funding_dedicated=Decimal(".4"))
    p = modules["money"].project_as_of("BASE", state, state.clock_ms)
    checks = modules["money"].assert_invariants(state, "BASE")
    assert checks["I05"] is True  # Reproduced negative witness, not semantic PASS.
    assert p.L_f == 0 and p.A == Decimal("949.6")
    assert p.A != Decimal(949), "The normative owner-union result is949, not949.6"


def test_capture_unposted_cash_accepted(audit):
    _, modules, _ = audit
    _, _, state = setup_state(audit, cash_settled=Decimal(1234))
    assert not state.postings
    checks = modules["money"].assert_invariants(state, "BASE")
    assert checks["I07"] is True  # Cash-to-journal violation explicitly reproduced.


def test_capture_over_exit_public_reducer(audit):
    helper, modules, _ = audit
    m = modules["model"]
    key, _, state = setup_state(audit, phase=m.OwnerPhase.ACKED_OPEN, quantity=Decimal(1),
                                entry_price=Decimal(100), initial_stop=Decimal(90), target=Decimal(120))
    event = helper.make_event(modules, m.EventKind.ECONOMIC_EXIT,
                              {"quantity": "2", "raw_price": "90", "effective_price": "90",
                               "exit_fee": "0", "exit_reason": "STOP_LOSS", "slice_id": "OVER_EXIT"}, key)
    cfg = m.ReplayConfig(("STRUCTURAL_CONTINUATION_LONG_04H",), m.CostScenario.BASE)
    result, _, _ = modules["reducer"].reduce(state, event, cfg)
    assert result.owner_ledgers[key].pending_exit_slices[0].quantity == 2
    assert result.owner_ledgers[key].trade_payable == 20
    assert modules["money"].assert_invariants(result, "BASE")["I16"] is True


def test_capture_immutable_clock_conflict_ignored(audit):
    helper, modules, _ = audit
    key, _, state = setup_state(audit)
    m = modules["model"]
    cfg = m.ReplayConfig(("STRUCTURAL_CONTINUATION_LONG_04H",), m.CostScenario.BASE)
    event = helper.make_event(modules, m.EventKind.RISK_KILL, {}, key, "CLOCK_CONFLICT")
    first = modules["reducer"].reduce(state, event, cfg)[0]
    altered = dataclasses.replace(event, available_at_ms=event.available_at_ms + 60000)
    second = modules["reducer"].reduce(first, altered, cfg)[0]
    assert second == first  # Envelope changed; required conflict was not raised.


@pytest.mark.parametrize("prices", [("50000", "52000"), ("52000", "50000")])
def test_same_close_mark_conflict_enforced(audit, prices):
    helper, modules, _ = audit
    key, _, state = setup_state(audit)
    m = modules["model"]
    cfg = m.ReplayConfig(("STRUCTURAL_CONTINUATION_LONG_04H",), m.CostScenario.BASE)
    e1 = helper.make_event(modules, m.EventKind.OBSERVED_MARK,
                           {"price": prices[0], "close_ms": state.clock_ms}, key, "MARK1",
                           available=state.clock_ms + 60000)
    e2 = helper.make_event(modules, m.EventKind.OBSERVED_MARK,
                           {"price": prices[1], "close_ms": state.clock_ms}, key, "MARK2",
                           available=state.clock_ms + 60000)
    first = modules["reducer"].reduce(state, e1, cfg)[0]
    with pytest.raises(modules["journal"].ConflictFailClosedError):
        modules["reducer"].reduce(first, e2, cfg)


def test_capture_shared_book_loss_kills_unrelated_candidate(audit):
    _, modules, _ = audit
    m = modules["model"]
    key, lossowner, state = setup_state(audit, phase=m.OwnerPhase.EXIT_PENDING)
    s = m.PendingExitSlice("A_LOSS", Decimal(1), Decimal(100), Decimal(0), -Decimal(100),
                          Decimal(0), state.clock_ms - 1, state.clock_ms, m.ExitReason.STOP_LOSS, True)
    lossowner = dataclasses.replace(lossowner, pending_exit_slices=(s,), trade_payable=Decimal(100))
    bkey = m.OwnerKey("BASE", "CANDIDATE_B")
    bowner = dataclasses.replace(lossowner, owner_key=bkey, candidate_id="STRUCTURAL_CONTINUATION_LONG_12H",
                                cash_settled=Decimal(0), pending_exit_slices=(), trade_payable=Decimal(0))
    combined = dataclasses.replace(state, owner_ledgers={key: lossowner, bkey: bowner})
    pooled = modules["money"].project_as_of("BASE", combined, state.clock_ms)
    solo_b = dataclasses.replace(state, owner_ledgers={bkey: dataclasses.replace(bowner, cash_settled=Decimal(1000))})
    alone = modules["money"].project_as_of("BASE", solo_b, state.clock_ms)
    assert pooled.killed and pooled.A == 0
    assert not alone.killed and alone.A == Decimal(950)
    # PUBLIC_API normalized loss/kill; no claim of nonzero full-replay trade interference.


def test_capture_full_replay_duplicate_mark_ingestion(audit):
    helper, modules, _ = audit
    m, rp = modules["model"], modules["replay"]
    t = helper.START
    bar = m.Bar1m(t, Decimal(100), Decimal(102), Decimal(99), Decimal(101), Decimal(10), "BTCUSDT")
    marks = [m.MarkBar1m(t, Decimal(100), Decimal(102), Decimal(99), Decimal(price), "BTCUSDT", t + 120000)
             for price in ("100", "101")]
    observed = []
    for ordering in (marks, list(reversed(marks))):
        dataset = rp.SyntheticDataset("INDEPENDENT_CONFLICTING_SOURCE_CLOSE",
                                      {"BTCUSDT": [bar]}, {"BTCUSDT": ordering},
                                      {"BTCUSDT": m.SymbolFilters("BTCUSDT", Decimal(".1"), Decimal(".001"))})
        observed.append(helper.run_replay(modules, dataset, ["STRUCTURAL_CONTINUATION_LONG_04H"],
                                           m.CostScenario.BASE))
    assert all(r["exception"] is None for r in observed)  # Required fail-closed was bypassed.
    assert observed[0]["observed_final_marks"]["BTCUSDT"] == "101"
    assert observed[1]["observed_final_marks"]["BTCUSDT"] == "100"
    out = os.environ.get("P1_FINAL_SMALL_PROBE_OUTPUT")
    if out:
        Path(out).write_text(json.dumps({"scope": "FULL_REPLAY", "status": "BLOCKED",
                                        "expected": "CONFLICT_FAIL_CLOSED in both source orderings",
                                        "observed": observed}, indent=2) + "\n")
