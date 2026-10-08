"""R2 synthetic mechanics only; no historical/protected fixtures or profit proof."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import zipfile
from dataclasses import replace
from decimal import ROUND_UP, Decimal, Inexact, localcontext
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.strategy_research.perp_analysis import summary
from btc_quant_agent.strategy_research.perp_replay import (
    CANDIDATES,
    Candidate,
    Series,
    bootstrap,
    derived,
    execute,
    feature,
)
from btc_quant_agent.strategy_research.perp_source import (
    HOUR,
    MINUTE,
    Bar,
    Funding,
    SourceError,
    canonical,
    digest,
    parse_funding,
    parse_prices,
    resample,
    source_url,
    verified_csv,
)

D = Decimal
ROOT = Path(__file__).resolve().parents[1]
START = 100 * HOUR


def bars() -> tuple[Bar, ...]:
    return tuple(
        Bar(
            "BTCUSDT",
            START + i * MINUTE,
            START + (i + 1) * MINUTE,
            D(100),
            D(101),
            D(99),
            D(100),
            D(10000000),
            "a" * 64,
            "SYNTHETIC_TEST",
        )
        for i in range(40 * 60)
    )


def run(series: Series, direction: str = "LONG", **kwargs: Any) -> Any:
    return execute(
        series,
        series.features[0],
        Candidate("NAIVE", direction, 4),
        1,
        0,
        200 * HOUR,
        (),
        proxy=True,
        **kwargs,
    )


def actual_rates(rate: str) -> tuple[Funding, ...]:
    return tuple(Funding(t, D(8), D(rate)) for t in range(0, 200 * HOUR, 8 * HOUR))


def archive(name: str, data: bytes) -> tuple[bytes, bytes]:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr(name.removesuffix(".zip") + ".csv", data)
    value = output.getvalue()
    return value, f"{hashlib.sha256(value).hexdigest()}  {name}\n".encode()


def test_frozen_registry_and_method_hash() -> None:
    raw = (ROOT / "configs/strategy_research/G2_R2_PERP_PREREGISTRATION.json").read_bytes()
    receipt = json.loads(
        (
            ROOT / "evidence/v0.6/b_line/g2_reconstruction_r2/PRE_REGISTRATION_RECEIPT.json"
        ).read_text()
    )
    method = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == receipt["method_sha256"]
    assert {c.identity for c in CANDIDATES} == {c["id"] for c in method["candidates"]}
    assert len(CANDIDATES) == 8 and method["grid"]["mode"] == "NO_GRID"


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
        "BTCUSD_PERP",
        "BTCUSDT_260626",
        "../BTCUSDT",
    ],
)
def test_protected_wrong_market_denied_before_access(symbol: str) -> None:
    with pytest.raises(SourceError, match="UNREGISTERED"):
        source_url("price", symbol, "2026-05")


@pytest.mark.parametrize(
    "kind,month", [("spot", "2026-05"), ("price", "2026-08"), ("funding", "2026-04")]
)
def test_unregistered_market_window(kind: str, month: str) -> None:
    with pytest.raises(SourceError):
        source_url(kind, "BTCUSDT", month)


@pytest.mark.parametrize(
    "family,direction,hours",
    [
        ("GRID", "LONG", 12),
        ("NAIVE", "NEUTRAL", 4),
        ("BREAKOUT", "LONG", 24),
        ("BREAKOUT", "LONG", True),
    ],
)
def test_no_extra_trials_maker_grid_or_horizon(family: str, direction: str, hours: int) -> None:
    with pytest.raises(SourceError):
        Candidate(family, direction, hours)


def test_checksum_corrupt_and_archive_member_denied() -> None:
    name = "BTCUSDT-1m-2026-05.zip"
    value, checksum = archive(name, b"synthetic test only")
    assert verified_csv(value, checksum, name) == b"synthetic test only"
    with pytest.raises(SourceError, match="CHECKSUM"):
        verified_csv(value + b"tamper", checksum, name)
    with pytest.raises(SourceError, match="IDENTITY"):
        verified_csv(value, checksum, "ETHUSDT-1m-2026-05.zip")
    bad, _ = archive("../other.zip", b"synthetic")
    official = f"{hashlib.sha256(bad).hexdigest()}  {name}".encode()
    with pytest.raises(SourceError, match="MEMBER"):
        verified_csv(bad, official, name)


@pytest.mark.parametrize("timeframe", [1, 15, 60, 240])
def test_resampling_closed_bar_availability_epoch(timeframe: int) -> None:
    raw = bars()
    rows = resample(raw, timeframe)
    assert rows[0].t == START and rows[-1].end == raw[-1].end
    assert all(b.end - b.t == timeframe * MINUTE and b.available == b.end + MINUTE for b in rows)
    assert sum((r.qv for r in rows), D(0)) == sum((r.qv for r in raw), D(0))


def test_duplicate_missing_permutation_and_clock_attack() -> None:
    raw = bars()
    assert canonical(tuple(reversed(raw))) == raw
    with pytest.raises(SourceError, match="DUPLICATE"):
        canonical((*raw, raw[0]))
    with pytest.raises(SourceError, match="MISSING"):
        canonical((*raw[:100], *raw[101:]))
    with pytest.raises(SourceError, match="1M"):
        canonical((replace(raw[0], end=raw[0].end + 1),))
    with pytest.raises(SourceError, match="ALIGNMENT"):
        resample(raw[1:61], 60)


def test_bad_millisecond_microsecond_or_month_schema() -> None:
    row = b"1777593600000000,100,101,99,100,1,1777593659999999,100,1,1,100,0\n"
    with pytest.raises(SourceError, match="TIMESTAMP"):
        parse_prices(row, "BTCUSDT", "2026-05")
    with pytest.raises(SourceError, match="INCOMPLETE"):
        parse_prices(
            b"1777593600000,100,101,99,100,1,1777593659999,100,1,1,100,0\n", "BTCUSDT", "2026-05"
        )
    with pytest.raises(SourceError, match="SHAPE"):
        parse_prices(b"a,b\n", "BTCUSDT", "2026-05")


def test_corrupt_nonfinite_unknown_grade_and_negative_volume() -> None:
    b = bars()[0]
    with pytest.raises(SourceError, match="OHLC"):
        replace(b, c=D(200))
    with pytest.raises(SourceError, match="NONFINITE"):
        replace(b, h=D("NaN"))
    with pytest.raises(SourceError, match="GRADE"):
        replace(b, grade="RECEIPT_PROVEN_PIT")
    with pytest.raises(SourceError, match="OHLC"):
        replace(b, qv=D(-1))


def test_funding_schema_duplicate_and_future_month() -> None:
    raw = b"calc_time,funding_interval_hours,last_funding_rate\n1777593600000,8,0.0001\n"
    result = parse_funding(raw, "BTCUSDT", "2026-05")
    assert result[0].rate == D("0.0001")
    with pytest.raises(SourceError, match="DUPLICATE"):
        parse_funding(raw + raw.split(b"\n")[1] + b"\n", "BTCUSDT", "2026-05")
    with pytest.raises(SourceError, match="EVENT"):
        parse_funding(raw, "BTCUSDT", "2026-06")
    with pytest.raises(SourceError, match="SCHEMA"):
        parse_funding(b"fundingRate,fundingTime\n1,2\n", "BTCUSDT", "2026-05")


def test_lookahead_feature_lineage_and_same_bar_denied() -> None:
    series = Series(bars())
    f = series.features[0]
    assert f.entry == f.decision + MINUTE
    for attack in [
        replace(f, decision=f.decision + HOUR, entry=f.entry + HOUR),
        replace(f, risk=f.risk / 2),
        replace(f, identity="b" * 64),
    ]:
        with pytest.raises(SourceError, match="LINEAGE"):
            execute(series, attack, Candidate("NAIVE", "LONG", 4), 1, 0, 200 * HOUR, (), proxy=True)
    with pytest.raises(SourceError, match="SAME_BAR"):
        execute(
            series,
            replace(f, entry=f.decision),
            Candidate("NAIVE", "LONG", 4),
            1,
            0,
            200 * HOUR,
            (),
            proxy=True,
        )
    hours = resample(bars(), 60)
    with pytest.raises(SourceError, match="FEATURE"):
        feature((*hours[:24], replace(hours[24], t=hours[24].t + HOUR, end=hours[24].end + HOUR)))


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_ambiguous_stop_before_target_and_bad_gap(direction: str) -> None:
    original = Series(bars())
    f = original.features[0]
    index = (f.entry - START) // MINUTE
    raw = list(bars())
    raw[index] = replace(raw[index], h=D(107), l=D(93))
    result = run(Series(tuple(raw)), direction).trade
    assert result is not None and result.reason == "SL_FIRST" and result.gross_R == -1
    assert result.mfe_R == 0 and result.net_R < -1
    raw = list(bars())
    raw[index + 1] = replace(
        raw[index + 1],
        o=D(96 if direction == "LONG" else 104),
        c=D(96 if direction == "LONG" else 104),
        h=D(97 if direction == "LONG" else 105),
        l=D(95 if direction == "LONG" else 103),
    )
    gap = run(Series(tuple(raw)), direction).trade
    assert gap is not None and gap.gross_R < -1


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_direction_sign_favorable_gap_not_overcredited(direction: str) -> None:
    original = Series(bars())
    f = original.features[0]
    index = (f.entry - START) // MINUTE
    raw = list(bars())
    raw[index + 1] = replace(
        raw[index + 1],
        o=D(108 if direction == "LONG" else 92),
        c=D(108 if direction == "LONG" else 92),
        h=D(109 if direction == "LONG" else 93),
        l=D(107 if direction == "LONG" else 91),
    )
    t = run(Series(tuple(raw)), direction).trade
    assert t is not None and t.reason == "TP1" and t.gross_R == 2 and t.net_pnl > 0


def test_proxy_funding_empty_input_still_nonzero_and_double_stress() -> None:
    series = Series(bars())
    t = run(series).trade
    assert (
        t is not None
        and t.funding_events == 1
        and t.funding > 0
        and t.stress_funding == 2 * t.funding
    )
    assert (
        t.stress_fee == 2 * t.fee
        and t.stress_spread == 2 * t.spread
        and t.stress_slippage == 2 * t.slippage
    )
    assert t.stress_net_R < t.net_R < 0 and t.gross_R == 0
    assert t.net_pnl == t.gross_pnl - t.fee - t.spread - t.slippage - t.funding
    assert t.capital < D(334) and t.net_pnl / t.capital == t.net_R * (t.risk_price / t.entry_price)


def test_actual_funding_direction_sign_benefits_discarded() -> None:
    series = Series(bars())
    f = series.features[0]
    long = execute(
        series,
        f,
        Candidate("NAIVE", "LONG", 4),
        1,
        0,
        200 * HOUR,
        actual_rates("0.001"),
        proxy=False,
    ).trade
    short = execute(
        series,
        f,
        Candidate("NAIVE", "SHORT", 4),
        1,
        0,
        200 * HOUR,
        actual_rates("0.001"),
        proxy=False,
    ).trade
    assert long is not None and short is not None
    assert long.funding > 0 and short.funding == 0 and short.funding_signed_proxy < 0
    assert short.stress_funding > 0  # no favorable funding assumed
    negative = execute(
        series,
        f,
        Candidate("NAIVE", "SHORT", 4),
        1,
        0,
        200 * HOUR,
        actual_rates("-0.001"),
        proxy=False,
    ).trade
    assert negative is not None and negative.funding > 0
    with pytest.raises(SourceError, match="FUNDING"):
        execute(series, f, Candidate("NAIVE", "LONG", 4), 1, 0, 200 * HOUR, (), proxy=False)


def test_no_overlap_purge_unfilled_stale_and_liquidity_lag() -> None:
    series = Series(bars())
    f = series.features[0]
    assert run(series, previous_exit=f.entry + MINUTE).status == "POSITION_OPEN_WAIT"
    assert (
        execute(
            series,
            f,
            Candidate("NAIVE", "LONG", 4),
            1,
            f.entry - 11 * HOUR,
            200 * HOUR,
            (),
            proxy=True,
        ).status
        == "EMBARGO"
    )
    assert (
        execute(
            series, f, Candidate("NAIVE", "LONG", 4), 1, 0, f.entry + 15 * HOUR, (), proxy=True
        ).status
        == "EMBARGO"
    )
    raw = list(bars())
    index = (f.entry - START) // MINUTE
    raw[index - 2] = replace(raw[index - 2], qv=D(0))
    assert run(Series(tuple(raw))).status == "NO_FILL"
    # Future liquidity can't repair the latest available minute's zero volume.
    raw[index - 1] = replace(raw[index - 1], qv=D(999999999))
    assert run(Series(tuple(raw))).status == "NO_FILL"


def test_r1_read_only_no_signed_or_production_imports() -> None:
    import ast

    for path in (ROOT / "src/btc_quant_agent/strategy_research").glob("*.py"):
        tree = ast.parse(path.read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(
            x.startswith(
                (
                    "btc_quant_agent.execution",
                    "btc_quant_agent.market_watch",
                    "btc_quant_agent.h40",
                    "btc_quant_agent.h41",
                )
            )
            for x in imports
        )
    assert not (ROOT / "configs/strategy_research/G2_R1_PREREGISTRATION.json").exists()


def test_decimal_context_restart_and_provenance_determinism() -> None:
    original = Series(bars())
    t = run(original).trade
    assert t is not None
    expected = derived(t)
    with localcontext() as context:
        context.prec = 7
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        other = Series(tuple(reversed(bars())))
        repeated = run(other).trade
        assert repeated is not None and derived(repeated) == expected
    assert expected["grade"] == "SYNTHETIC_TEST"
    assert digest(expected) == digest(derived(run(original).trade))


def test_zero_atr_wait_no_funding_and_neutral_controls() -> None:
    series = Series(tuple(replace(b, h=D(100), l=D(100)) for b in bars()))
    result = execute(
        series,
        series.features[0],
        Candidate("BREAKOUT", "LONG", 4),
        1,
        0,
        200 * HOUR,
        (),
        proxy=True,
    )
    assert result.status == "WAIT" and result.trade is None


def test_time_block_bootstrap_common_shocks_not_iid_and_fixed_seed() -> None:
    values = [(i * 7 * 24 * HOUR, D(i % 3 - 1)) for i in range(14)]
    first = bootstrap(values, 0)
    with localcontext() as context:
        context.prec = 6
        assert bootstrap(list(reversed(values)), 0) == first
    assert first["blocks"] == 14 and first["replicates"] == 2000
    assert D(first["lower_bonferroni"]) <= D(first["lower_95"])


def test_fetch_cache_and_first_push_gate_before_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = ROOT / "scripts/strategy_research/fetch_perp_r2.py"
    spec = importlib.util.spec_from_file_location("r2_fetch_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("NETWORK_OR_PROTECTED_ACCESS")

    monkeypatch.setattr(module, "build_opener", forbidden)
    with pytest.raises(ValueError, match="CACHE"):
        module.fetch(tmp_path)
    monkeypatch.setattr(
        module, "freeze_gate", lambda: (_ for _ in ()).throw(ValueError("FIRST_PUSH_UNVERIFIED"))
    )
    with pytest.raises(ValueError, match="FIRST_PUSH"):
        module.fetch(Path("/tmp/v06-g2-r2-unproven"))


def test_summary_drawdown_not_grid_paired_profit_or_margined_return() -> None:
    t = run(Series(bars())).trade
    assert t is not None
    result = summary([t])
    assert result["n"] == 1 and result["maker_fees_usdt"] == "0.000000000000"
    assert result["realized_drawdown_usdt"] is not None
    assert summary([t], event_study=True)["realized_drawdown_usdt"] is None


def test_dynamic_funding_terminal_gap_cannot_omit_settlements() -> None:
    from btc_quant_agent.strategy_research.perp_source import funding_complete

    missing = (
        Funding(0, D(8), D("0.001")),
        Funding(8 * HOUR, D(8), D("0.001")),
        Funding(16 * HOUR, D(8), D("0.001")),
        Funding(17 * HOUR, D(1), D("0.001")),
    )
    assert not funding_complete(missing, 0, 24 * HOUR)
    complete = (*missing, *(Funding(t * HOUR, D(1), D("0.001")) for t in range(18, 24)))
    assert funding_complete(complete, 0, 24 * HOUR)


def test_zero_volume_entry_or_open_exit_path_cannot_be_filled() -> None:
    series = Series(bars())
    index = (series.features[0].entry - START) // MINUTE
    raw = list(bars())
    raw[index] = replace(raw[index], qv=D(0))
    assert run(Series(tuple(raw))).status == "NO_FILL"
    raw = list(bars())
    raw[index + 1] = replace(raw[index + 1], qv=D(0))
    with pytest.raises(SourceError, match="ZERO_VOLUME_OUTCOME"):
        run(Series(tuple(raw)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "ETHUSDT"),
        ("kind", "funding"),
        ("market_type", "SPOT"),
        ("grade", "RECEIPT_PROVEN_PIT"),
        ("exposure", "FRESH_HOLDOUT"),
        ("retrieved_utc", "2020-01-01T00:00:00+00:00"),
    ],
)
def test_manifest_record_identity_bound_before_price_access(field: str, value: str) -> None:
    from btc_quant_agent.strategy_research.perp_source import MONTHS, SYMBOLS, validate_manifest

    records = [
        {
            "kind": kind,
            "symbol": symbol,
            "month": month,
            "url": source_url(kind, symbol, month),
            "market_type": "USDT_M_PERPETUAL_FUTURES",
            "grade": "ARCHIVAL_EVENT_TIME_RECONSTRUCTED",
            "exposure": "PRIOR_EXPOSED_OR_DEVELOPMENT",
            "retrieved_utc": "2026-10-08T12:00:00+00:00",
            "status": 200,
            "archive_sha256": "a" * 64,
            "csv_sha256": "b" * 64,
            "checksum_sha256": "c" * 64,
        }
        for kind in ("price", "funding")
        for symbol in SYMBOLS
        for month in (MONTHS if kind == "price" else MONTHS[1:])
    ]
    validate_manifest(records, "2026-10-08T10:00:00+00:00")
    records[0][field] = value
    with pytest.raises(SourceError):
        validate_manifest(records, "2026-10-08T10:00:00+00:00")


def test_public_funding_calculation_jitter_preserved_not_silently_snapped() -> None:
    from btc_quant_agent.strategy_research.perp_source import funding_complete

    raw = (
        b"calc_time,funding_interval_hours,last_funding_rate\n"
        b"1777593600000,8,0.0001\n1777622400005,8,0.0001\n"
    )
    observed = parse_funding(raw, "BTCUSDT", "2026-05")
    assert observed[1].t == 1777622400005
    assert not funding_complete(observed, 1777593600000, 1777651200000)


def test_replay_rejects_unknown_cache_before_reading_any_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/strategy_research"))
    path = ROOT / "scripts/strategy_research/replay_perp_r2.py"
    spec = importlib.util.spec_from_file_location("replay_scope_synthetic_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def forbidden() -> Any:
        pytest.fail("UNKNOWN_MANIFEST_OR_PROTECTED_CACHE_READ")

    monkeypatch.setattr(module, "freeze_gate", forbidden)
    with pytest.raises(SourceError, match="CACHE_PERMISSION_BEFORE_READ"):
        module.replay(Path("/root/unknown-classified-cache"), Path("/tmp/out"))
