"""Synthetic-only attack tests; no fixture represents empirical market profit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, ClassVar, Self

import pytest

from btc_quant_agent.strategy_research.replay import (
    STRESS,
    Candidate,
    Decision,
    derived_trade,
    execute,
    signal,
)
from btc_quant_agent.strategy_research.source import (
    HOUR,
    MINUTE,
    Bar,
    SourceError,
    SourceManifest,
    archive_url,
    canonical_minutes,
    complete_window,
    digest,
    hourly,
    normalize_csv,
    require_available,
)

D = Decimal
ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "a" * 64
START = 100 * HOUR


def minute(t: int, **values: Any) -> Bar:
    return Bar(
        "BTCUSDT",
        t,
        t + MINUTE,
        t + MINUTE,
        t + MINUTE,
        D(100),
        D(101),
        D(99),
        D(100),
        D(10_000_000),
        TEST_ID,
        "SYNTHETIC_TEST",
        **values,
    )


def path() -> tuple[Bar, ...]:
    return tuple(minute(START + i * MINUTE) for i in range(4 * 60 + 1))


def decision() -> Decision:
    return Decision("BREAKOUT_04H", "BTCUSDT", START, START + MINUTE, "LONG", D(2), "UP", TEST_ID)


def trade(rows: tuple[Bar, ...] | None = None, **kwargs: Any) -> Any:
    return execute(
        Candidate("BREAKOUT", 4),
        decision(),
        rows or path(),
        partition_start=0,
        partition_end=200 * HOUR,
        synthetic_test=True,
        **kwargs,
    )


def feature_hours() -> tuple[Bar, ...]:
    rows = tuple(minute(START + i * MINUTE) for i in range(25 * 60))
    hours = hourly(rows, "BTCUSDT", START, START + 25 * HOUR)
    return (*hours[:-1], replace(hours[-1], close=D(102), high=D(102)))


def test_registry_matches_frozen_method_and_sha() -> None:
    raw = (ROOT / "configs/strategy_research/G2_R1_PREREGISTRATION.json").read_bytes()
    method = json.loads(raw)
    receipt = json.loads(
        (ROOT / "evidence/v0.6/b_line/g2_discovery_r1/PRE_REGISTRATION_RECEIPT.json").read_text()
    )
    assert hashlib.sha256(raw).hexdigest() == receipt["method_sha256"]
    identities = {
        Candidate(f, h).identity
        for f in ("BREAKOUT", "TREND_PULLBACK", "RANGE_REVERSION")
        for h in (4, 8, 16, 24)
    }
    assert identities == {c["id"] for c in method["candidates"]}
    assert len(identities) == 12
    assert all(c["direction"] == "LONG" for c in method["candidates"])


@pytest.mark.parametrize(
    "symbol",
    [
        "ZECUSDT",
        "HYPEUSDT",
        "ORCAUSDT",
        "PUMPUSDT",
        "NMRUSDT",
        "BRUSDT",
        "RLCUSDT",
        "QNTUSDT",
        "../BTCUSDT",
    ],
)
def test_protected_or_unknown_symbol_denied_before_any_access(symbol: str) -> None:
    with pytest.raises(SourceError, match="UNREGISTERED"):
        archive_url(symbol, "2026-05")


@pytest.mark.parametrize("month", ["2026-04", "2026-09", "2026-05/../../"])
def test_unregistered_window_denied(month: str) -> None:
    with pytest.raises(SourceError):
        archive_url("BTCUSDT", month)


@pytest.mark.parametrize("family,hours", [("GRID", 4), ("BREAKOUT", 12), ("BREAKOUT", True)])
def test_no_extra_candidate_or_horizon(family: str, hours: int) -> None:
    with pytest.raises(ValueError):
        Candidate(family, hours)


def test_permutation_determinism_and_duplicate_denial() -> None:
    rows = list(path())
    shuffled = list(rows)
    random.Random(42).shuffle(shuffled)
    assert canonical_minutes(rows) == canonical_minutes(shuffled)
    assert digest([asdict(b) for b in canonical_minutes(rows)]) == digest(
        [asdict(b) for b in canonical_minutes(shuffled)]
    )
    with pytest.raises(SourceError, match="DUPLICATE"):
        canonical_minutes([*rows, rows[0]])


def test_missing_middle_minute_is_not_filled_even_before_early_stop() -> None:
    rows = path()
    early_stop = replace(rows[1], low=D(97), close=D(98))
    broken = (rows[0], early_stop, *rows[2:100], *rows[101:])
    with pytest.raises(SourceError, match="MISSING_1M"):
        trade(broken)


def test_no_hourly_resampling_with_a_missing_minute() -> None:
    rows = tuple(minute(START + i * MINUTE) for i in range(60))
    with pytest.raises(SourceError, match="MISSING_1M"):
        hourly(rows[:20] + rows[21:], "BTCUSDT", START, START + HOUR)
    with pytest.raises(SourceError, match="ALIGNMENT"):
        hourly(rows, "BTCUSDT", START + MINUTE, START + HOUR)


def test_normalization_actual_microseconds_digest_and_cache_identity() -> None:
    start_us = START * 1000
    row = f"{start_us},100,101,99,100,1,{start_us + 59999999},100,1,1,100,0\n".encode()
    manifest = SourceManifest(
        "BTCUSDT",
        "synthetic://g2-unit-test",
        hashlib.sha256(row).hexdigest(),
        START + MINUTE,
        "SYNTHETIC_UNIT_TEST",
        "SYNTHETIC_TEST",
    )
    bars = normalize_csv(row, manifest)
    assert bars[0].event_ms == START
    assert bars[0].end_ms == START + MINUTE
    assert bars[0].source_identity == manifest.identity
    with pytest.raises(SourceError, match="DIGEST_CHANGED"):
        normalize_csv(row.replace(b"101", b"102"), manifest)
    assert replace(manifest, receipt_ms=manifest.receipt_ms + 1).identity != manifest.identity
    with pytest.raises(SourceError, match="VERSION"):
        replace(manifest, version="UNREGISTERED_CACHE_V2")


def test_archive_receipt_cannot_be_relabelled_online_or_synthetic() -> None:
    manifest = SourceManifest(
        "BTCUSDT",
        archive_url("BTCUSDT", "2026-05"),
        TEST_ID,
        START + MINUTE,
        "HISTORICAL_DEVELOPMENT",
        "ARCHIVE_RECEIPT_ONLY",
    )
    with pytest.raises(SourceError, match="CONTEMPORANEOUS"):
        replace(manifest, availability_basis="CONTEMPORANEOUS_RECEIPT_PROVEN")
    with pytest.raises(SourceError, match="SYNTHETIC"):
        replace(manifest, purpose="SYNTHETIC_UNIT_TEST", availability_basis="SYNTHETIC_TEST")
    with pytest.raises(SourceError, match="UNKNOWN_SOURCE"):
        replace(manifest, purpose="VERIFIED_LOCAL_FIXTURE")


@pytest.mark.parametrize("market", ["USDT_M_PERP", "MARGIN", "TESTNET"])
def test_derivatives_or_borrowing_rejected_no_funding_profit(market: str) -> None:
    with pytest.raises(SourceError, match="MARKET"):
        SourceManifest(
            "BTCUSDT",
            "synthetic://g2-unit-test",
            TEST_ID,
            START,
            "SYNTHETIC_UNIT_TEST",
            "SYNTHETIC_TEST",
            market_type=market,
        )


def test_feature_availability_lag_and_shift_by_one_attack() -> None:
    hours = feature_hours()
    valid = signal(Candidate("BREAKOUT", 4), hours, synthetic_test=True)
    assert valid.action == "LONG"
    assert valid.entry_ms == hours[-1].end_ms + 2 * MINUTE
    late = replace(hours[-1], available_ms=valid.decision_ms + 1)
    with pytest.raises(SourceError, match="PIT_LATE"):
        signal(Candidate("BREAKOUT", 4), (*hours[:-1], late), synthetic_test=True)
    with pytest.raises(SourceError, match="CALENDAR"):
        signal(
            Candidate("BREAKOUT", 4),
            (
                *hours[:-1],
                replace(
                    hours[-1],
                    event_ms=hours[-1].event_ms + HOUR,
                    end_ms=hours[-1].end_ms + HOUR,
                    receipt_ms=hours[-1].receipt_ms + HOUR,
                    available_ms=hours[-1].available_ms + HOUR,
                ),
            ),
            synthetic_test=True,
        )


def test_signal_fails_without_explicit_test_context() -> None:
    with pytest.raises(SourceError, match="CONTEMPORANEOUS"):
        signal(Candidate("BREAKOUT", 4), feature_hours())


def test_archive_prices_are_outcome_only_never_signal_inputs() -> None:
    bar = replace(minute(START), availability_basis="ARCHIVE_RECEIPT_ONLY")
    with pytest.raises(SourceError, match="CONTEMPORANEOUS"):
        require_available([bar], START + HOUR, synthetic_test=True)


def test_stop_target_collision_is_loss_and_no_unknown_mfe_credit() -> None:
    rows = path()
    collision = replace(rows[1], high=D(105), low=D(97))
    result = trade((rows[0], collision, *rows[2:]))
    assert result.reason == "SL_FIRST"
    assert result.gross_R == -1
    assert result.mfe_R == 0
    assert result.net_R < -1


def test_stop_gap_and_target_gap_are_conservative() -> None:
    rows = path()
    stop_gap = replace(rows[2], open=D(96), low=D(95), high=D(97), close=D(96))
    stopped = trade((*rows[:2], stop_gap, *rows[3:]))
    assert stopped.gross_R == -2
    target_gap = replace(rows[2], open=D(106), high=D(107), low=D(105), close=D(106))
    targeted = trade((*rows[:2], target_gap, *rows[3:]))
    assert targeted.gross_R == 2
    assert targeted.reason == "TP1"


def test_timeout_cost_split_spot_funding_and_capital_invariance() -> None:
    result = trade()
    assert result.reason == "TIMEOUT"
    assert result.gross_R == 0
    assert result.net_R == D("-0.15")  # (100+100)*(10+2+3)b.p. / risk=2
    assert result.funding_R == 0
    assert result.taker_fee_R + result.spread_R + result.slippage_R == -result.net_R
    assert result.exit_ms - result.entry_ms == 4 * HOUR
    bigger = trade(notional=D(2000))
    assert bigger.net_R == result.net_R
    assert bigger.pnl_usdt == 2 * result.pnl_usdt
    assert trade(friction=STRESS).net_R < result.net_R
    assert result.synthetic_test_only is True


def test_no_fill_with_missing_liquidity_and_fixed_stress() -> None:
    rows = path()
    assert trade((replace(rows[0], quote_volume=D(0)), *rows[1:])) is None
    limited = (replace(rows[0], quote_volume=D(2_000_000)), *rows[1:])
    assert trade(limited) is not None
    assert trade(limited, participation=D("0.0001")) is None


def test_participation_receipt_at_execution_must_not_be_late() -> None:
    rows = path()
    late = replace(rows[0], available_ms=decision().entry_ms + 1)
    with pytest.raises(SourceError, match="PIT_LATE"):
        trade((late, *rows[1:]))


def test_same_bar_entry_overlap_and_boundary_denial() -> None:
    args = {"partition_start": 0, "partition_end": 200 * HOUR, "synthetic_test": True}
    with pytest.raises(SourceError, match="SAME_BAR"):
        execute(Candidate("BREAKOUT", 4), replace(decision(), entry_ms=START), path(), **args)
    with pytest.raises(SourceError, match="OVERLAPPING"):
        trade(previous_exit_ms=decision().entry_ms + MINUTE)
    with pytest.raises(SourceError, match="BOUNDARY"):
        execute(
            Candidate("BREAKOUT", 4),
            decision(),
            path(),
            partition_start=START,
            partition_end=200 * HOUR,
            synthetic_test=True,
        )
    with pytest.raises(SourceError, match="BOUNDARY"):
        execute(
            Candidate("BREAKOUT", 4),
            decision(),
            path(),
            partition_start=0,
            partition_end=decision().entry_ms + 4 * HOUR,
            synthetic_test=True,
        )


def test_wait_no_cost_and_short_ineligible() -> None:
    assert (
        execute(
            Candidate("BREAKOUT", 4),
            replace(decision(), action="WAIT"),
            (),
            partition_start=0,
            partition_end=200 * HOUR,
            synthetic_test=True,
        )
        is None
    )
    with pytest.raises(SourceError, match="UNREGISTERED_DECISION"):
        execute(
            Candidate("BREAKOUT", 4),
            replace(decision(), action="SHORT"),
            path(),
            partition_start=0,
            partition_end=200 * HOUR,
            synthetic_test=True,
        )


def test_restart_identical_input_hash_and_explicit_output_provenance() -> None:
    first = derived_trade(trade())
    second = derived_trade(trade(tuple(reversed(path()))))
    assert first == second
    assert digest(first) == digest(second)
    assert first["synthetic_test_only"] is True
    assert first["net_R"] == "-0.150000000000"


def test_empirical_entrypoint_cannot_execute_even_synthetic_rows() -> None:
    with pytest.raises(SourceError, match="CONTEMPORANEOUS"):
        execute(
            Candidate("BREAKOUT", 4),
            decision(),
            path(),
            partition_start=0,
            partition_end=200 * HOUR,
        )


def test_invalid_prices_risk_and_nonfinite_values_fail_closed() -> None:
    with pytest.raises(SourceError, match="OHLC"):
        replace(minute(START), close=D(102))
    with pytest.raises(SourceError, match="NONFINITE"):
        replace(minute(START), high=D("Infinity"))
    with pytest.raises(SourceError, match="INVALID_RISK"):
        execute(
            Candidate("BREAKOUT", 4),
            replace(decision(), risk=D("NaN")),
            path(),
            partition_start=0,
            partition_end=200 * HOUR,
            synthetic_test=True,
        )


def test_decimal_context_does_not_change_signal_or_trade() -> None:
    expected = derived_trade(trade())
    with localcontext() as context:
        context.prec = 8
        assert derived_trade(trade()) == expected


def test_metadata_audit_never_reads_a_body(monkeypatch: pytest.MonkeyPatch) -> None:
    file = ROOT / "scripts/strategy_research/audit_sources.py"
    spec = importlib.util.spec_from_file_location("g2_metadata_audit_test", file)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    requests = []

    class HeadersOnly:
        status = 200
        headers: ClassVar[dict[str, str]] = {
            "Content-Length": "123",
            "Last-Modified": "Mon, 01 Jun 2026 00:00:00 GMT",
        }

        def __init__(self, url: str) -> None:
            self.url = url

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self, *args: object) -> bytes:
            pytest.fail("OUTCOME_BODY_READ_NOT_AUTHORIZED")

    class Opener:
        def open(self, request: Any, *, timeout: int) -> HeadersOnly:
            assert request.get_method() == "HEAD"
            requests.append(request.full_url)
            return HeadersOnly(request.full_url)

    monkeypatch.setattr(audit, "build_opener", lambda *args: Opener())
    result = audit.audit()
    assert len(requests) == 12
    assert len(set(requests)) == 12
    assert all(row["empirical_eligible"] is False for row in result["sources"])
    assert result["new_empirical_outcome_reads"] == 0
    assert result["archive_bodies_read"] == 0
    with pytest.raises(Exception, match="REDIRECT_NOT_AUTHORIZED"):
        audit.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere")


def test_complete_window_does_not_blend_symbols() -> None:
    rows = path()
    other = tuple(replace(b, symbol="ETHUSDT") for b in rows)
    assert complete_window((*other, *rows), "BTCUSDT", START, START + MINUTE) == rows[:1]
    with pytest.raises(SourceError):
        complete_window(rows, "ETHUSDT", START, START + MINUTE)


def test_zero_range_wait_remains_no_trade() -> None:
    hours = tuple(replace(b, high=D(100), low=D(100)) for b in feature_hours()[:-1])
    last = replace(feature_hours()[-1], high=D(100), low=D(100), close=D(100))
    wait = signal(Candidate("BREAKOUT", 4), (*hours, last), synthetic_test=True)
    assert wait.action == "WAIT" and wait.risk == 0
    assert (
        execute(
            Candidate("BREAKOUT", 4),
            wait,
            (),
            partition_start=0,
            partition_end=200 * HOUR,
            synthetic_test=True,
        )
        is None
    )


def test_fractional_stop_boundary_is_independent_of_decimal_context() -> None:
    from decimal import ROUND_UP, Inexact

    rows = tuple(
        replace(b, open=D("100.123456789"), high=D("101.2"), low=D("99"), close=D("100.123456789"))
        for b in path()
    )
    first = replace(rows[1], low=D("98.88888895"))
    rows = (rows[0], first, *rows[2:])
    setup = replace(decision(), risk=D("1.234567891"))
    args = {"partition_start": 0, "partition_end": 200 * HOUR, "synthetic_test": True}
    expected = execute(Candidate("BREAKOUT", 4), setup, rows, **args)
    assert expected is not None and expected.reason == "TIMEOUT"
    with localcontext() as context:
        context.prec = 8
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        observed = execute(Candidate("BREAKOUT", 4), setup, rows, **args)
        assert observed == expected
        assert derived_trade(observed) == derived_trade(expected)


def test_hourly_volume_is_independent_of_decimal_context() -> None:
    rows = tuple(
        replace(minute(START + i * MINUTE), quote_volume=D("1234.5678912345")) for i in range(60)
    )
    expected = hourly(rows, "BTCUSDT", START, START + HOUR)
    assert expected[0].quote_volume == D("74074.0734740700")
    with localcontext() as context:
        context.prec = 8
        assert hourly(rows, "BTCUSDT", START, START + HOUR) == expected
