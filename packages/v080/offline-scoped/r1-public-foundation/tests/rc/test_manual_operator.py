import shutil
import sqlite3
import json
from pathlib import Path

import pytest

from btc_quant_agent.platform.rc_fixture import DECISION, TRIGGER
from btc_quant_agent.platform.rc_fixture import fixture
from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.rc_source import canonical
from btc_quant_agent.platform.rc_operator import (
    ingest_synthetic_fixture, observe_episode, recover, review_once, status,
)
from btc_quant_agent.platform.rc_store import RCStore
from btc_quant_agent.platform.rc_source import admit_stream


def test_manual_ingest_review_observe_and_restart_recovery(tmp_path):
    output = tmp_path / "manual"
    ingested = ingest_synthetic_fixture(output, "SYNTHETIC_positive_v1.jsonl")
    assert ingested["input_receipts"] == 492
    assert ingested["exposure"] == "SYNTHETIC" and ingested["network_requests"] == 0
    reviewed = review_once(output, "BTCUSDT", TRIGGER, DECISION)
    assert reviewed["state"] == "ARMED" and reviewed["episode_id"]
    later = observe_episode(output, reviewed["episode_id"])
    assert later["outcome"] in {"TARGET_FIRST", "STOP_FIRST", "TIME_STOP",
                                 "NO_FILL", "MISSED_ENTRY", "AMBIGUOUS_OHLC_ORDER_UNKNOWN",
                                 "MISSING_COVERAGE", "RIGHT_CENSORED", "INSUFFICIENT_FUTURE_HORIZON"}
    current = status(output)
    assert current["source_freshness"]["native_status"] == "NATIVE_BLOCKED_AUTHORITY"
    assert current["b_shadow_states"][-1]["status"] in {"EXPIRED", "UNKNOWN"}
    assert recover(output)["mode"] == "SNAPSHOT_RECOVERED_FROM_VERIFIED_DURABLE_STORE"


def test_actual_cli_observations_respect_early_and_later_asof_cutoffs(tmp_path, monkeypatch, capsys):
    import hashlib

    from btc_quant_agent.platform import cli

    output = tmp_path / "cli-manual"
    monkeypatch.setattr(cli, "local_output", lambda _value: output)
    cli.main(["offline-rc", "ingest", "--fixture", "SYNTHETIC_positive_v1.jsonl"])
    cli.main(["offline-rc", "review", "--symbol", "BTCUSDT", "--trigger-ms", str(TRIGGER),
              "--decision-ms", str(DECISION)])
    capsys.readouterr()
    decision = RCStore(output / "state.sqlite").decisions()[0]
    cli.main(["offline-rc", "observe", "--episode-id", decision.episode_id,
              "--asof-ms", str(DECISION)])
    early = json.loads(capsys.readouterr().out)
    assert early["outcome"] == "INSUFFICIENT_FUTURE_HORIZON"
    assert RCStore(output / "state.sqlite").verify()["receipts"] == 492
    cli.main(["offline-rc", "observe", "--episode-id", decision.episode_id])
    later = json.loads(capsys.readouterr().out)
    assert later["outcome"] == "TARGET_FIRST"
    database = output / "state.sqlite"
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with pytest.raises(SystemExit):
        cli.main(["offline-rc", "observe", "--episode-id", decision.episode_id,
                  "--asof-ms", str(DECISION + 1)])
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    cli.main(["offline-rc", "recover"])
    assert "SNAPSHOT_RECOVERED_FROM_VERIFIED_DURABLE_STORE" in capsys.readouterr().out


def test_old_rc_v1_store_migrates_latest_terminal_lifecycle_without_rewriting_decisions(stored, positive, tmp_path):
    stored.transition(positive.episode_id, 0, "EXPIRED", DECISION + 1000, "TEST_V1_TERMINAL")
    old_store = tmp_path / "old.sqlite"
    shutil.copy2(stored.path, old_store)
    # Recreate an accepted RC V1-only store by removing only the new B sidecar tables.
    with sqlite3.connect(old_store) as db:
        db.execute("DROP TABLE b_shadow_states")
        db.execute("DROP TABLE b_schema_migrations")
    before = RCStore(old_store, readonly=True).decisions()
    with pytest.raises(ValueError, match="B_SHADOW_STATE_MIGRATION_REQUIRED"):
        RCStore(old_store, readonly=True).verify()
    migrated = RCStore(old_store)
    after = migrated.decisions()
    assert [d.model_dump(mode="json") for d in after] == [d.model_dump(mode="json") for d in before]
    states = migrated.b_states(positive.episode_id)
    assert len(states) == 1
    assert states[0]["status"] == "EXPIRED"
    assert states[0]["at_ms"] == DECISION + 1000
    assert states[0]["schema_version"] == "V070_B_SHADOW_STATE_V1"
    with pytest.raises(ValueError, match="B_SHADOW_STATE_TRANSITION_INVALID"):
        migrated.note_b_state("BTCUSDT", TRIGGER, "ARMED", at_ms=DECISION + 2000,
                              reason="CANNOT_REARM_TERMINAL")


def test_sidecar_correction_appends_v1_terminal_instead_of_rearming(stored, positive):
    stored.transition(positive.episode_id, 0, "EXPIRED", DECISION + 1000, "V1_EXPIRED")
    with sqlite3.connect(stored.path) as db:
        db.execute("DELETE FROM b_shadow_states WHERE state_id=? AND revision>0",
                   (positive.episode_id,))
        db.execute("DELETE FROM b_schema_migrations WHERE version=?",
                    ("V070_B_SHADOW_STATE_V1_RECONCILE_LATEST_RC_LIFECYCLE",))
    repaired = RCStore(stored.path)
    states = repaired.b_states(positive.episode_id)
    assert [x["status"] for x in states] == ["ARMED", "EXPIRED"]
    assert states[-1]["reason"] == "MIGRATED_LATEST_V1_TERMINAL_CORRECTION"


def test_source_blocked_and_unknown_are_persisted_versioned_states(stored, positive):
    stored.note_source_blocked("BTCUSDT", TRIGGER, at_ms=DECISION + 100)
    stored.note_b_state("BTCUSDT", TRIGGER, "UNKNOWN", at_ms=DECISION + 200,
                        reason="AMBIGUOUS_OHLC_ORDER_UNKNOWN")
    state = stored.b_states(positive.episode_id)
    assert [x["status"] for x in state] == ["ARMED", "SOURCE_BLOCKED", "UNKNOWN"]
    assert [x["revision"] for x in state] == [0, 1, 2]


@pytest.mark.parametrize("field", ["state_id", "decision_digest"])
def test_b_state_loader_rejects_self_rehashed_wrong_identity_or_decision(stored, positive, field):
    identity = positive.episode_id
    with sqlite3.connect(stored.path) as db:
        row = db.execute("SELECT value FROM b_shadow_states WHERE state_id=?", (identity,)).fetchone()
        value = json.loads(row[0])
        value[field] = "0" * 64
        db.execute("UPDATE b_shadow_states SET digest=?,value=? WHERE state_id=? AND revision=0",
                   (fingerprint(value), canonical(value), identity))
    with pytest.raises(ValueError, match="B_SHADOW_STATE_CHAIN_INVALID"):
        stored.b_states()


def test_b_state_loader_rejects_self_rehashed_regressing_clock(stored, positive):
    identity = positive.episode_id
    stored.note_source_blocked("BTCUSDT", TRIGGER, at_ms=DECISION + 200)
    stored.note_b_state("BTCUSDT", TRIGGER, "UNKNOWN", at_ms=DECISION + 300,
                        reason="UNKNOWN_AFTER_BLOCK")
    with sqlite3.connect(stored.path) as db:
        row = db.execute("SELECT value FROM b_shadow_states WHERE state_id=? AND revision=2",
                         (identity,)).fetchone()
        value = json.loads(row[0])
        value["at_ms"] = DECISION + 100
        db.execute("UPDATE b_shadow_states SET digest=?,value=? WHERE state_id=? AND revision=2",
                   (fingerprint(value), canonical(value), identity))
    with pytest.raises(ValueError, match="B_SHADOW_STATE_TRANSITION_OR_CLOCK_INVALID"):
        stored.b_states()


def test_watch_to_armed_transition_is_mirrored_without_unknown_state(tmp_path):
    rows = fixture(optional_hourly=False)
    store = RCStore(tmp_path / "watch.sqlite")
    admit_stream(store, rows)
    decision = store.compile("BTCUSDT", TRIGGER, DECISION)
    assert decision.market_state == "WATCH"
    store.commit(decision)
    store.transition(decision.episode_id, 0, "ARMED", DECISION + 1, "OPTIONAL_CONFIRMATION")
    assert [x["status"] for x in store.b_states(decision.episode_id)] == ["WATCH", "ARMED"]


def test_synthetic_ingest_rejects_symlinked_fixtures_parent_before_open(tmp_path, monkeypatch):
    from btc_quant_agent.platform import rc_operator

    project = tmp_path / "fake-project"
    module = project / "src/btc_quant_agent/platform/rc_operator.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    (project / "fixtures").symlink_to(Path(__file__).resolve().parents[2] / "fixtures",
                                      target_is_directory=True)
    monkeypatch.setattr(rc_operator, "__file__", str(module))
    with pytest.raises(ValueError, match="SYNTHETIC_FIXTURE_ROOT_INVALID"):
        rc_operator.ingest_synthetic_fixture(tmp_path / "output", "SYNTHETIC_positive_v1.jsonl")
