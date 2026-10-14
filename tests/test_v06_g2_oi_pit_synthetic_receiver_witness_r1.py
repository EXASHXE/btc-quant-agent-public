"""Invented receiver traces only: never provider calls or admitted market data."""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from itertools import permutations
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.strategy_research.g2_oi_pit_synthetic_receiver_witness_r1 import (
    CONTRACT,
    PERIOD_MS,
    UNIT,
    Attempt,
    ClockWitness,
    DecisionWindows,
    EvidenceSpan,
    ObservationWindow,
    ReceiverState,
    append_attempt,
    evaluate_two_buckets,
    replay,
)

END = 3_600_000
DECISION = 3_800_000
M = 1_000_000


def clock(**kwargs: object) -> ClockWitness:
    return replace(ClockWitness(
        epoch="SYNTHETIC_BOOT_A", anchor_mono_ns=0,
        anchor_utc_upper_ms=3_700_000,
        coverage_start_ns=0, coverage_end_ns=500_000 * M,
        max_drift_ms=0, offset_uncertainty_ms=10,
        external_chrony_receipt="FAKE_CHRONY_RECORD_NOT_ATTESTED",
    ), **kwargs)


def fake_body(end: int, quantity: str = "20403.637", *, pretty: bool = False) -> bytes:
    row = {
        "symbol": "BTCUSDT", "period": "15m", "timestamp": end,
        "sumOpenInterest": quantity, "unit": UNIT, "contractVersion": CONTRACT,
    }
    return json.dumps(row, sort_keys=True, indent=2 if pretty else None).encode("utf-8")


def attempt(seq: int, end: int = END, *, qty: str = "20403.637",
            body: bytes | None = None, ack: int = 7 * M, **kwargs: object) -> Attempt:
    raw = fake_body(end, qty) if body is None else body
    sample = Attempt(
        sequence=seq, attempt_id=f"SYNTHETIC_ATTEMPT_{seq}",
        request_epoch="SYNTHETIC_BOOT_A", headers_epoch="SYNTHETIC_BOOT_A",
        body_epoch="SYNTHETIC_BOOT_A", ack_epoch="SYNTHETIC_BOOT_A",
        request_start_ns=0, headers_received_ns=M, body_last_byte_ns=5 * M,
        integrity_complete_ns=6 * M, durability_ack_ns=ack,
        raw_body=raw, claimed_raw_sha256=sha256(raw).hexdigest(),
        claimed_raw_len=len(raw), body_complete=True, append_ack=True,
        fsync_ack=True, crash_phase="NONE", clock=clock(),
    )
    return replace(sample, **kwargs)


def windows(decision=DECISION):
    return DecisionWindows(ObservationWindow(END - PERIOD_MS, END),
                           ObservationWindow(decision - 1000, decision - 1), 1000)


def evidence(*, gap: str | None = None, decision=DECISION):
    w = windows(decision)
    masks = (EvidenceSpan("X", w.x_confirmation.start_ms, w.x_confirmation.end_ms,
                          known_at_ms=END + 2),
             EvidenceSpan("QUOTE", w.decision_quote.start_ms, w.decision_quote.end_ms,
                          known_at_ms=decision - 1)) + tuple(
        EvidenceSpan("OI", end - PERIOD_MS, end, period_end_ms=end, known_at_ms=end)
        for end in (END - PERIOD_MS, END)
    )
    return tuple(replace(s, complete_observation=True, missing=(s.source == gap)) for s in masks)


def check(state: ReceiverState, *, decision=DECISION, gap=None, **kwargs):
    return evaluate_two_buckets(
        state, newest_period_end_ms=END, decision_ms=decision,
        evidence=evidence(gap=gap, decision=decision), required_windows=windows(decision),
        rights_receipt="FABRICATED_RIGHTS", origin_receipt="FABRICATED_ORIGIN",
        **kwargs,
    )


def pair(*, second_ack=7 * M):
    return replay((attempt(1, END - PERIOD_MS), attempt(2, END, ack=second_ack)))


def assert_unadmitted(v):
    assert v.synthetic_label == "SYNTHETIC_ONLY"
    assert v.pit_status == "PIT_UNKNOWN"
    assert v.source_status == "SOURCE_NOT_ADMITTED"


def test_01_complete_two_bucket_synthetic_time_coherent_but_never_admitted():
    state = pair()
    v = check(state)
    assert v.diagnostic == "SYNTHETIC_TIME_COHERENT_NOT_ADMITTED"
    assert len(v.selected_versions) == 2
    assert all(r.synthetic_label == "SYNTHETIC_ONLY" for r in state.receipts)
    assert_unadmitted(v)


def test_02_period_end_does_not_substitute_for_complete_body_time():
    v = check(pair(), decision=END + 5)
    assert v.diagnostic == "LATE_DURABLE_RECEIPT"
    assert_unadmitted(v)


def test_03_header_only_and_partial_body_have_no_version():
    for bad in (
        {"body_complete": False},
        {"body_last_byte_ns": None},
        {"integrity_complete_ns": None},
        {"claimed_raw_len": 1},
        {"claimed_raw_sha256": "a" * 64},
        {"claimed_raw_sha256": ""},
    ):
        r = replay((attempt(1, **bad),)).receipts[0]
        assert r.receipt_kind == "BODY_OR_DIGEST_INCOMPLETE"
        assert r.version_id is None and r.first_known_at_ms is None


@pytest.mark.parametrize("bad", [
    {"step_detected": True}, {"wall_rollback": True},
    {"offset_uncertainty_ms": 1001},
    {"external_chrony_receipt": None},
    {"coverage_end_ns": 6 * M},
    {"coverage_start_ns": M},
    {"epoch": "UNMATCHED_EPOCH"},
])
def test_04_clock_witness_fail_closed(bad):
    r = replay((attempt(1, clock=clock(**bad)),)).receipts[0]
    assert r.receipt_kind == "CLOCK_UNKNOWN"
    assert r.version_id is None


def test_05_reconnect_epoch_and_rollback_cannot_splice_clocks():
    for field in ("request_epoch", "headers_epoch", "body_epoch", "ack_epoch"):
        r = replay((attempt(1, **{field: "DIFFERENT_EPOCH"}),)).receipts[0]
        assert r.receipt_kind == "CLOCK_UNKNOWN"


def test_06_body_complete_without_durable_fsync_or_ack_is_not_replayable():
    for change in (
        {"append_ack": False}, {"fsync_ack": False},
        {"durability_ack_ns": None},
        {"durability_ack_ns": 5 * M},
        {"crash_phase": "BEFORE_ACK"},
    ):
        r = replay((attempt(1, **change),)).receipts[0]
        assert r.receipt_kind == "LATE_OR_MISSING_DURABILITY"
        assert r.version_id is None


def test_07_late_fsync_12_20_08_blocks_12_20_05_decision():
    safe_start = 3_700_000
    delayed_ack_ns = (388_000 + 8) * M
    state = pair(second_ack=delayed_ack_ns)
    assert state.receipts[1].first_safe_ms == safe_start + 388_008
    v = check(state, decision=4_080_005)
    assert v.diagnostic == "LATE_DURABLE_RECEIPT"
    assert_unadmitted(v)


def test_08_crash_after_ack_remains_appended_and_duplicate_does_not_erase():
    first = attempt(1, crash_phase="AFTER_ACK")
    state = append_attempt(ReceiverState(), first)
    assert state.receipts[0].receipt_kind == "NEW_VERSION"
    later = attempt(2)
    result = append_attempt(state, later)
    assert len(result.receipts) == 2
    assert result.receipts[0] == state.receipts[0]
    assert result.receipts[1].receipt_kind == "RAW_DUPLICATE"
    assert result.receipts[1].first_known_at_ms == result.receipts[0].first_known_at_ms


def test_09_raw_duplicate_vs_same_normalized_numeric_representation():
    a = attempt(1)
    b = attempt(2)
    c = attempt(3, body=fake_body(END, pretty=True))
    result = replay((a, b, c))
    assert [r.receipt_kind for r in result.receipts] == [
        "NEW_VERSION", "RAW_DUPLICATE", "FORMAT_DUPLICATE"
    ]
    assert len({r.version_id for r in result.receipts}) == 1


def test_10_same_logical_key_numeric_correction_appends_new_version():
    base = attempt(1, qty="200.0")
    update = attempt(2, qty="201.0", ack=100 * M)
    state = replay((base, update))
    assert [r.receipt_kind for r in state.receipts] == ["NEW_VERSION", "REVISION"]
    assert [r.version for r in state.receipts] == [1, 2]
    assert state.receipts[1].corrects_version_id == state.receipts[0].version_id
    assert state.receipts[0].quantity == Decimal("200.0")
    assert state.receipts[1].quantity == Decimal("201.0")


def test_11_late_correction_cannot_rewrite_prior_decision():
    source = (attempt(1, END - PERIOD_MS), attempt(2, END, qty="200.0"))
    early = replay(source)
    later = replay(source + (attempt(3, END, qty="201.0", ack=200_000 * M),))
    v1 = check(early, decision=3_750_000)
    after = check(later, decision=3_750_000)
    assert v1.selected_versions == after.selected_versions
    future = check(later, decision=4_000_000)
    assert future.selected_versions[1] != v1.selected_versions[1]
    assert later.receipts[1] == early.receipts[1]


def test_12_missing_prior_bucket_and_late_backfill_never_repair_past():
    only = replay((attempt(1, END),))
    assert check(only).diagnostic == "GAP_OR_NONCONSECUTIVE_BUCKET"
    with_backfill = replay((attempt(1, END), attempt(2, END - PERIOD_MS, ack=200_000 * M)))
    assert check(with_backfill, decision=3_750_000).diagnostic == "LATE_DURABLE_RECEIPT"


@pytest.mark.parametrize("bad", [
    {"contract_version": "UNKNOWN_VERSION"},
    {"unit": "UNKNOWN_UNIT"},
    {"parser_version": "MISMATCH_V9"},
    {"period": "5m"},
    {"endpoint": "/other"},
    {"venue": "UNKNOWN"},
    {"raw_body": b"not-json", "claimed_raw_sha256": sha256(b"not-json").hexdigest(),
     "claimed_raw_len": 8},
    {"raw_body": b'{}', "claimed_raw_sha256": sha256(b'{}').hexdigest(),
     "claimed_raw_len": 2},
])
def test_13_contract_units_and_decoder_conflicts_block(bad):
    r = replay((attempt(1, **bad),)).receipts[0]
    assert r.receipt_kind == "INVALID_CONTRACT_OR_DECODER"
    assert r.version_id is None


def test_14_missing_rights_and_fake_signed_cannot_source_admit():
    state = pair()
    no_rights = evaluate_two_buckets(
        state, newest_period_end_ms=END, decision_ms=DECISION,
        evidence=evidence(), rights_receipt=None, origin_receipt="FAKE_ORIGIN"
    )
    assert no_rights.diagnostic == "RIGHTS_OR_ORIGIN_UNVERIFIED"
    assert_unadmitted(no_rights)
    fake_signature = replay((
        attempt(1, END-PERIOD_MS, synthetic_signed=True, clock=clock(synthetic_signed=True),
                rights_receipt="FAKE_RIGHTS", origin_receipt="FAKE_ORIGIN"),
        attempt(2, END, synthetic_signed=True, clock=clock(synthetic_signed=True),
                rights_receipt="FAKE_RIGHTS", origin_receipt="FAKE_ORIGIN"),
    ))
    assert_unadmitted(check(fake_signature))


@pytest.mark.parametrize("gap", ["X", "QUOTE", "OI"])
def test_15_missing_or_censored_x_quote_oi_blocks(gap):
    assert check(pair(), gap=gap).diagnostic == "SOURCE_GAP"
    assert_unadmitted(check(pair(), gap=gap))


def test_16_missing_evidence_source_and_bad_window_block():
    s = pair()
    for spans in ((EvidenceSpan("OI", END-PERIOD_MS, END),),
                  (EvidenceSpan("X", END, END),) + evidence()[1:]):
        v = evaluate_two_buckets(s, newest_period_end_ms=END, decision_ms=DECISION,
                                 evidence=spans, rights_receipt="FAKE", origin_receipt="FAKE")
        assert v.diagnostic == "SOURCE_GAP"
        assert_unadmitted(v)


def test_17_strict_boundary_and_no_backdating_newer_revision():
    state = pair()
    exact = state.receipts[1].first_known_at_ms
    assert exact is not None
    assert check(state, decision=exact).diagnostic == "LATE_DURABLE_RECEIPT"
    out_of_order = replay((attempt(1, END, ack=70 * M), attempt(2, END, qty="400", ack=7 * M)))
    assert out_of_order.receipts[1].first_known_at_ms >= out_of_order.receipts[0].first_safe_ms


def test_18_explicit_sequence_replay_permutation_is_invariant():
    attempts = (attempt(1, END - PERIOD_MS), attempt(2, END),
                attempt(3, END, qty="20404.0", ack=60 * M))
    expected = replay(attempts)
    for order in permutations(attempts):
        assert replay(order) == expected
        assert check(replay(order), decision=3_750_000).selected_versions == (
            check(expected, decision=3_750_000).selected_versions
        )
    with pytest.raises(ValueError, match="NONCONTIGUOUS"):
        replay((attempt(2),))
    with pytest.raises(ValueError, match="REUSED_ATTEMPT_ID"):
        replay((attempt(1), replace(attempt(2), attempt_id="SYNTHETIC_ATTEMPT_1")))


def test_19_429_and_418_stop_without_provider_poll():
    for status in (418, 429):
        r = replay((attempt(1, http_status=status),)).receipts[0]
        assert r.receipt_kind == "COLLECTOR_PERMIT_INELIGIBLE"
        assert r.first_safe_ms is None


def test_20_import_ast_forbids_network_clock_and_persistence():
    code = (ROOT / "scripts/strategy_research/g2_oi_pit_synthetic_receiver_witness_r1.py").read_text()
    tree = ast.parse(code)
    allowed = {"__future__", "json", "dataclasses", "decimal", "hashlib", "typing"}
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(x.name.split(".")[0] for x in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "eval", "exec", "__import__"}
    assert set(modules) <= allowed
    assert "SYNTHETIC_ONLY" in code and "SOURCE_NOT_ADMITTED" in code
    assert "socket" not in modules and "requests" not in modules


@pytest.mark.parametrize("start,end", [(0, 1), (END - 1, END), (END, END),
                                      (END - 2 * PERIOD_MS - 1, END - 1)])
def test_w01_fabricated_short_zero_or_shifted_labels_are_not_coverage(start, end):
    spans = tuple(EvidenceSpan(s, start, end) for s in ("X", "QUOTE", "OI"))
    v = evaluate_two_buckets(pair(), newest_period_end_ms=END, decision_ms=DECISION,
                             evidence=spans, rights_receipt="FAKE", origin_receipt="FAKE")
    assert v.diagnostic in {"SOURCE_GAP", "SOURCE_EVIDENCE_UNKNOWN"}
    assert not v.selected_versions
    assert_unadmitted(v)


@pytest.mark.parametrize("key", ["symbol", "period", "timestamp", "sumOpenInterest",
                                "unit", "contractVersion"])
@pytest.mark.parametrize("same_value", [True, False])
def test_w02_duplicate_json_members_never_define_a_version(key, same_value):
    row = json.loads(fake_body(END))
    original = row[key]
    row[key] = original if same_value else "CONFLICTING_FIRST_VALUE"
    raw = json.dumps(row).encode()
    raw = raw[:-1] + b", " + json.dumps(key).encode() + b": " + json.dumps(original).encode() + b"}"
    r = replay((attempt(1, body=raw),)).receipts[0]
    assert r.receipt_kind == "INVALID_CONTRACT_OR_DECODER"
    assert r.version_id is None and r.first_known_at_ms is None


@pytest.mark.parametrize("qty", ["NaN", "sNaN", "Infinity", "bad", "", " 1", "1 ",
                                "1_0", "+1", "-0", "1e3", "1e999999", "9" * 100])
def test_w02_nonnumeric_or_nonliteral_decimal_fails_closed(qty):
    r = replay((attempt(1, qty=qty),)).receipts[0]
    assert r.receipt_kind == "INVALID_CONTRACT_OR_DECODER"
    assert r.version_id is None and r.first_known_at_ms is None


@pytest.mark.parametrize("anchor", [END - 100, END - 6])
def test_w03_receiver_or_ack_before_period_close_fails_closed(anchor):
    r = replay((attempt(1, clock=clock(anchor_utc_upper_ms=anchor)),)).receipts[0]
    assert r.receipt_kind in {"PERIOD_RECEIPT_ORDER_UNKNOWN", "CLOCK_UNKNOWN"}
    assert r.version_id is None and r.first_known_at_ms is None


def evaluate_masks(spans, *, contract=None):
    return evaluate_two_buckets(
        pair(), newest_period_end_ms=END, decision_ms=DECISION, evidence=spans,
        required_windows=windows() if contract is None else contract,
        rights_receipt="INVENTED_NOT_AUTHENTICATED", origin_receipt="INVENTED_NOT_AUTHENTICATED",
    )


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("attack", ["short", "zero", "shifted", "missing", "censored",
                                  "unknown", "not_observed", "late", "no_receipt",
                                  "receipt_before_end", "duplicate"])
def test_w01_each_contractual_observation_mask_fails_closed(index, attack):
    spans = list(evidence())
    s = spans[index]
    if attack == "missing":
        del spans[index]
    elif attack == "duplicate":
        spans.append(s)
    else:
        changes = {
            "short": {"start_ms": s.start_ms + 1},
            "zero": {"start_ms": s.end_ms},
            "shifted": {"start_ms": s.start_ms - 1, "end_ms": s.end_ms - 1},
            "censored": {"censored": True},
            "unknown": {"complete_observation": None},
            "not_observed": {"complete_observation": False},
            "late": {"known_at_ms": DECISION},
            "no_receipt": {"known_at_ms": None},
            "receipt_before_end": {"known_at_ms": s.end_ms - 1},
        }
        spans[index] = replace(s, **changes[attack])
    v = evaluate_masks(tuple(spans))
    assert v.diagnostic in {"SOURCE_GAP", "SOURCE_EVIDENCE_UNKNOWN"}
    assert not v.selected_versions
    assert_unadmitted(v)


def test_w01_rest_bucket_labels_and_unknown_contract_never_prove_local_coverage():
    for spans in (evidence(), tuple(replace(s, complete_observation=None) for s in evidence())):
        v = evaluate_two_buckets(pair(), newest_period_end_ms=END, decision_ms=DECISION,
                                 evidence=spans, rights_receipt="FAKE", origin_receipt="FAKE")
        assert v.diagnostic == "SOURCE_EVIDENCE_UNKNOWN"
        assert_unadmitted(v)
    for end in (None, END, END + PERIOD_MS, float(END - PERIOD_MS)):
        spans = list(evidence())
        spans[2] = replace(spans[2], period_end_ms=end)
        assert evaluate_masks(tuple(spans)).diagnostic == "SOURCE_GAP"


@pytest.mark.parametrize("contract", [
    DecisionWindows(ObservationWindow(END - PERIOD_MS + 1, END), windows().decision_quote, 1000),
    DecisionWindows(ObservationWindow(END, END), windows().decision_quote, 1000),
    DecisionWindows(ObservationWindow(0, END - 1), windows().decision_quote, 1000),
    DecisionWindows(windows().x_confirmation, ObservationWindow(END - 1000, END), 1000),
    DecisionWindows(windows().x_confirmation, windows().decision_quote, 999),
    DecisionWindows(windows().x_confirmation, windows().decision_quote, True),
    DecisionWindows(ObservationWindow(float(END - PERIOD_MS), END), windows().decision_quote, 1000),
])
def test_w01_mismatched_or_invalid_predeclared_window_contract(contract):
    v = evaluate_masks(evidence(), contract=contract)
    assert v.diagnostic == "SOURCE_GAP"
    assert not v.selected_versions
    assert_unadmitted(v)


def test_w01_honest_segmented_invented_masks_cover_all_four_windows():
    segments = []
    for span in evidence():
        mid = (span.start_ms + span.end_ms) // 2
        segments.extend((replace(span, end_ms=mid), replace(span, start_ms=mid)))
    v = evaluate_masks(tuple(reversed(segments)))
    assert v.diagnostic == "SYNTHETIC_TIME_COHERENT_NOT_ADMITTED"
    assert len(v.selected_versions) == 2
    assert_unadmitted(v)
    # One millisecond of unobserved exposure cannot be hidden by complete neighbours.
    segments[1] = replace(segments[1], start_ms=segments[1].start_ms + 1)
    assert evaluate_masks(tuple(segments)).diagnostic == "SOURCE_GAP"


@pytest.mark.parametrize("value", [1, 1.0, True, None, [], {}, float("nan")])
def test_w02_quantity_requires_literal_string_not_json_numeric_or_other_type(value):
    row = json.loads(fake_body(END))
    row["sumOpenInterest"] = value
    r = replay((attempt(1, body=json.dumps(row).encode()),)).receipts[0]
    assert r.receipt_kind == "INVALID_CONTRACT_OR_DECODER"
    assert r.version_id is None


def test_w02_nested_duplicates_escaped_member_and_ambiguous_raw_encoding():
    raw = fake_body(END)
    attacks = (
        raw.replace(b'"sumOpenInterest":', b'"sumOpenInterest": "1", "sumOpen\\u0049nterest":'),
        raw[:-1] + b', "extra": {"x": 1, "x": 1}}',
        raw + raw,
        b'\xff' + raw,
        b'\xef\xbb\xbf' + raw,
        raw.decode().encode("utf-16"),
        raw.decode().encode("utf-32"),
        b'"' + b'[' * 4100,
        fake_body(END, "1." + "0" * 19),
    )
    for body in attacks:
        r = replay((attempt(1, body=body),)).receipts[0]
        assert r.receipt_kind == "INVALID_CONTRACT_OR_DECODER"
        assert r.version_id is None


def test_w02_literal_format_duplicates_preserve_original_known_time():
    state = replay((attempt(1, qty="200.0"), attempt(2, qty="200.00", ack=50 * M)))
    assert state.receipts[1].receipt_kind == "FORMAT_DUPLICATE"
    assert state.receipts[1].first_known_at_ms == state.receipts[0].first_known_at_ms


def test_w03_previous_later_receipt_cannot_hide_impossible_period_order():
    state = replay((attempt(1, END - PERIOD_MS),
                    attempt(2, clock=clock(anchor_utc_upper_ms=END - 100))))
    assert state.receipts[1].receipt_kind == "PERIOD_RECEIPT_ORDER_UNKNOWN"
    assert state.receipts[1].version_id is None
    assert_unadmitted(check(state))


def test_w03_receiver_at_period_close_and_durable_ack_after_close_is_coherent():
    r = replay((attempt(1, clock=clock(anchor_utc_upper_ms=END - 5)),)).receipts[0]
    assert r.receipt_kind == "NEW_VERSION"
    assert r.first_known_at_ms == END + 2
    assert r.first_safe_ms >= END
