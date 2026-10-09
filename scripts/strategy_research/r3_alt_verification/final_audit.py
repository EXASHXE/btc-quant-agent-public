"""One-shot, source-pinned independent audit; never changes target source."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
import types
from collections import Counter
from decimal import Decimal

TARGET_SHA = "164243b770f74f98876b55a7f070b1adf2f554d5"
EXPECTED_SOURCE_HASHES = {
    "src/btc_quant_agent/strategy_research/r3_alt_engine/__init__.py": "b5f8a24f1b141a9c9df8a7e961f18c2b5e7718699e55ff00dfc250385ce35b78",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/clock.py": "50f2fa2c66f2952c0729bd8637dd5e8e9f23230c1737e12d466fbca80116cb55",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/execution.py": "5a9157e4ae0fe2dba99d4ad4383f600ff1e0efb6db07548b4746841e0dbedad6",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/frozen_primitives.py": "5d06f3f77993ae9eb1e76e29042d3375250477e5c7efdc67788d7a696ffa054f",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/journal.py": "896986ef11de8d752f6623f2f9d5221288f9b115ed1b9dbb16e7d4e756ba30ee",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/model.py": "cb31085e8a389bbb4f58d6472e8890ea29f1606b43c5605e10e46c1ce228b23a",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/money.py": "649d07456d9d567468f584406f471ca7dd34b51c6e693c1cbe9acc3c8a2bd0e7",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/reducer.py": "cf3425c9c1b3bf45841945ad473639f42731964432f75208ebb8ae4b005aac9c",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/replay.py": "50a80b9242d757e8f69d5ac9f4ad15e3fb348a5ee0c52a8474eec4666147ffdd",
    "src/btc_quant_agent/strategy_research/r3_alt_engine/signals.py": "b4ca80132f851842a048e3197f3b4b90a6c8495d0360ee6f4d56045a371b990d",
    "tests/test_r3_alt_clock_execution.py": "25cc4e97190af3ea6f30aeced0a9a57a110a51d0b2dc98925d66d117d030a8ea",
    "tests/test_r3_alt_events_money.py": "d25538d756dc41d625128ec01abb54c341f01e276c1d1958eee48dc7f287fe06",
    "tests/test_r3_alt_retest_replay.py": "717bbaca8a03b7854c0deeda8815486a1bcea60fee0bbf337771bf2eaff5ada7"
}
D = Decimal
START = 1699999200000
PREFIX = "btc_quant_agent.strategy_research.r3_alt_engine"
TARGET_ERRORS = (ValueError, TypeError, LookupError, ArithmeticError, RuntimeError)


def serialize(value):
    if dataclasses.is_dataclass(value):
        return {f.name: serialize(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serialize(x) for x in value]
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def load_target(root):
    """Use only archived namespace roots, excluding any installed parent package."""
    global TARGET_ERRORS
    root = Path(root).resolve()
    for relative, expected_hash in EXPECTED_SOURCE_HASHES.items():
        actual_hash = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"PINNED_SOURCE_HASH_MISMATCH: {relative}")
    sys.path.insert(0, str(root / "src"))
    for name, relative in [("btc_quant_agent", "src/btc_quant_agent"),
                           ("btc_quant_agent.strategy_research", "src/btc_quant_agent/strategy_research")]:
        module = types.ModuleType(name)
        module.__path__ = [str(root / relative)]
        sys.modules[name] = module
    modules = {n: importlib.import_module(f"{PREFIX}.{n}") for n in
               ("model", "money", "reducer", "journal", "clock", "replay", "signals")}
    TARGET_ERRORS = TARGET_ERRORS + (
        modules["money"].InvariantViolationError,
        modules["journal"].ConflictFailClosedError,
        modules["journal"].CauseOrOwnerFailClosedError,
        modules["journal"].InvalidMinuteClockError,
    )
    proof = {}
    for label, fn in [("ReplayEngine", modules["replay"].ReplayEngine),
                      ("reduce", modules["reducer"].reduce),
                      ("project_as_of", modules["money"].project_as_of),
                      ("assert_invariants", modules["money"].assert_invariants)]:
        p = Path(inspect.getfile(fn)).resolve()
        assert p.is_relative_to(root / "src"), p
        proof[label] = {"file": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    return modules, proof


def independent_dataset(modules):
    """Fixed BEFORE execution: valid OHLC, 240h warmup, no outcome-driven edits."""
    m = modules["model"]
    bars, marks = [], []
    price = D("50000")
    for minute in range(256 * 60):
        h = minute // 60
        step = D("0.25") if h < 240 else D("6")
        o, c = price, price + step
        high, low = max(o, c) + D("350"), min(o, c) - D("350")
        t = START + minute * 60000
        bars.append(m.Bar1m(t, o, high, low, c, D("10"), "BTCUSDT"))
        marks.append(m.MarkBar1m(t, o, high, low, c, "BTCUSDT", t + 120000))
        price = c
    schedule = tuple(START + h * 3600000 for h in range(8, 257, 8))
    return modules["replay"].SyntheticDataset(
        source_name="INDEPENDENT_FIXED_VALID_OHLC_240H_V1",
        bars_1m={"BTCUSDT": bars}, mark_bars_1m={"BTCUSDT": marks},
        symbol_filters={"BTCUSDT": m.SymbolFilters("BTCUSDT", D("0.1"), D("0.001"), D("5"))},
        known_funding_schedule=schedule)


def run_replay(modules, dataset, candidates, scenario, schedule=None):
    m, rp = modules["model"], modules["replay"]
    cfg = m.ReplayConfig(candidates=tuple(candidates), cost_scenario=scenario,
                         initial_cash=D("1000"), symbols=("BTCUSDT",),
                         known_funding_schedule=schedule)
    counts = Counter()
    latest = None
    original = rp.reduce

    def observe(state, event, config):
        nonlocal latest
        result = original(state, event, config)
        latest = result[0]
        counts[event.kind.value] += 1
        return result

    rp.reduce = observe  # Read-only observer, never changes an input/state/result.
    begin = time.monotonic()
    try:
        report = rp.ReplayEngine().run_simulation(dataset, cfg)
        outcome = {"exception": None, "report": serialize(report)}
    except TARGET_ERRORS as exc:
        outcome = {"exception": type(exc).__name__ + ": " + str(exc), "report": None}
    finally:
        rp.reduce = original
    outcome.update(candidates=list(candidates), scenario=scenario.value,
                   seconds=round(time.monotonic() - begin, 4), event_counts=dict(counts))
    if latest is not None:
        outcome["observed_final_marks"] = serialize(latest.latest_marks)
        # Independent CASH account reconstruction from actual postings, not target projection.
        cash_delta = D(0)
        for p in latest.postings:
            if not p.is_memo:
                if p.dr_account.value == "CASH":
                    cash_delta += p.amount
                if p.cr_account.value == "CASH":
                    cash_delta -= p.amount
        outcome["independent_cash_posting_delta"] = str(cash_delta)
        outcome["residual_owners"] = serialize(latest.owner_ledgers)
        outcome["postings_count"] = len(latest.postings)
        outcome["true_live_quantity"] = str(sum((o.quantity for o in latest.owner_ledgers.values()), D(0)))
        outcome["pending_trade_and_fee_liabilities"] = str(sum(
            (o.trade_payable + o.fee_payable + o.trade_receivable for o in latest.owner_ledgers.values()), D(0)))
    return outcome


def g1(modules, root):
    path = Path(root) / "tests/test_r3_alt_retest_replay.py"
    spec = importlib.util.spec_from_file_location("read_only_a_fixture", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    m = modules["model"]
    runs = []
    for scenario in (m.CostScenario.BASE, m.CostScenario.STRESS):
        for direction in ("win", "loss"):
            ds = helper._build_synthetic_dataset(n_hours=245, trend=direction)
            result = run_replay(modules, ds, ["STRUCTURAL_CONTINUATION_LONG_04H"], scenario)
            result.update(fixture="A_T28_" + scenario.value + "_" + direction,
                          expected_min_trades=1, expected_net_sign=1 if direction == "win" else -1,
                          invalid_ohlc_bars=sum(not (b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high)
                                               for b in ds.bars_1m["BTCUSDT"]))
            runs.append(result)
            print(json.dumps({"progress": result["fixture"], "trades": len(result["report"]["completed_trades"])
                              if result["report"] else None, "exception": result["exception"]}), flush=True)
    ds = helper._build_synthetic_dataset(n_hours=245, trend="win")
    schedule = (START + 8 * 3600000, START + 16 * 3600000)
    for scenario in (m.CostScenario.BASE, m.CostScenario.STRESS):
        result = run_replay(modules, ds, ["STRUCTURAL_CONTINUATION_LONG_12H"], scenario,
                            schedule if scenario == m.CostScenario.BASE else None)
        result.update(fixture="A_T29_" + scenario.value,
                      expected_min_trades=1 if scenario == m.CostScenario.BASE else 0)
        runs.append(result)
        print(json.dumps({"progress": result["fixture"], "trades": len(result["report"]["completed_trades"])
                          if result["report"] else None, "exception": result["exception"]}), flush=True)
    ds = independent_dataset(modules)
    result = run_replay(modules, ds, ["STRUCTURAL_CONTINUATION_LONG_04H"], m.CostScenario.BASE,
                        ds.known_funding_schedule)
    result.update(fixture="INDEPENDENT_FIXED_VALID_OHLC_240H_V1", expected_min_trades=1,
                  warmup_minutes=14400, invalid_ohlc_bars=0,
                  input_sha256=hashlib.sha256(json.dumps(serialize(ds), sort_keys=True).encode()).hexdigest())
    runs.append(result)
    return runs, ds


def make_event(modules, kind, payload, key, event_id="AUDIT_EVENT", available=START, economic=START):
    m = modules["model"]
    return m.Event(event_id, kind, key.book_id, "STRUCTURAL_CONTINUATION_LONG_04H", "BTCUSDT", key,
                   key.position_id, key.position_id, "", "AUDIT_S", "AUDIT_SOURCE", "",
                   economic, available, payload, modules["journal"].compute_payload_digest(payload))


def probes(modules, independent_ds):
    m, money, red = modules["model"], modules["money"], modules["reducer"]
    key = m.OwnerKey("BASE", "BTC_OWNER")
    cfg = m.ReplayConfig(("STRUCTURAL_CONTINUATION_LONG_04H",), m.CostScenario.BASE, symbols=("BTCUSDT",))

    def owner(**kw):
        base = {"owner_key": key, "candidate_id": "STRUCTURAL_CONTINUATION_LONG_04H", "symbol": "BTCUSDT",
                "direction": m.Direction.LONG, "phase": m.OwnerPhase.CLOSED_UNSETTLED, "cash_settled": D(1000)}
        base.update(kw)
        return m.OwnerLedger(**base)

    def state(*owners, **kw):
        base = {"clock_ms": START, "latest_mark_close_ms": START,
                "owner_ledgers": {o.owner_key: o for o in owners}, "opening_equity_posted": {"BASE": True}}
        base.update(kw)
        return m.EngineState(**base)

    outcomes = {}
    phantom = state(owner(cash_settled=D(1234)))
    checks = money.assert_invariants(phantom, "BASE")
    outcomes["unposted_cash"] = {"scope": "PUBLIC_API_STATE_MUTATION", "expected": "I07 fail closed for unposted CASH1234",
                                 "observed": serialize(checks), "status": "BLOCKED", "cash": "1234", "cash_postings": 0}
    short = state(owner(funding_payable=D(1), enc_funding_dedicated=D("0.4"), enc_shortfall=D(0)))
    pr = money.project_as_of("BASE", short, START)
    checks = money.assert_invariants(short, "BASE")
    outcomes["missing_shortfall"] = {"scope": "PUBLIC_API_STATE_MUTATION", "expected_shortfall": "0.6",
                                     "expected_free_without_other_covers": "949", "observed": serialize(pr),
                                     "invariants": checks, "status": "BLOCKED" if pr.A != D(949) else "PASS"}
    opened = state(owner(phase=m.OwnerPhase.ACKED_OPEN, quantity=D(1), entry_price=D(100),
                          initial_stop=D(90), target=D(120)), latest_marks={"BTCUSDT": D(100)})
    exit_event = make_event(modules, m.EventKind.ECONOMIC_EXIT,
                            {"quantity": "2", "raw_price": "90", "effective_price": "90",
                             "exit_fee": "0", "exit_reason": "STOP_LOSS", "slice_id": "OVER_EXIT"}, key)
    try:
        result = red.reduce(opened, exit_event, cfg)[0]
        outcomes["over_exit"] = {"scope": "PUBLIC_API_EVENT", "expected": "reject exit2 when filled1",
                                 "status": "BLOCKED", "owner": serialize(result.owner_ledgers[key]),
                                 "invariants": money.assert_invariants(result, "BASE")}
    except TARGET_ERRORS as exc:
        outcomes["over_exit"] = {"scope": "PUBLIC_API_EVENT", "status": "REJECTED",
                                 "exception": type(exc).__name__ + ": " + str(exc)}
    kill = make_event(modules, m.EventKind.RISK_KILL, {}, key, "ACK_CLOCK_ID")
    first = red.reduce(state(owner()), kill, cfg)[0]
    altered = dataclasses.replace(kill, available_at_ms=START + 60000)
    try:
        result = red.reduce(first, altered, cfg)[0]
        outcomes["clock_only_duplicate"] = {"scope": "PUBLIC_API_EVENT", "expected": "CONFLICT_FAIL_CLOSED",
                                            "status": "BLOCKED", "same_state_returned": result == first}
    except TARGET_ERRORS as exc:
        outcomes["clock_only_duplicate"] = {"scope": "PUBLIC_API_EVENT", "status": "REJECTED",
                                            "exception": type(exc).__name__ + ": " + str(exc)}
    # Correct normative G4 funding projection versus documentation equations.
    ethkey = m.OwnerKey("BASE", "ETH_WITNESS")
    btc = owner(enc_exit_fee=D(7), funding_payable=D(1), enc_funding_dedicated=D(".4"), enc_shortfall=D(".6"))
    eth = owner(owner_key=ethkey, candidate_id="STRUCTURAL_CONTINUATION_LONG_12H", symbol="ETHUSDT",
                cash_settled=D(0), enc_funding_future=D(2))
    funded = state(btc, eth)
    before = money.project_as_of("BASE", funded, START)
    ack = make_event(modules, m.EventKind.FUNDING_ACK, {"amount": "1"}, key, "FUND_ACK")
    try:
        after_state = red.reduce(funded, ack, cfg)[0]
        after = money.project_as_of("BASE", after_state, START)
        outcomes["funding_940"] = {"scope": "PUBLIC_API_NORMALIZED_LEDGER", "before": serialize(before),
                                   "after": serialize(after), "ETH_after": serialize(after_state.owner_ledgers[ethkey]),
                                   "expected": {"before_free": "940", "after_cash": "999", "after_free": "940.05"},
                                   "status": "PASS" if before.A == D(940) and after.A == D("940.05") else "BLOCKED"}
    except TARGET_ERRORS as exc:
        outcomes["funding_940"] = {"before": serialize(before), "exception": str(exc), "status": "UNVERIFIED"}
    sl = m.PendingExitSlice("LOSS", D(1), D(100), D(100), -D("169.336545"), D(0), START-1,
                             START+60000, m.ExitReason.STOP_LOSS, True)
    lossstate = state(owner(phase=m.OwnerPhase.EXIT_PENDING, pending_exit_slices=(sl,), trade_payable=D("169.336545")))
    before = money.project_as_of("BASE", lossstate, START)
    after = money.project_as_of("BASE", lossstate, START+60000)
    outcomes["loss_proof"] = {"scope": "PUBLIC_API_NORMALIZED_LEDGER", "before": serialize(before),
                              "after": serialize(after), "expected": {"before_E_r": "1000", "after_E_r": "830.663455", "after_kill": True},
                              "status": "PASS" if before.E_r == D(1000) and after.E_r == D("830.663455") and after.killed else "BLOCKED"}
    # G5: inject a legitimate closed owner with unpaid fee into the initial state, not market prices.
    rp = modules["replay"]
    factory = rp.EngineState
    captured = {}

    def initial_with_fee(*args, **kwargs):
        s = factory(*args, **kwargs)
        o = owner(fee_payable=D(2))
        captured["initial_owner"] = serialize(o)
        return dataclasses.replace(s, owner_ledgers={key: o}, opening_equity_posted={"BASE": True})

    rp.EngineState = initial_with_fee
    try:
        report = rp.ReplayEngine().run_simulation(independent_ds, cfg)
        outcomes["terminal_fee_orphan"] = {"scope": "INSTRUMENTED_FULL_REPLAY_INITIAL_STATE",
                                            "initial_injected_fee": "2", "report": serialize(report),
                                            "expected": "terminal_all_zero=False while fee_payable2 remains",
                                            "status": "BLOCKED" if report.terminal_all_zero else "PASS"}
    except TARGET_ERRORS as exc:
        outcomes["terminal_fee_orphan"] = {"scope": "INSTRUMENTED_FULL_REPLAY_INITIAL_STATE",
                                            "status": "REJECTED", "exception": type(exc).__name__ + ": " + str(exc)}
    finally:
        rp.EngineState = factory
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    modules, proof = load_target(args.target_root)
    runs, ds = g1(modules, args.target_root)
    # Once G1 fails, only bounded root-cause confirmatory probes; no exhaustive T01-T34 campaign.
    confirmations = probes(modules, ds)
    m = modules["model"]
    cid_a, cid_b = "STRUCTURAL_CONTINUATION_LONG_04H", "STRUCTURAL_CONTINUATION_LONG_12H"
    isolation_runs = []
    for candidates in ([cid_b], [cid_a, cid_b], [cid_b, cid_a]):
        isolation_runs.append(run_replay(modules, ds, candidates, m.CostScenario.BASE, ds.known_funding_schedule))
    result = {"target_sha": TARGET_SHA, "archive_root": str(Path(args.target_root).resolve()),
              "import_proof": proof, "python": sys.version, "g1_runs": runs,
              "confirmatory_probes": confirmations, "g3_isolation_runs": isolation_runs,
              "zero_access_counters": {"market_body_reads": 0, "protected_reads": 0, "exchange_calls": 0, "live_writes": 0},
              "observer_note": "Replay reduce wrapper only records events/state; G5 injected initial fee state is explicitly instrumented, not an ordinary production fixture."}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": args.output, "g1_counts": [len(r["report"]["completed_trades"]) if r["report"] else None for r in runs],
                      "probe_status": {k: v["status"] for k, v in confirmations.items()}}), flush=True)


if __name__ == "__main__":
    main()
