"""Real archive reader/dual gate exercised exclusively on synthetic ZIPs."""

import copy
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.exposed_dev_bridge import archive_adapter as adapter
from scripts.research.exposed_dev_bridge import authorization as auth
from scripts.research.exposed_dev_bridge import inspection
from scripts.research.exposed_dev_bridge import pipeline as cli
from scripts.research.strategy_eval import HORIZONS
from scripts.research.strategy_eval import pipeline as p1
from scripts.research.strategy_eval.costs import BASELINE, STRESS, Outcome, economics

from .conftest import archive, publish

START = n.quarter_window("Q3")[0]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(scope, doc, allowlist, panel_sha="0" * 64):
    entry = {"path": doc["p1_binding"]["panel_path"], "sha256": panel_sha,
             "start_utc_s": START, "end_utc_s": START + 3 * 86400}
    allowlist.write_bytes(n.canonical_bytes({"schema": "strategy_eval.exposed-dev.v1",
        "exposure": "EXPOSED_DEV", "fixture_reference": "SYNTHETIC_ZIP_UNIT_TEST_ONLY", "panels": [entry]}))
    doc["p1_binding"].update(panel_sha256=panel_sha, allowlist_sha256=sha(allowlist))
    scope.write_bytes(n.canonical_bytes(doc))


@pytest.fixture
def zip_scope(tmp_path):
    roots = {v: tmp_path / v for v in ("binance", "okx")}
    times = list(range(START * n.US, (START + 3 * 86400) * n.US, 60 * n.US))
    records = {"binance": [archive(roots["binance"], "binance", f, times=times)
                for f in ("klines", "spot_klines", "markPriceKlines")], "okx": []}
    for day in range(3):
        records["binance"].append(archive(roots["binance"], "binance", "metrics", period=f"2026-07-{day + 1:02d}",
            times=list(range((START + day * 86400) * n.US, (START + (day + 1) * 86400) * n.US, 300 * n.US))))
    records["binance"].append(archive(roots["binance"], "binance", "fundingRate",
        times=list(range(START * n.US, (START + 3 * 86400) * n.US, 28800 * n.US))))
    for family in ("candlesticks", "spot_candlesticks", "funding_rates"):
        left = (START + 16 * 3600) * n.US
        step = (28800 if family == "funding_rates" else 60) * n.US
        record = archive(roots["okx"], "okx", family, period="2026-07-02",
                         times=list(range(left, left + 86400 * n.US, step)))
        if family == "funding_rates":
            record["gaps"] = 3  # aggregate report is not a BTC calendar
        records["okx"].append(record)
    plans = []
    for venue, root in roots.items():
        publish(root, venue, records[venue])
        plans.append({"quarter": "Q3", "venue": venue, "root": str(root),
            "manifest_sha256": sha(root / "manifest.json"), "qc_sha256": sha(root / "qc.json"),
            "files": [{"path": r["local_path"], "family": r["family"], "symbol": r["symbol"],
                "market": r["market"], "sha256": r["local_sha256"],
                "start_utc": n.iso_us(n.file_window(r, venue)[0]),
                "end_utc": n.iso_us(n.file_window(r, venue)[1])} for r in records[venue]]})
    scope, allowlist = tmp_path / "fixture-owner.json", tmp_path / "fixture-p1.json"
    output = tmp_path / "output"
    doc = {"schema": "exposed_dev_bridge.owner-scope.v2", "exposure": "EXPOSED_DEV",
        "fixture_reference": "SYNTHETIC_ZIP_UNIT_TEST_ONLY",
        "authorization": {"role": "Owner", "decision": "AUTHORIZE_EXPOSED_DEV", "owner": "SYNTHETIC_FIXTURE",
            "reference": "UNIT_TEST_ONLY_NOT_REAL_AUTHORITY", "issued_at_utc": "2026-01-01T00:00:00Z"},
        "archive_ranges": [{"start_utc": "2026-07-01T00:00:00Z", "end_utc": "2026-08-01T00:00:00Z"}],
        "origin_ranges": [{"start_utc": "2026-07-01T00:00:00Z", "end_utc": "2026-07-04T00:00:00Z"}],
        "governance": {"protected_dates_complete": True, "holdout_status": "OWNER_CONFIRMED",
            "protected_date_exclusions": [{"kind": "PROTECTED", "start_utc": "2026-09-01T00:00:00Z",
                                            "end_utc": "2026-10-01T00:00:00Z"}],
            "private_partition_attestations": {name: {"status": "OWNER_CONFIRMED", "reference": "TEST_ONLY",
                "date_exclusions": []} for name in auth.PRIVATE_PARTITIONS}},
        "sources": plans, "p1_binding": {"allowlist_path": str(allowlist),
            "panel_path": str(output / "normalized_panel.json"), "start_utc_s": START,
            "end_utc_s": START + 3 * 86400}}
    bind(scope, doc, allowlist)
    return scope, doc, allowlist, output, roots, records


def permit_for(fixture):
    scope, _, allowlist, output, _, _ = fixture
    return auth.authorize_dual_gate(scope, allowlist, output / "normalized_panel.json")


def republish(fixture):
    scope, doc, allowlist, _, roots, records = fixture
    for plan in doc["sources"]:
        venue, root = plan["venue"], roots[plan["venue"]]
        publish(root, venue, records[venue])
        plan.update(manifest_sha256=sha(root / "manifest.json"), qc_sha256=sha(root / "qc.json"))
        plan["files"] = [{"path": r["local_path"], "family": r["family"], "symbol": r["symbol"],
            "market": r["market"], "sha256": r["local_sha256"],
            "start_utc": n.iso_us(n.file_window(r, venue)[0]),
            "end_utc": n.iso_us(n.file_window(r, venue)[1])} for r in records[venue]]
    bind(scope, doc, allowlist)


@pytest.mark.parametrize("evaluate", [False, True])
def test_real_style_zip_to_actual_p1_parser_and_economics(zip_scope, evaluate):
    scope, doc, allowlist, output, _, _ = zip_scope
    ledger = {}
    rows = list(adapter.panel_rows(permit_for(zip_scope), ledger))
    assert len(rows) == 72 and all(r["action"] == "NO_ACTION" for r in rows)
    assert [r["t"] for r in rows] == [START + 60 + i * 3600 for i in range(72)]
    assert all(v <= 3000 for v in ledger["max_retained_rows_by_channel"].values())
    assert ledger["scan_budget"]["reserved_expanded"] < 8 * 1024**2
    assert ledger["scan_budget"]["reserved_objects"] == 10
    row = rows[30]
    assert row["native_feature_ready"] is True
    for h in HORIZONS:
        value = Outcome.from_dict(row["outcomes"][str(h)])
        assert value.entry_t == row["t"] + 60 and value.exit_t == value.entry_t + h * 3600
        assert value.entry_price == value.exit_price == 100
        assert all(value.entry_t * n.US < s.t_us <= value.exit_t * n.US for s in value.settlements)
        for scenario in (BASELINE, STRESS):
            long, short = economics(value, 1, h, scenario), economics(value, -1, h, scenario)
            assert long["status"] == short["status"] == "RESOLVED"
            assert long["funding_debit"] == -short["funding_debit"]
            assert long["total_cost"] == pytest.approx(scenario.nominal_round_trip_bp / 10000)
    refs = row["source_references"]["perp"].values()
    by_id = {s["source_id"]: s for s in ledger["sources"]}
    assert all(by_id[r["source_id"]]["original_record"]["market"] == "futures_um" for r in refs)
    assert all(by_id[r["source_id"]]["source_path"].endswith(".zip") for r in refs)
    assert all(len(by_id[r["source_id"]]["actual_raw_sha256"]) == 64 for r in refs)
    assert all(r["native_time_unit"] == "ms" and r["event_utc_us"] == r["native_sample"] * 1000 for r in refs)
    assert ledger["receiver_pit"] == "PIT_UNKNOWN"
    okx = [s for s in ledger["sources"] if s["original_record"]["family"] == "funding_rates"][0]
    assert okx["original_record"]["gaps"] == 3
    assert okx["scan"]["retained_btc_eth_settlements"] == 3
    assert ledger["future_okx_not_used_for_binance_labels"] is True
    # Expected bytes are derived only from this synthetic ZIP fixture; no real
    # source outcome is used to create or modify an Owner scope in this task.
    raw = (b'{"exposure":"EXPOSED_DEV","label":"HISTORICAL_OFFLINE / PIT_UNKNOWN","rows":['
        + b','.join(n.canonical_bytes(r).rstrip(b'\n') for r in rows)
        + b'],"schema":"strategy_eval.normalized.v1","start_utc_s":' + str(START).encode() + b'}\n')
    bind(scope, doc, allowlist, hashlib.sha256(raw).hexdigest())
    result = cli.materialize(scope, output, allowlist, evaluate=evaluate)
    assert result["exit_code"] == 0 and result["status"] == "AUTHORIZED_PANEL_PARSED"
    assert result["origin_rows"] == 72 and result["historical_outcomes_evaluated"] == 0
    parsed, _, _ = p1.authorized_panel(output / "normalized_panel.json", allowlist)
    assert all(isinstance(o, Outcome) for r in parsed for o in r["outcomes"].values())
    assert all(d == 72 for d in result["horizon_denominators"].values())
    assert (output / "normalized_panel.json").read_bytes() == raw
    if evaluate:
        assert result["evaluation_delegated"] is True
        assert result["evaluated_origin_count"] == result["evaluated_decision_records"] == 0
        assert (output / "p1_evaluation/run_config.json").is_file()


@pytest.mark.parametrize("case,reason", [
    ("unsigned", "EXPLICIT_OWNER_AUTHORIZATION_REQUIRED"),
    ("private", "PRIVATE_PROTECTED_PARTITIONS_UNCONFIRMED"),
    ("private_pending", "PRIVATE_PROTECTED_PARTITIONS_UNCONFIRMED"),
    ("private_unexcluded", "PRIVATE_PARTITION_NOT_EXCLUDED"),
    ("binding", "OWNER_P1_BINDING_REQUIRED"), ("missing_p1", "P1_ALLOWLIST_REQUIRED"),
    ("p1_hash", "P1_ALLOWLIST_HASH_MISMATCH"), ("p1_interval", "P1_PANEL_BINDING_MISMATCH"),
    ("p1_panel_hash", "P1_PANEL_BINDING_MISMATCH"), ("p1_path", "P1_PANEL_BINDING_MISMATCH"),
    ("test_only_p1", "SYNTHETIC_ALLOWLIST_FOR_REAL_INPUT_FORBIDDEN"),
    ("protected", "PROTECTED_DATE_OVERLAP"), ("public_h39", "PROTECTED_DATE_OVERLAP"),
    ("raw_hash", "SCOPE_RAW_HASH_MISMATCH"),
    ("wrong_market", "SCOPE_SOURCE_IDENTITY_MISMATCH"),
    ("symlink_p1", "UNSAFE_OR_MISSING_FILE"), ("changed_manifest", "SCOPE_METADATA_HASH_MISMATCH"),
])
def test_dual_gate_denials_before_any_csv_label_read(zip_scope, monkeypatch, case, reason):
    scope, doc, allowlist, output, roots, records = zip_scope
    if case == "unsigned":
        doc["authorization"]["decision"] = "UNSIGNED_PROPOSAL_HOLD"
    elif case == "private":
        doc["governance"].pop("private_partition_attestations")
    elif case == "private_pending":
        doc["governance"]["private_partition_attestations"]["FINAL_HOLDOUT"]["status"] = "UNKNOWN"
    elif case == "private_unexcluded":
        doc["governance"]["private_partition_attestations"]["FORWARD"]["date_exclusions"] = [
            {"kind": "PROTECTED", "start_utc": "2026-07-02T00:00:00Z", "end_utc": "2026-07-03T00:00:00Z"}]
    elif case == "binding":
        doc.pop("p1_binding")
    elif case == "p1_hash":
        doc["p1_binding"]["allowlist_sha256"] = "f" * 64
    elif case in ("p1_interval", "p1_panel_hash", "p1_path", "test_only_p1"):
        value = json.loads(allowlist.read_bytes())
        if case == "test_only_p1":
            value["test_only"] = True
        else:
            key, replacement = {"p1_interval": ("end_utc_s", START + 2 * 86400),
                "p1_panel_hash": ("sha256", "f" * 64), "p1_path": ("path", str(output / "elsewhere.json"))}[case]
            value["panels"][0][key] = replacement
        allowlist.write_bytes(n.canonical_bytes(value))
        doc["p1_binding"]["allowlist_sha256"] = sha(allowlist)
    elif case == "protected":
        doc["governance"]["protected_date_exclusions"].append({"kind": "PROTECTED",
            "start_utc": "2026-07-02T00:00:00Z", "end_utc": "2026-07-03T00:00:00Z"})
    elif case == "public_h39":
        doc["archive_ranges"][0]["end_utc"] = "2026-10-01T00:00:00Z"
        doc["governance"]["protected_date_exclusions"] = [{"kind": "PROTECTED",
            "start_utc": "2026-10-01T00:00:00Z", "end_utc": "2026-11-01T00:00:00Z"}]
    elif case == "raw_hash":
        path = roots["binance"] / records["binance"][0]["local_path"]
        path.write_bytes(path.read_bytes() + b"changed")
    elif case == "wrong_market":
        doc["sources"][0]["files"][0]["market"] = "spot"
    elif case == "symlink_p1":
        target = allowlist.with_name("actual-p1.json")
        allowlist.rename(target)
        allowlist.symlink_to(target)
    elif case == "changed_manifest":
        path = roots["okx"] / "manifest.json"
        path.write_bytes(path.read_bytes() + b"\n")
    scope.write_bytes(n.canonical_bytes(doc))
    monkeypatch.setattr(n, "_csv_rows", lambda *a, **k: pytest.fail("Denied gate opened outcome CSV"))
    monkeypatch.setattr(p1, "authorized_panel", lambda *a, **k: pytest.fail("Denied gate reached P1"))
    result = cli.materialize(scope, output, None if case == "missing_p1" else allowlist)
    assert result["exit_code"] == 2 and reason in result["blockers"]
    assert result["outcome_labels_read"] == result["historical_outcomes_evaluated"] == 0
    assert not (output / "normalized_panel.json").exists()


def test_label_reader_defaults_to_feature_qc_and_requires_permit(zip_scope):
    permit = permit_for(zip_scope)
    source = next(s for s in adapter.scoped_sources(permit) if s.record["family"] == "candlesticks")
    with pytest.raises(n.BridgeError, match="DUAL_AUTHORIZATION_REQUIRED"):
        next(adapter.native_records(source, n.Budget(), purpose="OUTCOME"))
    rows = list(adapter.native_records(source, n.Budget()))
    assert len(rows) == 1440 and all(r.provenance["read_purpose"] == "FEATURE_QC" for r in rows)
    assert rows[0].provenance["file_calendar_timezone"] == "UTC+08:00"
    assert rows[0].t == START + 16 * 3600  # preserve event epoch, no extra shift


def test_scope_or_allowlist_changed_after_gate_denied_before_labels(zip_scope, monkeypatch):
    permit = permit_for(zip_scope)
    permit.allowlist_path.write_bytes(permit.allowlist_path.read_bytes() + b"\n")
    monkeypatch.setattr(n, "_csv_rows", lambda *a, **k: pytest.fail("Changed authority opened labels"))
    with pytest.raises(n.BridgeError, match="INPUT_CHANGED"):
        list(adapter.panel_rows(permit, {}))


def test_unsigned_proposal_cli_reads_only_metadata_and_compressed_sha(zip_scope, monkeypatch):
    scope, doc, _, output, _, _ = zip_scope
    doc["authorization"]["decision"] = "UNSIGNED_PROPOSAL_HOLD"
    doc["governance"]["protected_dates_complete"] = False
    scope.write_bytes(n.canonical_bytes(doc))
    monkeypatch.setattr(n, "_csv_rows", lambda *a, **k: pytest.fail("Proposal decoded a payload"))
    result = inspection.inspect_proposal(scope, output)
    assert result["pass_compressed_archives"] == 10
    assert result["payload_rows_read"] == result["outcome_labels_read"] == 0
    assert result["access_status"] == "P3_ACCESS_SCOPE_HOLD"
    assert all(s["unchanged"] for s in result["sources"])


@pytest.mark.parametrize("case,reason", [
    ("mark_1440_gap", "UNRESOLVED_FUNDING_RATE_OR_MARK"),
    ("funding_missing", "UNRESOLVED_FUNDING_SETTLEMENT"),
    ("funding_archive_missing", "UNRESOLVED_FUNDING_COVERAGE"),
    ("entry_missing", "UNRESOLVED_ENTRY_PRICE"), ("exit_missing", "UNRESOLVED_EXIT_PRICE"),
    ("spot_archive_missing", "MISSING_X_1M_WINDOW"),
])
def test_native_zip_missingness_retains_every_origin_without_fills(zip_scope, case, reason):
    _, _, _, _, roots, records = zip_scope
    family = ("markPriceKlines" if case == "mark_1440_gap" else "fundingRate" if case.startswith("funding")
              else "spot_klines" if case == "spot_archive_missing" else "klines")
    index = next(i for i, r in enumerate(records["binance"]) if r["family"] == family)
    if case in ("funding_archive_missing", "spot_archive_missing"):
        records["binance"].pop(index)
    else:
        step = 28800 if family == "fundingRate" else 60
        times = list(range(START, START + 3 * 86400, step))
        target = START + 32 * 3600  # funding inside origin at day 2 06:01
        if case == "mark_1440_gap":
            times = [t for t in times if not START + 86400 <= t < START + 2 * 86400]
            gaps = 1440
        else:
            target = START + 30 * 3600 + 120 if case == "entry_missing" else (
                START + 38 * 3600 + 120 if case == "exit_missing" else target)
            times.remove(target)
            gaps = 1 if family == "klines" else 0
        new = archive(roots["binance"], "binance", family, times=[t * n.US for t in times])
        new["gaps"] = gaps
        records["binance"][index] = new
    republish(zip_scope)
    ledger = {}
    rows = list(adapter.panel_rows(permit_for(zip_scope), ledger))
    assert len(rows) == 72 and all(r["action"] == "NO_ACTION" for r in rows)
    row = rows[30]
    if case == "spot_archive_missing":
        assert row["x"] is None and row["x_reason"] == reason and not row["native_feature_ready"]
    else:
        assert "8" not in row["outcomes"] and row["outcome_reasons"]["8"] == reason
        assert economics(None, 1, 8)["sleeve_pnl"] is None
    if case == "mark_1440_gap":
        scanned = next(s for s in ledger["sources"] if s["original_record"]["family"] == family)
        assert scanned["scan"]["missing_minutes"] == 1440


@pytest.mark.parametrize("family", ["metrics", "candlesticks"])
def test_native_wrong_contract_rejected_even_with_pass_hash(zip_scope, family):
    _, _, _, _, roots, records = zip_scope
    venue = "binance" if family == "metrics" else "okx"
    record = next(r for r in records[venue] if r["family"] == family)
    path = roots[venue] / record["local_path"]
    with zipfile.ZipFile(path) as source:
        rows = list(csv.reader(io.StringIO(source.read(record["member_filename"]).decode())))
    rows[1][1 if family == "metrics" else 0] = "ETHUSDT" if family == "metrics" else "ETH-USDT-SWAP"
    text = io.StringIO(newline="")
    csv.writer(text, lineterminator="\n").writerows(rows)
    raw = text.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr(record["member_filename"], raw)
    record.update(local_sha256=sha(path), compressed_bytes=path.stat().st_size, expanded_bytes=len(raw))
    if venue == "binance":
        record["publisher_checksum"] = record["local_sha256"]
    republish(zip_scope)
    with pytest.raises(n.BridgeError, match="CSV_SYMBOL_FAMILY_MISMATCH"):
        list(adapter.panel_rows(permit_for(zip_scope), {}))


@pytest.mark.parametrize("kind", ["manifest", "closed_raw"])
def test_change_after_closed_stream_rejected_before_p1(zip_scope, monkeypatch, kind):
    _, _, _, _, roots, records = zip_scope
    permit = permit_for(zip_scope)
    original = adapter.RollingStream.finish
    changed = False
    def change_after_stream(self):
        nonlocal changed
        original(self)
        if not changed:
            path = roots["binance"] / ("manifest.json" if kind == "manifest" else records["binance"][0]["local_path"])
            path.write_bytes(path.read_bytes() + b"\n")
            changed = True
    monkeypatch.setattr(adapter.RollingStream, "finish", change_after_stream)
    with pytest.raises(n.BridgeError, match="INPUT_CHANGED"):
        list(adapter.panel_rows(permit, {}))


def test_expected_panel_hash_mismatch_discards_panel_and_reports_reads(zip_scope):
    scope, _, allowlist, output, _, _ = zip_scope
    result = cli.materialize(scope, output, allowlist)
    assert result["exit_code"] == 2 and result["status"] == "MATERIALIZATION_BLOCKED"
    assert result["blockers"] == ["P1_EXPECTED_PANEL_HASH_MISMATCH"]
    assert result["outcome_labels_read"] > 0  # synthetic ZIP fixture only
    assert not (output / "normalized_panel.json").exists()


def test_panel_parent_symlink_is_denied_before_csv(zip_scope, monkeypatch):
    scope, doc, allowlist, output, _, _ = zip_scope
    target = output.with_name("actual-output")
    target.mkdir()
    output.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(n, "_csv_rows", lambda *a, **k: pytest.fail("Symlink opened labels"))
    with pytest.raises(ValueError, match="UNSAFE_DIRECTORY_SYMLINK"):
        auth.authorize_dual_gate(scope, allowlist, output / "normalized_panel.json")
