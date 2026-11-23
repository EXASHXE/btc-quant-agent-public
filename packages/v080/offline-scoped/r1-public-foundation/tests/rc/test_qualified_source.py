import hashlib
import json

import pytest

from btc_quant_agent.platform.qualified_source import (
    BINANCE_MARKET_ENDPOINT, BINANCE_VENUE, NativeAdmissionBlocked,
    QualificationDimensions, admit_native,
    decode_binance_kline, source_status,
)


def test_qualification_dimensions_are_separate_and_fail_closed():
    q = QualificationDimensions(implemented=True, integrated=True, offline_tested=True)
    assert q.native_qualified is False
    assert q.shadow_qualified is False
    assert q.economically_validated is False
    independent = QualificationDimensions(implemented=True, integrated=True, offline_tested=True,
                                          native_qualified=True)
    assert independent.native_qualified is True
    # This model records independent dimensions; promotion is controlled by separate evidence.


def test_display_distinguishes_synthetic_from_unqualified_native():
    assert source_status(exposure="SYNTHETIC") == "SYNTHETIC"
    assert source_status(exposure="NATIVE") == "NATIVE_BLOCKED_AUTHORITY"


def test_operator_source_inspection_is_network_free_and_admission_stays_blocked(capsys):
    from btc_quant_agent.platform.cli import main

    main(["source", "inspect", "--exposure", "native"])
    output = capsys.readouterr().out
    assert '"status": "NATIVE_BLOCKED_AUTHORITY"' in output
    assert '"exposure": "NATIVE_UNQUALIFIED"' in output
    assert '"network_requests": 0' in output


def wire(**changes):
    event_ms = 1_800_003_600_100
    kline = {"t": 1_800_000_000_000, "T": 1_800_003_599_999,
             "s": "BTCUSDT", "i": "1h", "o": "100", "h": "102",
             "l": "99", "c": "101", "v": "3.5", "x": True}
    event = {"e": "kline", "E": event_ms, "s": "BTCUSDT", "k": kline}
    for key, value in changes.items():
        if key.startswith("k_"):
            kline[key[2:]] = value
        else:
            event[key] = value
    value = {"stream": "btcusdt@kline_1h", "data": event}
    raw = json.dumps(value, separators=(",", ":")).encode()
    return raw, event_ms


def decode(raw, event_ms, **metadata):
    return decode_binance_kline(raw, venue=BINANCE_VENUE, endpoint=BINANCE_MARKET_ENDPOINT,
                                received_ms=event_ms + 1, available_ms=event_ms + 2,
                                durable_ms=event_ms + 3, observed_now_ms=event_ms + 4,
                                expected_symbol="BTCUSDT", expected_interval="1h",
                                **metadata)


def test_original_wire_decoder_binds_native_unqualified_receipt():
    raw, event_ms = wire()
    receipt = decode(raw, event_ms)
    assert receipt.source_status == "NATIVE_UNQUALIFIED"
    assert receipt.clock_status == "UNQUALIFIED"
    assert receipt.interval == "1H" and receipt.close_time_ms == receipt.end_time_ms - 1
    assert receipt.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert receipt.normalized_sha256 != receipt.raw_sha256
    with pytest.raises(NativeAdmissionBlocked, match="NATIVE_BLOCKED_AUTHORITY"):
        admit_native(receipt)


@pytest.mark.parametrize(("mutations", "error"), [
    ({"k_x": 0}, "NATIVE_KLINE_NOT_EXPLICITLY_FINAL"),
    ({"k_s": "ETHUSDT"}, "NATIVE_SYMBOL_OR_INTERVAL_MISMATCH"),
    ({"k_i": "2h"}, "NATIVE_SYMBOL_OR_INTERVAL_MISMATCH"),
    ({"k_h": "NaN"}, "NATIVE_OHLCV_INVALID"),
    ({"k_h": "98"}, "NATIVE_CANDLE_INTEGRITY_OR_CLOCK_INVALID"),
])
def test_original_wire_decoder_rejects_bad_source_events(mutations, error):
    raw, event_ms = wire(**mutations)
    with pytest.raises(ValueError, match=error):
        decode(raw, event_ms)


def test_original_wire_decoder_rejects_endpoint_and_future_availability():
    raw, event_ms = wire()
    with pytest.raises(ValueError, match="VENUE_OR_ENDPOINT"):
        decode_binance_kline(raw, venue=BINANCE_VENUE, endpoint="wss://wrong/market",
                             received_ms=event_ms + 1, available_ms=event_ms + 2,
                             durable_ms=event_ms + 3, observed_now_ms=event_ms + 4,
                             expected_symbol="BTCUSDT", expected_interval="1h")
    with pytest.raises(ValueError, match="EVENT_OR_AVAILABILITY"):
        decode_binance_kline(raw, venue=BINANCE_VENUE, endpoint=BINANCE_MARKET_ENDPOINT,
                             received_ms=event_ms + 1, available_ms=event_ms + 2,
                             durable_ms=event_ms + 3, observed_now_ms=event_ms + 2,
                             expected_symbol="BTCUSDT", expected_interval="1h")


def test_original_wire_decoder_rejects_unbound_revision_and_clock_promotion():
    raw, event_ms = wire()
    with pytest.raises(ValueError, match="REVISION_PROVENANCE_UNKNOWN"):
        decode(raw, event_ms, revision=1)
    with pytest.raises(ValueError, match="CALLER_CLOCK_STATUS_CANNOT_QUALIFY"):
        decode(raw, event_ms, clock_status="NATIVE_QUALIFIED")


def test_original_wire_decoder_rejects_unknown_event_and_invalid_event_time():
    raw, event_ms = wire(e="unknown")
    with pytest.raises(ValueError, match="EVENT_PROVENANCE_UNKNOWN"):
        decode(raw, event_ms)
    raw, event_ms = wire()
    event = json.loads(raw)
    event["data"]["E"] = 1_800_000_000_000
    with pytest.raises(ValueError, match="EVENT_OR_AVAILABILITY_CLOCK_INVALID"):
        decode(json.dumps(event, separators=(",", ":")).encode(), event_ms)


@pytest.mark.parametrize("clock_values", [
    (1_800_003_600_000, 1_800_003_600_200, 1_800_003_600_300),
    (1_800_003_600_101, 1_800_003_600_100, 1_800_003_600_300),
    (1_800_003_600_101, 1_800_003_600_200, 1_800_003_600_199),
])
def test_original_wire_decoder_rejects_unordered_receipt_clocks(clock_values):
    raw, event_ms = wire()
    with pytest.raises(ValueError, match="EVENT_OR_AVAILABILITY_CLOCK_INVALID"):
        decode_binance_kline(raw, venue=BINANCE_VENUE, endpoint=BINANCE_MARKET_ENDPOINT,
                             received_ms=clock_values[0], available_ms=clock_values[1],
                             durable_ms=clock_values[2], observed_now_ms=1_800_003_601_000,
                             expected_symbol="BTCUSDT", expected_interval="1h")


def test_original_wire_decoder_rejects_combined_stream_mismatch():
    raw, event_ms = wire()
    data = json.loads(raw)
    data["stream"] = "ethusdt@kline_1h"
    with pytest.raises(ValueError, match="STREAM_SYMBOL_INTERVAL_MISMATCH"):
        decode(json.dumps(data, separators=(",", ":")).encode(), event_ms)


def test_native_file_inspection_is_local_quarantined_and_never_qualified(tmp_path):
    from btc_quant_agent.platform.rc_operator import inspect_native_wire_file

    raw, event_ms = wire()
    quarantine = tmp_path / "native_quarantine"
    quarantine.mkdir()
    (quarantine / "capture.json").write_bytes(raw)
    result = inspect_native_wire_file("capture.json", symbol="BTCUSDT", interval="1h",
                                      received_ms=event_ms + 1, available_ms=event_ms + 2,
                                      durable_ms=event_ms + 3, observed_now_ms=event_ms + 4,
                                      root=tmp_path)
    assert result["source_status"] == "NATIVE_UNQUALIFIED"
    assert result["source_state"] == "NATIVE_BLOCKED_AUTHORITY"
    assert result["network_requests"] == 0 and result["source_qualified"] is False
    with pytest.raises(ValueError, match="FILENAME_INVALID"):
        inspect_native_wire_file("../outside.json", symbol="BTCUSDT", interval="1h",
                                 received_ms=event_ms + 1, available_ms=event_ms + 2,
                                 durable_ms=event_ms + 3, observed_now_ms=event_ms + 4,
                                 root=tmp_path)


def test_native_file_inspection_rejects_symlinked_quarantine_parent(tmp_path):
    from btc_quant_agent.platform.rc_operator import inspect_native_wire_file

    raw, event_ms = wire()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "capture.json").write_bytes(raw)
    (tmp_path / "native_quarantine").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="NATIVE_QUARANTINE_ROOT_INVALID"):
        inspect_native_wire_file("capture.json", symbol="BTCUSDT", interval="1h",
                                 received_ms=event_ms + 1, available_ms=event_ms + 2,
                                 durable_ms=event_ms + 3, observed_now_ms=event_ms + 4,
                                 root=tmp_path)


def test_original_wire_decoder_requires_source_scope_binding():
    raw, event_ms = wire()
    with pytest.raises(ValueError, match="SIGNED_SCOPE_BINDING_MISSING"):
        decode_binance_kline(raw, venue=BINANCE_VENUE, endpoint=BINANCE_MARKET_ENDPOINT,
                             received_ms=event_ms + 1, available_ms=event_ms + 2,
                             durable_ms=event_ms + 3, observed_now_ms=event_ms + 4)
