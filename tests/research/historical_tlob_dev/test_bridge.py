"""Artificial fixtures only. No authentic scope, archive, panel or historical outcome."""

import json
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from io import BytesIO
from itertools import pairwise

import pytest

from scripts.research.historical_tlob_dev import bridge as b


def altered(monkeypatch, scope, tape):
    """Explicit synthetic source replacement, with freshly declared synthetic hashes."""
    scope["source_sha256"] = b.digest(asdict(tape))
    scope["feature_sha256"] = b.digest([tape.features, tape.oi])
    monkeypatch.setattr(b, "synthetic_tape", lambda year, seed: tape)


@pytest.mark.parametrize("scope", [None, {}, {"schema": "exposed_dev_bridge.owner-scope.v2"},
                                   {"schema": b.SCOPE_SCHEMA, "data_kind": "EXPOSED_DEV"}])
def test_no_real_or_missing_scope_before_source_generation(monkeypatch, scope):
    _, policy = b.fixture()
    def forbidden(*args):
        raise AssertionError("Source generation/access must not happen")
    monkeypatch.setattr(b, "synthetic_tape", forbidden)
    with pytest.raises(ValueError, match="SCOPE_REQUIRED|REAL_ACCESS_DISABLED"):
        b.simulate(scope, policy)


def test_unattested_fixture_before_source_generation(monkeypatch):
    scope, policy = b.fixture()
    scope["fixture_attestation"] = None
    monkeypatch.setattr(b, "synthetic_tape", lambda *args: pytest.fail("source reached"))
    with pytest.raises(ValueError, match="UNATTESTED_FIXTURE"):
        b.simulate(scope, policy)


@pytest.mark.parametrize("year", [2021, 2022, 2023, 2024])
def test_historical_style_calendar_paired_population_and_selection(year):
    scope, policy = b.fixture(year)
    run = b.simulate(scope, policy)
    x, tlob = (run.result["arms"][a] for a in ("X", "TLOB"))
    assert x["eligible_origins"] == tlob["eligible_origins"]
    assert x["synthetic_trades"] and tlob["synthetic_trades"]
    assert {r["origin"] for r in run.mask if r["TLOB"]} <= {
        r["origin"] for r in run.mask if r["X"]}
    assert any(r["X"] and not r["TLOB"] for r in run.mask)
    assert run.result["data_kind"] == b.KIND and not run.result["outcome_authorized"]
    assert run.result["real_outcome_payload_reads"] == run.result["real_labels_materialized"] == 0
    assert not run.result["real_pnl_computed"]


@pytest.mark.parametrize("identity", ["symbol", "product", "oi_field", "oi_unit", "venue"])
def test_native_source_mapping_cannot_be_substituted(identity):
    scope, policy = b.fixture()
    scope["source_identity"][identity] = "NOT_AUTHORIZED"
    with pytest.raises(ValueError, match="SOURCE_MAPPING_MISMATCH"):
        b.simulate(scope, policy)


@pytest.mark.parametrize("field,reason", [("registration_sha256", "REGISTRATION_HASH_MISMATCH"),
    ("source_sha256", "SOURCE_HASH_MISMATCH"), ("feature_sha256", "FEATURE_HASH_MISMATCH")])
def test_exact_hash_mismatch_stops(field, reason):
    scope, policy = b.fixture()
    scope[field] = "0" * 64
    with pytest.raises(ValueError, match=reason):
        b.simulate(scope, policy)


def test_complete_archive_and_private_exclusions_before_source(monkeypatch):
    scope, policy = b.fixture()
    left = scope["archive_windows"][0][0]
    scope["exclusions"] = [[left + b.HOUR, left + 2 * b.HOUR]]
    monkeypatch.setattr(b, "synthetic_tape", lambda *args: pytest.fail("source reached"))
    with pytest.raises(ValueError, match="FULL_ARCHIVE_PROTECTED_OVERLAP"):
        b.simulate(scope, policy)


def test_private_attestation_completeness_and_coverage():
    scope, policy = b.fixture()
    del scope["private_partition_attestations"]["H41"]
    with pytest.raises(ValueError, match="PRIVATE_PARTITIONS_REQUIRED"):
        b.simulate(scope, policy)
    scope, _ = b.fixture()
    scope["private_partition_attestations"]["H41"]["date_exclusions"] = [[1, 2]]
    with pytest.raises(ValueError, match="PRIVATE_EXCLUSION_NOT_COVERED"):
        b.simulate(scope, policy)


def test_full_archive_window_cannot_be_silently_sliced():
    scope, policy = b.fixture()
    scope["archive_windows"][0][0] += 60
    with pytest.raises(ValueError, match="COMPLETE_ARCHIVE_WINDOW_REQUIRED"):
        b.simulate(scope, policy)


def test_complete_lookback_and_exit_windows_no_concatenation():
    scope, policy = b.fixture()
    start, end = scope["feature_windows"][0]
    scope["feature_windows"] = [[start, start + 20 * b.HOUR], [start + 21 * b.HOUR, end]]
    run = b.simulate(scope, policy)
    assert any(not r["eligible"] and r["reason"] == "FEATURE_WINDOW" for r in run.mask)
    scope, policy = b.fixture()
    scope["label_windows"] = [[start, start + 30 * b.HOUR]]
    run = b.simulate(scope, policy)
    assert any(r["reason"] == "EXIT_WINDOW" for r in run.mask)
    assert all(r["exit"] < start + 30 * b.HOUR for r in run.mask if r["eligible"])


@pytest.mark.parametrize("change", ["missing_oi", "late_oi", "late_x", "wrong_oi_clock"])
def test_missing_and_future_features_mask_both_arms(monkeypatch, change):
    scope, policy = b.fixture()
    tape = b.synthetic_tape(2021, 7)
    first = scope["origins"][0]
    label = first - 60 - 600
    if change == "missing_oi":
        tape = replace(tape, oi=tuple(s for s in tape.oi if s[0] != label))
    elif change in ("late_oi", "wrong_oi_clock"):
        values = []
        for s in tape.oi:
            values.append((s[0], s[1], first, s[3]) if s[0] == label and change == "late_oi"
                          else (s[0], s[1] + 1, s[2], s[3]) if s[0] == label else s)
        tape = replace(tape, oi=tuple(values))
    else:
        tape = replace(tape, features=tuple((*s[:4], first) if s[0] == first else s
                                           for s in tape.features))
    altered(monkeypatch, scope, tape)
    run = b.simulate(scope, policy)
    assert not run.mask[0]["eligible"]
    assert run.mask[0]["reason"] == "FEATURE_MISSING_OR_LATE"
    assert all(first not in run.result["arms"][arm]["eligible_origins"] for arm in ("X", "TLOB"))
    assert all(first not in run.result["arms"][arm]["valid_no_signal_origins"] for arm in ("X", "TLOB"))


def test_causal_delay_exact_time_exit_and_duplicate_origins():
    scope, policy = b.fixture()
    scope["origins"] += [scope["origins"][0]]
    run = b.simulate(scope, policy)
    assert run.result["duplicate_origins_removed"] == 1
    for arm in run.result["arms"].values():
        trades = arm["synthetic_trades"]
        assert len({r["origin"] for r in trades}) == len(trades)
        for r in trades:
            assert r["entry"] == r["origin"] + 60
            assert r["exit"] - r["entry"] == 4 * b.HOUR


@pytest.mark.parametrize("kind", ["entry", "exit"])
def test_missing_fill_is_ineligible_not_zero_return(monkeypatch, kind):
    scope, policy = b.fixture()
    original = b.simulate(scope, policy)
    trade = original.result["arms"]["X"]["synthetic_trades"][0]
    tape = original.tape
    tape = replace(tape, opens=tuple(p for p in tape.opens if p[0] != trade[kind]))
    altered(monkeypatch, scope, tape)
    run = b.simulate(scope, policy)
    row = next(r for r in run.mask if r["origin"] == trade["origin"])
    assert not row["eligible"] and row["reason"] == "MISSING_EXECUTION_PRICE"


def test_missing_funding_and_duplicate_funding_rejected(monkeypatch):
    scope, policy = b.fixture()
    tape = b.synthetic_tape(2021, 7)
    tape = replace(tape, settlements=())
    altered(monkeypatch, scope, tape)
    run = b.simulate(scope, policy)
    assert any(r["reason"] == "MISSING_FUNDING" for r in run.mask)
    tape = replace(tape, settlements=((tape.window[0], 0.0, 100.0),) * 2)
    altered(monkeypatch, scope, tape)
    with pytest.raises(ValueError, match="FUNDING_CHRONOLOGY_INVALID"):
        b.simulate(scope, policy)


@pytest.mark.parametrize("entry_order,exit_order", [("taker", "taker"), ("maker", "taker"),
                                                      ("maker", "maker")])
def test_fee_units_spread_slippage_funding_and_short_signs(monkeypatch, entry_order, exit_order):
    scope, policy = b.fixture()
    policy.update(entry_order=entry_order, exit_order=exit_order)
    run = b.simulate(scope, policy)
    trade = run.result["arms"]["X"]["synthetic_trades"][0]
    tape = replace(run.tape, opens=tuple((t, 100.0 if t == trade["entry"] else
                                         90.0 if t == trade["exit"] else v) for t, v in run.tape.opens))
    # A positive synthetic settlement inside the trade credits a short.
    settle = trade["entry"] + b.HOUR
    tape = replace(tape, settlements=((trade["entry"], -99.0, 100.0),
                                      (settle, 0.01, 100.0),
                                      (trade["exit"], -0.002, 100.0),
                                      (trade["exit"] + 1, 99.0, 100.0)),
                   funding_calendar=(trade["entry"], settle, trade["exit"], trade["exit"] + 1))
    altered(monkeypatch, scope, tape)
    r = b.simulate(scope, policy).result["arms"]["X"]["synthetic_trades"][0]
    c = r["artificial_accounting"]
    assert c["gross_return"] == pytest.approx(0.1)
    assert c["entry_fee"] == pytest.approx(policy["fee_bp"][entry_order] / 10000)
    assert c["exit_fee"] == pytest.approx(policy["fee_bp"][exit_order] / 10000 * 0.9)
    assert c["entry_spread"] == pytest.approx(0.0001)
    assert c["exit_slippage"] == pytest.approx(0.0002 * 0.9)
    assert c["funding_debit"] == pytest.approx(-0.008)
    assert c["net_return"] == pytest.approx(0.108 - c["total_cost"])
    assert r["initial_capital_return"] == pytest.approx(c["net_return"] * 0.4)


def test_native_maker_fill_uncertainty_is_preserved():
    out = b.Outcome(0, 4 * b.HOUR, 100, 90)
    assert b.economics(out, -1, 4, maker=True)["reason"] == "FILL_UNKNOWN"


@pytest.mark.parametrize("limit", ["concurrency", "capital"])
def test_overlap_and_capital_enforced_independently_per_arm(limit):
    scope, policy = b.fixture()
    if limit == "concurrency":
        policy.update(max_concurrent=1, capital_cap=1.0)
    else:
        policy.update(max_concurrent=10, capital_cap=0.4)
    run = b.simulate(scope, policy)
    x = run.result["arms"]["X"]
    assert x["capital_rejected_origins"]
    assert all(r["concurrent_after_entry"] == 1 for r in x["synthetic_trades"])
    trades = x["synthetic_trades"]
    assert all(a["exit"] <= c["entry"] for a, c in pairwise(trades))


@pytest.mark.parametrize("field,value", [("allocation", 2), ("capital_cap", 1.1),
    ("max_concurrent", 0), ("delay_s", 0), ("holding_h", None), ("spread_bp", float("nan"))])
def test_invalid_policy_rejected(field, value):
    scope, policy = b.fixture()
    policy[field] = value
    with pytest.raises(ValueError):
        b.simulate(scope, policy)


@pytest.mark.parametrize("mutate", ["scope", "policy", "mask", "result", "stage"])
def test_prepublication_revalidation_aborts_and_removes_stage(tmp_path, mutate):
    scope, policy = b.fixture()
    run = b.simulate(scope, policy)
    def tamper(path):
        if mutate == "scope":
            scope["seed"] += 1
        elif mutate == "policy":
            policy["fee_bp"]["taker"] += 1
        elif mutate == "mask":
            run.mask[0]["eligible"] = False
        elif mutate == "result":
            run.result["outcome_authorized"] = True
        else:
            path.write_bytes(b"tampered")
    out = tmp_path/"aborted"
    with pytest.raises(ValueError, match="CHANGED|MISMATCH"):
        b.publish(run, out, before_revalidation=tamper)
    assert not (out/"synthetic_panel.json").exists()
    assert not (out/".synthetic-panel.stage").exists()


def test_replay_freeze_and_atomic_exclusive_publication(tmp_path):
    scope, policy = b.fixture()
    run = b.simulate(scope, policy)
    replay = b.simulate(deepcopy(scope), deepcopy(policy))
    assert b.canonical(run.result) == b.canonical(replay.result)
    out = tmp_path/"run"
    b.publish(run, out)
    b.verify_publication(out, 2021, 7)
    assert json.loads((out/"synthetic_panel.json").read_bytes())["freeze"] == run.freeze
    with pytest.raises(ValueError, match="FRESH_OUTPUT_REQUIRED"):
        b.publish(run, out)
    (out/"synthetic_panel.json").write_text("{}")
    with pytest.raises(ValueError, match="SYNTHETIC_REPLAY_MISMATCH"):
        b.verify_publication(out, 2021, 7)


def test_output_symlink_collision_rejected(tmp_path):
    scope, policy = b.fixture()
    out = tmp_path/"existing"
    out.symlink_to(tmp_path/"missing")
    with pytest.raises(ValueError, match="FRESH_OUTPUT_REQUIRED"):
        b.publish(b.simulate(scope, policy), out)


def test_staged_symlink_rejected_without_reading_target(tmp_path):
    scope, policy = b.fixture()
    target = tmp_path/"unreadable-sentinel"
    target.write_text("This is a synthetic sentinel, not market data")
    def tamper(path):
        path.unlink()
        path.symlink_to(target)
    out = tmp_path/"no-symlink-publication"
    with pytest.raises(ValueError, match="UNSAFE_OR_MISSING_FILE"):
        b.publish(b.simulate(scope, policy), out, before_revalidation=tamper)
    assert not (out/"synthetic_panel.json").exists()
    assert not (out/".synthetic-panel.stage").exists()


def test_atomic_publication_never_replaces_competing_file(tmp_path):
    scope, policy = b.fixture()
    out = tmp_path/"competing"
    def competitor(path):
        (path.parent/"synthetic_panel.json").write_text("competing synthetic writer")
    with pytest.raises(FileExistsError):
        b.publish(b.simulate(scope, policy), out, before_revalidation=competitor)
    assert (out/"synthetic_panel.json").read_text() == "competing synthetic writer"
    assert not (out/".synthetic-panel.stage").exists()


def test_shared_implementation_hash_change_rejected(monkeypatch):
    scope, policy = b.fixture()
    run = b.simulate(scope, policy)
    original = b.published_file
    @contextmanager
    def replaced_code(path, limit):
        if str(path).endswith("strategy_eval/costs.py"):
            yield BytesIO(b"synthetic changed code sentinel")
        else:
            with original(path, limit) as stream:
                yield stream
    monkeypatch.setattr(b, "published_file", replaced_code)
    with pytest.raises(ValueError, match="FROZEN_INPUT_CHANGED"):
        run.verify()
