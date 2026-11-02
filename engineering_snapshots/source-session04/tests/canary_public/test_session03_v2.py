"""Versioned eight-hour launch compatibility; every authority here is fabricated."""

import json

import pytest

from btc_quant_agent.platform.canary import session03 as s
from btc_quant_agent.platform.canary.public_policy import END, PublicStop
from .test_session03 import Clock, body, prepared, signed_file
from .test_session02 import Backend


@pytest.mark.parametrize("version,hours,valid", [
    ("L4_FLEX_SESSION03_GRANT_V1", 6, True),
    ("L4_FLEX_SESSION03_GRANT_V1", 8, False),
    ("L4_FLEX_SESSION03_GRANT_V2", 6, True),
    ("L4_FLEX_SESSION03_GRANT_V2", 8, True),
    ("L4_FLEX_SESSION03_GRANT_V3", 8, False),
])
def test_versioned_launch_limits(version, hours, valid):
    value = body(Clock(), hours * 3600000)
    value["version"] = version
    if valid:
        assert s.GrantBody.model_validate_json(json.dumps(value)).version == version
    else:
        with pytest.raises(ValueError):
            s.GrantBody.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("version", list(s.LAUNCH_LIMITS))
def test_one_millisecond_excess_is_rejected_for_each_version(version):
    value = body(Clock(), s.LAUNCH_LIMITS[version] + 1)
    value["version"] = version
    with pytest.raises(ValueError, match="PERIOD_INVALID"):
        s.GrantBody.model_validate_json(json.dumps(value))


def test_original_v1_schema_and_distinct_v2_schema():
    old = json.loads(s.SCHEMA_V1.read_text())
    new = json.loads(s.SCHEMA.read_text())
    assert old["$defs"]["GrantBody"]["properties"]["version"]["const"] == "L4_FLEX_SESSION03_GRANT_V1"
    assert new["$defs"]["GrantBody"]["properties"]["version"]["const"] == s.VERSION
    assert new["x-runtime-constraints"]["maximum_launch_window_ms"] == 28800000
    req = s.requirements()
    assert req["grant_version"] == s.VERSION and req["maximum_launch_window_ms"] == 28800000
    assert req["owner_keys_installed"] is False and req["owner_grant_created"] is False


@pytest.mark.parametrize("remaining,allowed", [(25001, True), (25000, True), (24999, False), (1, False)])
def test_exact_startup_boundary_at_eight_hour_end(tmp_path, remaining, allowed):
    clock, scope = prepared(tmp_path)
    clock.advance(28800000 - remaining)
    output = tmp_path / "reservation"
    if allowed:
        scope.reserve_launch(clock, output, native=False)
        assert scope.end_ms == scope.outer_end_ms
        assert scope.end_ms - scope.authorization.grant.launch_window_start_utc_ms == 28800000
        assert scope.end_ms - scope.actual_start_ms == remaining
    else:
        with pytest.raises(PublicStop, match="INSUFFICIENT_REMAINING_WINDOW"):
            scope.reserve_launch(clock, output, native=False)
        assert not output.exists()


def test_margin_rechecked_at_atomic_reservation(tmp_path, monkeypatch):
    clock, scope = prepared(tmp_path)
    clock.advance(28800000 - 25000)
    preflight = s.Session03Scope.preflight

    def delayed(self, clock, *, native):
        result = preflight(self, clock, native=native)
        clock.advance(1)
        return result

    monkeypatch.setattr(s.Session03Scope, "preflight", delayed)
    with pytest.raises(PublicStop, match="INSUFFICIENT_REMAINING_WINDOW"):
        scope.reserve_launch(clock, tmp_path / "unused", native=False)
    assert not (tmp_path / "unused").exists()


def test_v2_launch_after_seven_hours_has_new_outer_end_and_replay(tmp_path):
    clock, scope = prepared(tmp_path)
    clock.advance(7 * 3600000)
    assert clock.wall() > END
    result = s.run_session03(scope, enabled=True, clock=clock, backend=Backend(clock), output=tmp_path / "run")
    assert result["absolute_outer_end_unchanged_ms"] == scope.outer_end_ms > END
    assert result["authorized_end_exclusive_ms"] == min(scope.actual_start_ms + 180000, scope.outer_end_ms)
    assert result["replay"]["status"] == "PARITY_VERIFIED"
    assert result["flex_window_contract"]["version"] == s.VERSION
    assert result["native_market_requests"] == 0 and not result["source_qualified"]


@pytest.mark.parametrize("version", list(s.LAUNCH_LIMITS))
def test_signed_version_is_preserved_in_replay_window(tmp_path, version):
    clock = Clock()
    data = body(clock, s.LAUNCH_LIMITS[version])
    data["version"] = version
    path, keys, _ = signed_file(tmp_path, data)
    scope = s.load_session03(path, clock.wall(), fabricated_keys=keys)
    scope.reserve_launch(clock, tmp_path / "reserved", native=False)
    contract = scope.record_window()
    assert contract["version"] == version
    record = {"flex_window_contract": contract, "scope_hash": scope.hash,
              "clock_contract_version": "L4_CLOCK_DOMAIN_V2", "scope_window_ms": [scope.start_ms, scope.end_ms]}
    s.validate_record_window(record)
    contract["launch_end_ms"] = contract["launch_start_ms"] + s.LAUNCH_LIMITS[version] + 1
    with pytest.raises(ValueError, match="BOUNDS_INVALID"):
        s.validate_record_window(record)
