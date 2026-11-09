from __future__ import annotations
import json
import hashlib
from pathlib import Path

import pytest

from btc_quant_agent.platform.mvp import fixtures
from btc_quant_agent.platform.mvp.models import Dataset, Reference, Decision, IMPORTED
from btc_quant_agent.platform.mvp.source import Source, normalize
from btc_quant_agent.platform.mvp.product import Product
from btc_quant_agent.platform.mvp.demo import run, followup
from btc_quant_agent.platform.mvp.cli import read_dataset, main
from btc_quant_agent.platform.native.clock import Clock
from btc_quant_agent.platform.rc_fixture import TRIGGER


@pytest.fixture
def warm(tmp_path):
    source = Source(tmp_path / "mvp", create=True, synthetic=True)
    data = fixtures.dataset()
    source.ingest(data)
    source.tick(TRIGGER + 120000)
    return source


def test_real_callable_positive_NO_SETUP_and_economic_chain(warm):
    p = Product(warm)
    decisions = [p.review(s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    assert [d.market_state for d in decisions] == ["ARMED", "NO_SETUP", "NO_SETUP"]
    for d in decisions:
        assert (
            d.mode == "EXPLORATORY_MVP"
            and not d.source_qualified
            and d.account == "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
        )
    output = p.dashboard()
    page = Path(output["dashboard"]).read_text()
    assert "EXPLORATORY_MVP" in page and "Hypothetical after-cost R" in page and "Source provenance" in page
    result = p.evaluate(warm.directory / "economics")
    assert result["scientific_decision"] == "INSUFFICIENT_SUPPORT"
    assert (
        json.loads((warm.directory / "economics/summary.json").read_text())["denominators"][
            "actually_actionable_at_review"
        ]
        == 0
    )


def test_recover_cli_rebuilds_snapshot_from_persisted_plan(warm, capsys):
    decision = Product(warm).review("BTCUSDT")
    assert main(["recover", "--output", str(warm.directory)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["recovered"] == [] and Path(result["dashboard"]).is_file()
    assert Product(Source(warm.directory)).decisions()[0] == decision


def test_all_NO_SETUP_is_complete_product(tmp_path):
    result = run(tmp_path / "flat", "all-no-setup")
    assert result["states"] == ["NO_SETUP"] * 3
    assert result["evaluation"]["scientific_decision"] == "INSUFFICIENT_SUPPORT"
    assert Path(result["dashboard"]).is_file()


def test_1760ms_jump_holds_then_independent_reconciliation_resumes(warm):
    warm.tick(TRIGGER + 120000, 1760)
    before = warm.assess()
    assert before["status"] == "MVP_DATA_NOT_READY" and before["clock"] == "CLOCK_DEGRADED_HOLD"
    assert not Product(warm).decisions()
    witness = fixtures.dataset(source_ms=TRIGGER + 120000, origin="INDEPENDENT_TEST_REPLAY")
    warm.reconcile(witness)
    decision = Product(warm).review("BTCUSDT")
    assert decision.market_state == "ARMED"
    assert decision.clock_condition == "CLOCK_DEGRADED_RECONCILED" and not decision.source_qualified
    # Strict sticky behavior has not been reconfigured or reset by MVP.
    strict = Clock()
    samples = iter(
        [
            {"wall_ms": 1000, "mono_before_ms": 1000, "mono_after_ms": 1000},
            {"wall_ms": 3760, "mono_before_ms": 2000, "mono_after_ms": 2000},
            {"wall_ms": 3000, "mono_before_ms": 3000, "mono_after_ms": 3000},
        ]
    )
    strict.pair = lambda: next(samples)
    strict.sample()
    with pytest.raises(ValueError, match="50MS"):
        strict.sample()
    with pytest.raises(ValueError, match="50MS"):
        strict.sample()


def test_same_origin_or_different_market_snapshot_cannot_clear_hold(warm):
    warm.tick(TRIGGER + 120000, 1760)
    warm.assess()
    with pytest.raises(ValueError, match="INDEPENDENT_SNAPSHOT"):
        warm.reconcile(fixtures.dataset(source_ms=TRIGGER + 120000))
    with pytest.raises(ValueError, match="DISAGREEMENT"):
        warm.reconcile(fixtures.dataset("flat", source_ms=TRIGGER + 120000, origin="SECOND"))
    assert warm.assess()["clock"] == "CLOCK_DEGRADED_HOLD"


def test_irreconcilable_timestamp_stays_quarantined(tmp_path):
    s = Source(tmp_path / "bad", create=True, synthetic=True)
    with pytest.raises(ValueError, match="UNRECONCILABLE_SOURCE_EVENT"):
        s.ingest(fixtures.dataset("irreconcilable"))
    assert not s.imports() and s.assess()["status"] == "MVP_DATA_NOT_READY"
    with pytest.raises(ValueError):
        s.reconcile(fixtures.dataset(origin="SECOND"))


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("x", False, "FINAL"),
        ("s", "ETHUSDT", "MISMATCH"),
        ("i", "1h", "MISMATCH"),
        ("T", TRIGGER, "NATIVE_BAR_ALIGNMENT_INVALID"),
        ("h", "0", "greater_than"),
    ],
)
def test_existing_completed_kline_parser_remains_boundary(field, value, reason):
    d = fixtures.dataset()
    r = d.rows[-1]
    value_row = r.model_dump(mode="json")
    value_row["raw_kline"]["data"]["k"][field] = value
    from btc_quant_agent.platform.mvp.models import Row

    with pytest.raises(ValueError, match=reason):
        normalize(d, Row.model_validate(value_row))


@pytest.mark.parametrize("value", [True, float("nan"), -1.0])
def test_archive_OHLCV_cannot_bypass_wire_validation(value):
    d = fixtures.dataset()
    row = d.rows[-1].model_dump(mode="json")
    row.update(kind="COMPLETED_DATASET", raw_kline=None)
    row["candle"]["volume"] = value
    from btc_quant_agent.platform.mvp.models import Row

    with pytest.raises(ValueError):
        normalize(d, Row.model_validate(row))


def test_future_data_and_fake_synthetic_label_rejected(warm):
    d = fixtures.dataset().model_dump(mode="json")
    d["rows"][-1]["candle"]["close"] += 1
    with pytest.raises(ValueError, match="NO_NATIVE_RELABEL"):
        warm.ingest(Dataset.model_validate(d))
    d = fixtures.dataset()
    r = d.rows[-1].model_copy(update={"original_source_event_ms": d.reference.upper_ms + 1})
    with pytest.raises(ValueError, match="SOURCE_EVENT"):
        normalize(d, r)


@pytest.mark.parametrize("grace", [59000, 301000])
def test_grace_outside_contract_rejected(tmp_path, grace):
    with pytest.raises(ValueError, match="60_TO_300"):
        Source(tmp_path / "m", create=True, synthetic=True, grace_ms=grace)


def test_grace_must_elapse_and_late_reference_is_not_fresh(warm):
    warm.tick(TRIGGER + 59000)
    assert "GRACE" in warm.assess()["reason"]
    warm.tick(TRIGGER + 600000)
    assert "STALE" in warm.assess()["reason"]


@pytest.mark.parametrize("hours", [4, 24, 48])
def test_only_requested_short_horizons(warm, hours):
    d = Product(warm).review("BTCUSDT", hours)
    assert d.opportunity.holding_hours == hours


@pytest.mark.parametrize("hours", [3, 49, True])
def test_out_of_scope_horizon_rejected(warm, hours):
    with pytest.raises(ValueError, match="4_TO_48"):
        Product(warm).review("BTCUSDT", hours)


def test_actual_import_has_no_fabricated_permission_or_clock_override(tmp_path):
    s = Source(tmp_path / "real", create=True)
    data = fixtures.dataset().model_copy(update={"evidence_class": IMPORTED, "fixture_id": None})
    with pytest.raises(ValueError, match="PERMISSION_ABSENT"):
        s.ingest(data)
    with pytest.raises(ValueError, match="OVERRIDE_FORBIDDEN"):
        s.tick(TRIGGER)
    assert s.assess()["status"] == "MVP_DATA_NOT_READY" and not s.imports()


def test_reference_uncertainty_and_boot_domain_are_bounded(warm):
    with pytest.raises(ValueError, match="UNCERTAINTY"):
        Reference(lower_ms=1000, upper_ms=6001, received_mono_ms=1000, boot_id="x", provenance="test")
    reference = fixtures.dataset().reference.model_copy(update={"boot_id": "another"})
    with pytest.raises(ValueError, match="BOOT"):
        reference.project(warm.sample())


def test_shadow_append_only_restart_and_C_preserves_producer_distinction(warm):
    p = Product(warm)
    original = p.review("BTCUSDT").model_dump(mode="json")
    later = followup(warm)
    assert later["restart_original_plan_unchanged"] and later["observation"]["actual_fill"] is False
    assert later["episode"]["state"]["status"] == "CANCELED"
    assert Product(Source(warm.directory)).decisions()[0].model_dump(mode="json") == original
    export = json.loads((warm.directory / "evaluation_later/H_episode_export.json").read_text())
    assert export["episodes"][0]["producer_outcome"] == "TARGET_FIRST"
    assert export["episodes"][0]["path"] == [] and not export["episodes"][0]["reviewed_ms"]


def test_frozen_decision_horizon_and_replay_are_immutable(warm):
    p = Product(warm)
    first = p.review("BTCUSDT")
    second = p.review("BTCUSDT")
    assert first == second and len(p.decisions()) == 1
    with pytest.raises(ValueError, match="IMMUTABLE"):
        p.review("BTCUSDT", 48)
    raw = first.model_dump(mode="json")
    raw["admitted_prefix"][0]["original"]["revision"] = 1
    with pytest.raises(ValueError, match="PREFIX_TAMPER"):
        Decision.model_validate_json(json.dumps(raw))


def test_protected_path_and_symlink_read_rejected(tmp_path):
    protected = tmp_path / "FINAL_HOLDOUT"
    protected.write_text("DO NOT READ")
    with pytest.raises(ValueError, match="PROTECTED"):
        read_dataset(protected)
    link = tmp_path / "data.json"
    link.symlink_to(protected)
    with pytest.raises(ValueError, match="PROTECTED|UNTRUSTED"):
        read_dataset(link)


def test_mode_and_strict_implementations_preserved():
    root = Path(__file__).resolve().parents[2]
    expected = json.loads((root / "deployment/accepted_application_manifest.json").read_text())["files"]
    prefixes = (
        "src/btc_quant_agent/platform/native/",
        "src/btc_quant_agent/platform/qualification/",
        "src/program_c/",
    )
    names = {
        "src/btc_quant_agent/platform/rc_strategy.py",
        "src/btc_quant_agent/platform/rc_observe.py",
        "src/btc_quant_agent/platform/qualified_source.py",
        "src/btc_quant_agent/platform/swing.py",
        "src/btc_quant_agent/platform/rc_models.py",
    }
    for row in expected:
        if row["path"] == "src/btc_quant_agent/platform/rc_strategy.py":
            from approved_compiler_delta import assert_original_s1_ast
            assert_original_s1_ast(root)
        elif row["path"].startswith(prefixes) or row["path"] in names:
            assert hashlib.sha256((root / row["path"]).read_bytes()).hexdigest() == row["sha256"], row["path"]


@pytest.mark.parametrize("kind", ["no-warmup", "gap"])
def test_missing_mandatory_warmup_and_gaps_never_generate_candidate(tmp_path, kind):
    s = Source(tmp_path / kind, create=True, synthetic=True)
    s.ingest(fixtures.dataset(kind))
    s.tick(TRIGGER + 120000)
    result = Product(s).review("BTCUSDT")
    assert result["status"] == "MVP_DATA_NOT_READY"
    assert "WARMUP_OR_COMPLETENESS" in result["reason"]
    assert not Product(s).decisions()


def test_wrong_mode_store_is_not_mutated(tmp_path):
    import sqlite3

    directory = tmp_path / "foreign"
    directory.mkdir()
    database = directory / "mvp.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE strict_state(value TEXT)")
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="MODE_MISMATCH"):
        Source(directory)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_original_workspace_output_rejected_before_creation(tmp_path):
    output = tmp_path / "lt-program-f-unified-protected" / "new"
    with pytest.raises(ValueError, match="PROTECTED_OUTPUT"):
        Source(output, create=True)
    assert not output.exists()


def test_interrupted_dataset_import_recovers_without_rewriting_data(tmp_path):
    from btc_quant_agent.platform.native.contract import digest

    s = Source(tmp_path / "partial", create=True, synthetic=True)
    data = fixtures.dataset()
    identity = digest(data.model_dump(mode="json"))
    s.events.append(
        "DATASET",
        {
            "dataset_id": identity,
            "dataset": data.model_dump(mode="json"),
            "permissions": None,
            "quarantined": False,
        },
    )
    result = s.ingest(data)
    assert result["status"] == "RECOVERED_IMPORT_WITH_NEW_DURABILITY_STAMP"
    assert len(s.datasets()) == len(s.imports()) == 1
    s.tick(TRIGGER + 120000)
    assert Product(s).review("BTCUSDT").market_state == "ARMED"


def test_archive_must_explicitly_identify_completed_candle():
    from btc_quant_agent.platform.mvp.models import Row

    d = fixtures.dataset()
    row = d.rows[-1].model_dump(mode="json")
    row.update(kind="COMPLETED_DATASET", raw_kline=None)
    row["candle"].pop("closed")
    with pytest.raises(ValueError, match="EXPLICIT_COMPLETED"):
        normalize(d, Row.model_validate(row))
