"""Deterministic public artificial coordinates; no source archive/payload reads."""

import itertools
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.research.historical_p3_synthetic_v1 import adapter as a


def prepared(tape=None):
    tape = a.artificial_fixture() if tape is None else tape
    return a.phase_one(a.fixture_scope(tape), tape), tape


def test_deterministic_paired_masks_and_separate_full_population():
    run = a.run_fixture()
    assert run.result == a.run_fixture().result
    x, z, full = (run.result["arms"][k] for k in ("X_common", "XZ_common", "X_full"))
    assert x["eligible_origins"] == z["eligible_origins"]
    assert set(x["eligible_origins"]) < set(full["eligible_origins"])
    assert {r["origin"] for r in z["ledger"] if r["XZ"]} <= {
        r["origin"] for r in x["ledger"] if r["X"]}
    assert all(v["metrics"]["resolved_trades"] for v in run.result["arms"].values())
    assert run.result["real_source_payload_reads"] == 0
    assert not run.result["outcome_authorized"] and not run.result["real_route_enabled"]
    assert set(a.HOLDS) == set(run.result["holds"])


@pytest.mark.parametrize("field,value,reason", [
    ("task", "OTHER", "TASK_IDENTITY"), ("schema", "owner.v2", "REAL_ROUTE_DISABLED"),
    ("authority", "OWNER_APPROVED", "REAL_ROUTE_DISABLED"),
    ("data_kind", "REAL", "REAL_ROUTE_DISABLED"),
    ("registration_sha256", "0" * 64, "HASH_IDENTITY"),
    ("metadata_sha256", "0" * 64, "HASH_IDENTITY"),
    ("source_sha256", "not-a-hash", "SOURCE_HASH_REQUIRED"),
    ("feature_sha256", "0" * 64, "HASH_IDENTITY"),
    ("trade_proposal_sha256", "0" * 64, "HASH_IDENTITY"),
    ("companion_sha256", "0" * 64, "HASH_IDENTITY"),
    ("protected_dates_complete", None, "PRIVATE_ATTESTATIONS"),
    ("origin_range", (a.ORIGINS[0], a.ORIGINS[1] + 1), "2021_ENVELOPE"),
    ("source_envelope", (a.ENVELOPE[0] - 1, a.ENVELOPE[1]), "2021_ENVELOPE"),
])
def test_structural_fail_closed(field, value, reason):
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)
    scope[field] = value
    with pytest.raises(ValueError, match=reason):
        a.phase_one(scope, tape)


@pytest.mark.parametrize("field", ["venue", "product", "symbol", "oi_field", "oi_unit"])
def test_no_mapping_substitution(field):
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)
    scope["source_identity"][field] = "2026_ALIAS"
    with pytest.raises(ValueError, match="SOURCE_IDENTITY"):
        a.phase_one(scope, tape)


def test_no_paths_or_loader_mode():
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)
    scope["source_root"] = "/tmp/2026-alias"
    with pytest.raises(ValueError, match="UNKNOWN_SCOPE_FIELDS"):
        a.phase_one(scope, tape)
    assert not hasattr(a, "load_real_sources")


@pytest.mark.parametrize("partition", a.PARTITIONS)
def test_private_attestation_and_full_archive_intersection(partition):
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)
    scope["private_partition_attestations"][partition]["status"] = None
    with pytest.raises(ValueError, match="PRIVATE_ATTESTATIONS"):
        a.phase_one(scope, tape)
    scope = a.fixture_scope(tape)
    scope["private_partition_attestations"][partition]["date_exclusions"] = [[
        tape.window[1] + 1, tape.window[1] + 2]]
    with pytest.raises(ValueError, match="PRIVATE_EXCLUSION_NOT_COVERED"):
        a.phase_one(scope, tape)
    scope["exclusions"] = [[tape.window[0], tape.window[0] + 1]]
    with pytest.raises(ValueError, match="ARCHIVE_OUTSIDE_SCOPE_OR_PROTECTED"):
        a.phase_one(scope, tape)


def test_half_open_dates_and_legacy_92_day_bound_unchanged():
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)
    assert a.ORIGINS[1] - a.ORIGINS[0] == 84 * 24 * a.HOUR
    assert a.ENVELOPE[1] - a.ENVELOPE[0] == 86 * 24 * a.HOUR
    for origin in (a.ORIGINS[0] - a.HOUR + 60, a.ORIGINS[1] + 60):
        scope["origins"] = [origin]
        with pytest.raises(ValueError, match="ORIGIN_SCOPE_CLOCK"):
            a.phase_one(scope, tape)
    # Hourly HH:01 origin at the last permitted hour is in scope; missing source is excluded.
    scope["origins"] = [a.ORIGINS[1] - a.HOUR + 60]
    assert not a.phase_one(scope, tape).masks["X_full"]
    repo = Path(__file__).resolve().parents[3]
    legacy = repo / "scripts/research/exposed_dev_bridge/authorization.py"
    assert a.hashlib.sha256(legacy.read_bytes()).hexdigest() == (
        "0fe98ac4a184be34acedc93120812d0b41ad3409e95174af0ece95ee3380602e")


@pytest.mark.parametrize("kind", ["x_late", "oi_late", "oi_predecessor"])
def test_feature_lookahead_and_missing_z_excludes_both_common_arms(kind):
    tape = a.artificial_fixture()
    f = tape.features[0]
    if kind == "x_late":
        rows = list(tape.features)
        rows[0] = (*f[:5], f[0] - 60)
        tape = replace(tape, features=tuple(rows))
    else:
        label = f[0] - 60 - 600
        if kind == "oi_predecessor":
            tape = replace(tape, oi=tuple(r for r in tape.oi if r[0] != label - 4 * a.HOUR))
        else:
            tape = replace(tape, oi=tuple((r[0], r[1], f[0] - 60, r[3])
                                         if r[0] == label else r for r in tape.oi))
    permit, _ = prepared(tape)
    assert f[0] not in permit.masks["X_common"]
    assert f[0] not in permit.masks["XZ_common"]
    assert (f[0] in permit.masks["X_full"]) == (kind != "x_late")


def test_outcomes_never_enter_masks():
    permit, tape = prepared()
    altered = replace(tape, opens=(), settlements=(), fills=(), convention="UNKNOWN")
    other, _ = prepared(altered)
    assert permit.masks == other.masks
    assert permit.binding["masks"] == other.binding["masks"]
    with pytest.raises(ValueError, match="HASH_IDENTITY"):
        a.phase_two(permit, altered)


def first_row(tape):
    return prepared(tape)[0].masks["rows"][0]


def test_short_costs_scaling_sign_funding_and_exact_8h_exit():
    tape = a.artificial_fixture()
    row = first_row(tape)
    entry, exit_t = row["entry"], row["exit"]
    assert entry % a.HOUR == 120 and exit_t - entry == 8 * a.HOUR
    # At entry excluded; at exit included. A later settlement is not an input signal.
    calendar = tuple(range(*tape.window, 8 * a.HOUR))
    settlement = next(t for t in calendar if entry < t <= exit_t)
    tape = replace(tape, opens=tuple((t, 100 if t == entry else 90 if t == exit_t else p)
                                    for t, p in tape.opens),
                   settlements=tuple((t, 0.001, 80) if t == settlement else (t, r, m)
                                     for t, r, m in tape.settlements))
    result = a.synthetic_outcome(tape, row)
    baseline = result["economics"]["baseline_16bp"]
    stress = result["economics"]["stress_32bp"]
    assert baseline["gross_return"] == pytest.approx(0.1)
    assert baseline["funding_credit"] == pytest.approx(0.0008)
    assert baseline["entry_fee"] == pytest.approx(0.0005)
    assert baseline["exit_fee"] == pytest.approx(0.00045)
    assert baseline["total_cost"] == pytest.approx(0.00152)
    assert baseline["net_return"] == pytest.approx(0.1 - 0.00152 + 0.0008)
    assert stress["total_cost"] == pytest.approx(0.00304)
    assert stress["net_return"] < baseline["net_return"]


@pytest.mark.parametrize("failure,status,reason", [
    ("NO_FILL", "INELIGIBLE", "FILL_NO_FILL"),
    ("PARTIAL", "UNRESOLVED", "FILL_PARTIAL"),
    ("UNKNOWN", "UNRESOLVED", "FILL_UNKNOWN"),
    ("entry", "INELIGIBLE", "MISSING_EXACT_ENTRY_OR_EXIT"),
    ("exit", "INELIGIBLE", "MISSING_EXACT_ENTRY_OR_EXIT"),
    ("rate", "UNRESOLVED", "RATE_OR_MARK"),
    ("mark", "UNRESOLVED", "RATE_OR_MARK"),
    ("settlement", "UNRESOLVED", "FUNDING_SETTLEMENT"),
    ("convention", "UNRESOLVED", "CONVENTION_UNKNOWN"),
])
def test_explicit_execution_and_funding_resolution(failure, status, reason):
    tape = a.artificial_fixture()
    row = first_row(tape)
    if failure in ("NO_FILL", "PARTIAL", "UNKNOWN"):
        tape = replace(tape, fills=tuple((t, failure if t == row["origin"] else f)
                                        for t, f in tape.fills))
    elif failure in ("entry", "exit"):
        tape = replace(tape, opens=tuple(r for r in tape.opens if r[0] != row[failure]))
    elif failure == "convention":
        tape = replace(tape, convention="PIT_UNKNOWN")
    else:
        hit = next(t for t in tape.calendar if row["entry"] < t <= row["exit"])
        tape = replace(tape, settlements=tuple(
            (t, None if failure == "rate" and t == hit else r,
             None if failure == "mark" and t == hit else m)
            for t, r, m in tape.settlements if not (failure == "settlement" and t == hit)))
    result = a.synthetic_outcome(tape, row)
    assert result["status"] == status and reason in result["reason"]
    assert result["economics"] is None


def test_missing_calendar_not_silently_zero_and_duplicates_rejected():
    tape = a.artificial_fixture()
    row = first_row(tape)
    with pytest.raises(ValueError, match="CALENDAR_CHANGED"):
        a.synthetic_outcome(replace(tape, calendar=()), row)
    with pytest.raises(ValueError, match="DUPLICATE_EXECUTION"):
        a.synthetic_outcome(replace(tape, opens=tape.opens + tape.opens[:1]), row)


def test_capital_cap_exit_release_same_timestamp_and_no_action():
    tape = a.artificial_fixture()
    # Force X true hourly, keep exact pre-outcome feature clocks.
    tape = replace(tape, features=tuple((f[0], True, -0.02, *f[3:]) for f in tape.features))
    permit, _ = prepared(tape)
    run = a.phase_two(permit, tape)
    arm = run.result["arms"]["X_full"]
    trades = [r for r in arm["ledger"] if r["status"] == "RESOLVED"]
    assert trades[1]["entry"] == trades[0]["exit"]
    assert all(a_["exit"] <= b["entry"] for a_, b in itertools.pairwise(trades))
    assert arm["status_counts"]["IGNORED_CAPITAL"] > 0
    assert arm["metrics"]["max_concurrent_positions"] == 1
    assert 0 < arm["metrics"]["exposure_fraction"] < 1
    assert a.run_fixture().result["arms"]["X_common"]["status_counts"]["NO_ACTION"] > 0


def test_unknown_outcomes_reserve_capital_and_partial_totals_labeled():
    permit, tape = prepared()
    origin = permit.masks["rows"][0]["origin"]
    tape = replace(tape, fills=tuple((t, "PARTIAL" if t == origin else f) for t, f in tape.fills))
    permit, _ = prepared(tape)
    arm = a.phase_two(permit, tape).result["arms"]["X_full"]
    assert arm["ledger"][0]["status"] == "UNRESOLVED"
    assert arm["ledger"][1]["status"] == "IGNORED_CAPITAL"
    assert arm["metrics"]["aggregate_status"] == "PARTIAL_RESOLVED_SUBSET"


@pytest.mark.parametrize("change", ["scope", "mask", "code", "result"])
def test_freeze_hash_invalidation(change, monkeypatch):
    run = a.run_fixture()
    if change == "scope":
        run.permit.scope["origins"].pop()
    elif change == "mask":
        run.permit.masks["X_common"].pop()
    elif change == "code":
        monkeypatch.setattr(a, "code_identity", dict)
    else:
        run.result["real_route_enabled"] = True
    with pytest.raises(ValueError, match="CHANGED"):
        run.verify()


def test_atomic_publication_replay_and_existing_target(tmp_path):
    run = a.run_fixture()
    output = tmp_path / "success"
    a.publish(run, output)
    a.replay(output)
    with pytest.raises(ValueError, match="FRESH_OUTPUT_REQUIRED"):
        a.publish(run, output)
    panel = output / "synthetic_panel.json"
    panel.write_bytes(panel.read_bytes() + b" ")
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        a.replay(output)


@pytest.mark.parametrize("failure", ["staged_bytes", "scope", "interrupt"])
def test_two_phase_atomicity_failure_leaves_no_panel(tmp_path, failure):
    run = a.run_fixture()
    output = tmp_path / failure

    def tamper(path):
        if failure == "staged_bytes":
            path.write_bytes(b"corrupt")
        elif failure == "scope":
            run.permit.scope["origins"].pop()
        else:
            raise RuntimeError("INTERRUPTED")

    with pytest.raises((ValueError, RuntimeError)):
        a.publish(run, output, before_revalidation=tamper)
    assert list(output.iterdir()) == []


def test_funding_entry_excluded_exit_included_shared_arithmetic():
    from scripts.research.strategy_eval.costs import BASELINE, Outcome, Settlement, economics
    t = a.ORIGINS[0]
    outcome = Outcome(t, t + 8 * a.HOUR, 100, 100,
                      (Settlement(t * a.US, 10, 100),
                       Settlement((t + 8 * a.HOUR) * a.US, 0.001, 100)),
                      (t * a.US, (t + 8 * a.HOUR) * a.US),
                      (t * a.US, (t + 8 * a.HOUR) * a.US))
    value = economics(outcome, -1, 8, BASELINE)
    assert value["funding_debit"] == -0.001
    assert value["net_return"] == pytest.approx(-0.0016 + 0.001)


def test_mask_ignores_future_settlement_values():
    permit, tape = prepared()
    changed = replace(tape, settlements=tuple((t, 1000, m) for t, r, m in tape.settlements))
    assert prepared(changed)[0].masks == deepcopy(permit.masks)


@pytest.mark.parametrize("days,accepted", [(92, True), (93, False), (126, False)])
def test_legacy_phase_one_retains_92_day_gate(tmp_path, monkeypatch, days, accepted):
    # Isolate the legacy duration check after synthetic upstream validation. No archives.
    from scripts.research.exposed_dev_bridge import authorization as legacy

    start = a.ORIGINS[0]
    end = start + days * 24 * a.HOUR
    panel = tmp_path / "normalized_panel.json"
    binding = {"mode": "DERIVED_P1_INTEGRITY_V1", "panel_path": str(panel),
               "allowlist_path": str(tmp_path / "p1_integrity_allowlist.json"),
               "start_utc_s": start, "end_utc_s": end}
    document = {"authorization": {
        "outcome_panel_materialization": "AUTHORIZE_EXPOSED_DEV_PANEL_MATERIALIZATION"}}
    scope_path = tmp_path / "synthetic-scope.json"
    scope_path.write_bytes(a.canonical(document))
    scope = {"schema": "exposed_dev_bridge.owner-scope.v2", "p1_binding": binding,
             "origin_ranges_utc_us_half_open": [(start * a.US, end * a.US)],
             "archive_ranges_utc_us_half_open": [(start * a.US, end * a.US)],
             "scope_sha256": a.hashlib.sha256(scope_path.read_bytes()).hexdigest()}
    monkeypatch.setattr(legacy, "validate_scope", lambda *args, **kwargs: scope)
    monkeypatch.setattr(legacy, "_private_dates_confirmed", lambda *args: None)
    if accepted:
        permit = legacy.authorize_phase_one(scope_path, panel)
        assert permit.start == start and permit.end == end
    else:
        with pytest.raises(ValueError, match="P1_BOUND_INTERVAL_INVALID"):
            legacy.authorize_phase_one(scope_path, panel)


def test_forged_result_with_updated_hash_cannot_publish(tmp_path):
    run = a.run_fixture()
    run.result["real_route_enabled"] = True
    run.result_sha256 = a.digest(run.result)
    with pytest.raises(ValueError, match="RESULT_NOT_DERIVED"):
        a.publish(run, tmp_path / "forged")
    assert not (tmp_path / "forged").exists()


def test_phase_one_does_not_iterate_outcome_payloads():
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)

    class Unreadable:
        def __iter__(self):
            pytest.fail("Phase one iterated an outcome payload")

        def __deepcopy__(self, memo):
            pytest.fail("Phase one copied an outcome payload")

    tape = replace(tape, opens=Unreadable(), fills=Unreadable(), settlements=Unreadable())
    assert a.phase_one(scope, tape).masks["X_common"]


def test_declared_source_hash_revalidated_before_outcomes():
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)
    scope["source_sha256"] = "0" * 64
    permit = a.phase_one(scope, tape)
    with pytest.raises(ValueError, match="HASH_IDENTITY:source_sha256"):
        a.phase_two(permit, tape)


def test_source_envelope_and_exclusions_half_open_edges():
    tape = a.artificial_fixture()
    scope = a.fixture_scope(tape)
    end = tape.window[1]
    scope["exclusions"] = [[end, end + 1]]
    assert a.phase_one(scope, tape).masks["X_common"]
    scope["exclusions"] = [[end - 1, end]]
    with pytest.raises(ValueError, match="ARCHIVE_OUTSIDE_SCOPE_OR_PROTECTED"):
        a.phase_one(scope, tape)
    scope = a.fixture_scope(tape)
    scope["archive_windows"] = [[a.ENVELOPE[0], a.ENVELOPE[1]]]
    assert a.phase_one(scope, tape).masks["X_common"]
    scope["archive_windows"][0][1] += 1
    with pytest.raises(ValueError, match="ARCHIVE_OUTSIDE_SCOPE_OR_PROTECTED"):
        a.phase_one(scope, tape)
    scope = a.fixture_scope(tape)
    scope["origins"] = [a.ORIGINS[0] + 60]
    # The earliest HH:01 lies in the proposed origin range but its 24h HH:50 OI
    # predecessor lies before the source envelope. It must remain source-ineligible.
    assert not a.phase_one(scope, tape).masks["X_common"]
