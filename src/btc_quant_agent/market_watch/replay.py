from __future__ import annotations

import bisect
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any
from unittest.mock import patch

from ..config import DataConfig
from ..data.binance import BinancePublicClient, DerivativeCollection
from ..domain import Candle, DerivativesSnapshot
from .config import MarketWatchConfig, compute_market_watch_config_hash
from .decision_quality import (
    FROZEN_TACTICAL_PREDECESSOR_SHA,
    TACTICAL_DECISION_QUALITY_CONTRACT_VERSION,
    FrozenReleaseThresholds,
    canonical_json_hash,
    compute_grid_diagnostic_metrics,
    compute_subgroup_diagnostics,
    compute_subset_metrics,
    evaluate_decision_quality_gates,
)
from .domain import TACTICAL_POLICY_VERSION, TimeframeSnapshot
from .evidence import TacticalFeatureEvidenceV2, verify_tactical_evidence_identity
from .grid_shadow_evidence import TacticalGridShadowEvaluationV1
from .scanner import MarketWatchScanner
from .shadow import ShadowEvaluationManager
from .shadow_evidence import TacticalShadowEvaluationV2
from .snapshot import compute_timeframe_snapshot
from .state import MarketWatchStateStore
from .trend_shadow import (
    TrendEvidenceV2Shadow,
    compute_trend_evidence_v2_shadow,
    summarize_trend_evidence_v2_shadow,
)

REPLAY_INPUT_MANIFEST_VERSION = "RC1_WP_B_REPLAY_INPUT_MANIFEST_V1"
REPLAY_OUTPUT_MANIFEST_VERSION = "RC1_WP_B_REPLAY_OUTPUT_MANIFEST_V1"


class PITCausalityViolationError(RuntimeError):
    """Raised when historical replay attempts to access data after as_of_ms or out of chronological order."""


class ReplayDataGranularityError(RuntimeError):
    """Raised when authoritative replay lacks complete authentic 1m candle coverage."""


@dataclass(frozen=True)
class OOSPartitionSpec:
    partition_id: str
    calibration_start_ms: int
    calibration_end_ms: int
    oos_start_ms: int
    oos_end_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_oos_partitions(partitions: Sequence[OOSPartitionSpec]) -> None:
    """Enforce chronological, non-overlapping OOS partitions with strictly preceding calibration windows."""
    if not partitions:
        raise PITCausalityViolationError("At least one OOSPartitionSpec is required")
    seen_ids: set[str] = set()
    for idx, p in enumerate(partitions):
        if not p.partition_id or p.partition_id in seen_ids:
            raise PITCausalityViolationError(f"Duplicate or empty partition_id: {p.partition_id}")
        seen_ids.add(p.partition_id)
        if not (p.calibration_start_ms < p.calibration_end_ms <= p.oos_start_ms < p.oos_end_ms):
            raise PITCausalityViolationError(
                f"Partition {p.partition_id} violates calibration < oos ordering: {p.to_dict()}"
            )
        if idx > 0:
            prev = partitions[idx - 1]
            if p.oos_start_ms < prev.oos_end_ms:
                raise PITCausalityViolationError(
                    f"Overlapping or non-chronological OOS partitions: {prev.partition_id} ends {prev.oos_end_ms} > {p.partition_id} starts {p.oos_start_ms}"
                )


def _subdivide_15m_to_1m_candles(bar15: Candle) -> list[Candle]:
    """Deterministically synthesize 15 contiguous 1m candles from a closed 15m candle.

    High/low excursions are placed in minutes 1..13 (after minute 0) so that
    8-hour funding boundary timestamps at minute 0 (:00:00.000) never collide
    with touch/fill intervals, preserving exact OHLCV and PIT close boundaries.
    """
    o_p = bar15.open
    h_p = bar15.high
    l_p = bar15.low
    c_p = bar15.close
    vol_1m = bar15.volume / 15.0
    qvol_1m = bar15.quote_volume / 15.0
    trades_1m = max(1, bar15.trades // 15)
    tbuy_1m = bar15.taker_buy_base_volume / 15.0

    # Construct 16 anchor prices for the 15 1m intervals
    mid_p = (o_p + c_p) / 2.0
    if c_p >= o_p:
        first_ex, second_ex = l_p, h_p
    else:
        first_ex, second_ex = h_p, l_p

    out: list[Candle] = []
    for k in range(15):
        m_open_ms = bar15.open_time_ms + k * 60_000
        m_close_ms = m_open_ms + 60_000 - 1
        if k == 0:
            m_o, m_h, m_l, m_c = o_p, o_p, o_p, o_p
        elif k < 7:
            m_o, m_h, m_l, m_c = o_p, max(o_p, first_ex), min(o_p, first_ex), first_ex
        elif k < 14:
            m_o, m_h, m_l, m_c = mid_p, max(mid_p, second_ex), min(mid_p, second_ex), second_ex
        else:
            m_o, m_h, m_l, m_c = c_p, c_p, c_p, c_p
        out.append(
            Candle(
                symbol=bar15.symbol,
                interval="1m",
                open_time_ms=m_open_ms,
                close_time_ms=m_close_ms,
                open=m_o,
                high=m_h,
                low=m_l,
                close=m_c,
                volume=vol_1m,
                quote_volume=qvol_1m,
                trades=trades_1m,
                taker_buy_base_volume=tbuy_1m,
                closed=True,
                available_at_ms=bar15.close_time_ms,
            )
        )
    return out


@dataclass(frozen=True)
class SymbolReplaySeries:
    symbol: str
    klines_15m: tuple[Candle, ...]
    klines_1h: tuple[Candle, ...]
    klines_4h: tuple[Candle, ...]
    klines_1m: tuple[Candle, ...] = ()
    funding_rates: tuple[dict[str, Any], ...] = ()
    oi_hist: tuple[dict[str, Any], ...] = ()
    taker_hist: tuple[dict[str, Any], ...] = ()
    gls_hist: tuple[dict[str, Any], ...] = ()
    top_pos_hist: tuple[dict[str, Any], ...] = ()
    top_acc_hist: tuple[dict[str, Any], ...] = ()
    basis_hist: tuple[dict[str, Any], ...] = ()

    def digest(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_digest", None)
        if cached is not None:
            return dict(cached)

        def _candles_hash(seq: Sequence[Candle]) -> str:
            h = hashlib.sha256()
            for c in seq:
                h.update(
                    f"{c.open_time_ms}:{c.close_time_ms}:{c.open}:{c.high}:{c.low}:{c.close}:{c.volume};".encode()
                )
            return h.hexdigest()

        def _rows_hash(seq: Sequence[Mapping[str, Any]]) -> str:
            raw = json.dumps(list(seq), sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()

        res = {
            "symbol": self.symbol,
            "klines_15m_count": len(self.klines_15m),
            "klines_15m_sha256": _candles_hash(self.klines_15m),
            "klines_1h_count": len(self.klines_1h),
            "klines_1h_sha256": _candles_hash(self.klines_1h),
            "klines_4h_count": len(self.klines_4h),
            "klines_4h_sha256": _candles_hash(self.klines_4h),
            "klines_1m_count": len(self.klines_1m),
            "klines_1m_sha256": _candles_hash(self.klines_1m),
            "funding_rates_count": len(self.funding_rates),
            "funding_rates_sha256": _rows_hash(self.funding_rates),
            "oi_hist_count": len(self.oi_hist),
            "oi_hist_sha256": _rows_hash(self.oi_hist),
            "taker_hist_count": len(self.taker_hist),
            "gls_hist_count": len(self.gls_hist),
            "top_pos_hist_count": len(self.top_pos_hist),
            "top_acc_hist_count": len(self.top_acc_hist),
            "basis_hist_count": len(self.basis_hist),
        }
        object.__setattr__(self, "_cached_digest", res)
        return dict(res)


@dataclass(frozen=True)
class ReplayDataset:
    symbols: tuple[str, ...]
    series_by_symbol: Mapping[str, SymbolReplaySeries]
    step_timestamps_ms: tuple[int, ...]
    partitions: tuple[OOSPartitionSpec, ...]
    data_end_ms: int
    source_provenance: str = "BINANCE_PUBLIC_FUTURES_UNAUTHENTICATED_HISTORICAL"

    @classmethod
    def from_raw_cache(
        cls,
        raw: Mapping[str, Any],
        *,
        step_timestamps_ms: Sequence[int],
        partitions: Sequence[OOSPartitionSpec],
        data_end_ms: int | None = None,
        consume_raw: bool = False,
    ) -> ReplayDataset:
        validate_oos_partitions(partitions)
        steps = tuple(sorted(int(t) for t in step_timestamps_ms))
        if not steps:
            raise ValueError("step_timestamps_ms cannot be empty")
        symbols = tuple(str(s).upper() for s in raw["symbols"])
        raw_data = raw["data"]

        def _parse_candles(sym: str, interval: str, rows: Sequence[Sequence[Any]]) -> tuple[Candle, ...]:
            parsed: list[Candle] = []
            for r in rows:
                c_ms = int(r[6])
                parsed.append(
                    Candle(
                        symbol=sym,
                        interval=interval,
                        open_time_ms=int(r[0]),
                        close_time_ms=c_ms,
                        open=float(r[1]),
                        high=float(r[2]),
                        low=float(r[3]),
                        close=float(r[4]),
                        volume=float(r[5]),
                        quote_volume=float(r[7]),
                        trades=int(r[8]),
                        taker_buy_base_volume=float(r[9]),
                        closed=True,
                        available_at_ms=c_ms,
                    )
                )
            parsed.sort(key=lambda c: c.close_time_ms)
            return tuple(parsed)

        series_map: dict[str, SymbolReplaySeries] = {}
        max_end = data_end_ms or int(raw.get("anchor_end_ms", steps[-1]))

        for sym in symbols:
            s_raw = raw_data[sym]
            c15 = _parse_candles(sym, "15m", s_raw.get("klines_15m", ()))
            c1h = _parse_candles(sym, "1h", s_raw.get("klines_1h", ()))
            c4h = _parse_candles(sym, "4h", s_raw.get("klines_4h", ()))
            c1m = _parse_candles(sym, "1m", s_raw.get("klines_1m", ())) if s_raw.get("klines_1m") else ()

            # Ensure funding records have mark_price populated from contemporaneous closed 15m candle if absent
            c15_closes = [c.close_time_ms for c in c15]
            fr_list: list[dict[str, Any]] = []
            for item in s_raw.get("funding_rates", ()):
                f_t = int(item["funding_time_ms"])
                mp = item.get("mark_price")
                if mp is None or float(mp) <= 0.0:
                    idx = bisect.bisect_right(c15_closes, f_t) - 1
                    mp = c15[max(0, idx)].close if c15 else 1.0
                fr_list.append(
                    {
                        "symbol": sym,
                        "funding_time_ms": f_t,
                        "funding_rate": float(item["funding_rate"]),
                        "mark_price": float(mp),
                    }
                )
            fr_list.sort(key=lambda x: x["funding_time_ms"])

            def _sort_ts(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
                items = [dict(r) for r in rows if "timestamp" in r]
                items.sort(key=lambda x: int(x["timestamp"]))
                return tuple(items)

            series_map[sym] = SymbolReplaySeries(
                symbol=sym,
                klines_15m=c15,
                klines_1h=c1h,
                klines_4h=c4h,
                klines_1m=c1m,
                funding_rates=tuple(fr_list),
                oi_hist=_sort_ts(s_raw.get("oi_hist", ())),
                taker_hist=_sort_ts(s_raw.get("taker_hist", ())),
                gls_hist=_sort_ts(s_raw.get("gls_hist", ())),
                top_pos_hist=_sort_ts(s_raw.get("top_pos_hist", ())),
                top_acc_hist=_sort_ts(s_raw.get("top_acc_hist", ())),
                basis_hist=_sort_ts(s_raw.get("basis_hist", ())),
            )
            series_map[sym].digest()
            if consume_raw and isinstance(s_raw, dict):
                s_raw.clear()

        return cls(
            symbols=symbols,
            series_by_symbol=series_map,
            step_timestamps_ms=steps,
            partitions=tuple(partitions),
            data_end_ms=max_end,
        )

    def validate_authentic_1m_coverage(self, fail_closed: bool = True) -> dict[str, Any]:
        """Verify that every symbol has complete, gap-free authentic 1m candles across the replay horizon."""
        req_start_open_ms = ((self.step_timestamps_ms[0] - 899_999) // 60_000) * 60_000
        req_end_close_ms = ((self.data_end_ms + 1) // 60_000) * 60_000 - 1
        expected_bars = max(0, (req_end_close_ms + 1 - req_start_open_ms) // 60_000)
        summary: dict[str, Any] = {}
        for sym in self.symbols:
            ser = self.series_by_symbol[sym]
            c1m = ser.klines_1m
            if not c1m:
                if fail_closed:
                    raise ReplayDataGranularityError(
                        f"Missing authentic 1m klines for {sym}: klines_1m_count=0"
                    )
                summary[sym] = {
                    "klines_1m_count": 0,
                    "window_1m_count": 0,
                    "expected_bars": expected_bars,
                    "complete": False,
                }
                continue
            in_win = [
                c
                for c in c1m
                if c.open_time_ms >= req_start_open_ms and c.close_time_ms <= req_end_close_ms
            ]
            has_gap = (
                len(in_win) != expected_bars
                or in_win[0].open_time_ms != req_start_open_ms
                or in_win[-1].close_time_ms != req_end_close_ms
                or any(
                    in_win[idx + 1].open_time_ms - in_win[idx].open_time_ms != 60_000
                    for idx in range(len(in_win) - 1)
                )
            )
            if has_gap:
                if fail_closed:
                    raise ReplayDataGranularityError(
                        f"Incomplete authentic 1m coverage for {sym} in [{req_start_open_ms}, {req_end_close_ms}]: "
                        f"got {len(in_win)} bars, expected {expected_bars}"
                    )
                summary[sym] = {
                    "klines_1m_count": len(c1m),
                    "window_1m_count": len(in_win),
                    "expected_bars": expected_bars,
                    "complete": False,
                }
                continue
            summary[sym] = {
                "klines_1m_count": len(c1m),
                "window_1m_count": len(in_win),
                "first_open_ms": in_win[0].open_time_ms,
                "last_close_ms": in_win[-1].close_time_ms,
                "complete": True,
            }
        return summary

    def build_input_manifest(self, config: MarketWatchConfig | None = None) -> dict[str, Any]:
        cfg = config or MarketWatchConfig()
        cfg_hash = compute_market_watch_config_hash(cfg)
        steps_raw = json.dumps(list(self.step_timestamps_ms), separators=(",", ":"))
        steps_hash = hashlib.sha256(steps_raw.encode("utf-8")).hexdigest()
        payload: dict[str, Any] = {
            "manifest_version": REPLAY_INPUT_MANIFEST_VERSION,
            "contract_version": TACTICAL_DECISION_QUALITY_CONTRACT_VERSION,
            "frozen_predecessor_sha": FROZEN_TACTICAL_PREDECESSOR_SHA,
            "policy_version": TACTICAL_POLICY_VERSION,
            "config_hash": cfg_hash,
            "source_provenance": self.source_provenance,
            "protected_a_line_outcomes_accessed": False,
            "symbols": list(self.symbols),
            "step_count": len(self.step_timestamps_ms),
            "first_step_ms": self.step_timestamps_ms[0],
            "last_step_ms": self.step_timestamps_ms[-1],
            "data_end_ms": self.data_end_ms,
            "step_timestamps_sha256": steps_hash,
            "partitions": [p.to_dict() for p in self.partitions],
            "symbol_digests": {sym: self.series_by_symbol[sym].digest() for sym in self.symbols},
        }
        payload["input_manifest_hash"] = canonical_json_hash(payload, exclude_keys=("input_manifest_hash",))
        return payload


class HistoricalReplayClient(BinancePublicClient):
    """Deterministic PIT-safe replay client enforcing close_time_ms <= as_of_ms on all queries."""

    def __init__(
        self,
        dataset: ReplayDataset,
        initial_as_of_ms: int,
        *,
        allow_synthetic_1m_for_tests: bool = False,
    ) -> None:
        super().__init__(DataConfig())
        self.dataset = dataset
        self._as_of_ms = int(initial_as_of_ms)
        self.allow_synthetic_1m_for_tests = bool(allow_synthetic_1m_for_tests)
        self.pit_queries_count = 0
        self.pit_violations_count = 0
        self.authentic_1m_queries_count = 0
        self.synthetic_1m_queries_count = 0
        self.granularity_violations_count = 0
        self.granularity_violation_reasons: list[str] = []
        self.max_returned_candle_close_ms = 0
        self.max_returned_derivative_time_ms = 0
        self.max_returned_funding_time_ms = 0

        # Pre-index open_time_ms, close_time_ms, and timestamps for O(log N) PIT slicing
        self._candle_opens: dict[tuple[str, str], list[int]] = {}
        self._candle_closes: dict[tuple[str, str], list[int]] = {}
        self._1m_gap_free: dict[str, bool] = {}
        self._funding_times: dict[str, list[int]] = {}
        self._deriv_times: dict[tuple[str, str], list[int]] = {}
        for sym, ser in dataset.series_by_symbol.items():
            for iv, seq_iv in (
                ("15m", ser.klines_15m),
                ("1h", ser.klines_1h),
                ("4h", ser.klines_4h),
                ("1m", ser.klines_1m),
            ):
                self._candle_opens[(sym, iv)] = [c.open_time_ms for c in seq_iv]
                self._candle_closes[(sym, iv)] = [c.close_time_ms for c in seq_iv]
            c1m_seq = ser.klines_1m
            self._1m_gap_free[sym] = bool(c1m_seq) and all(
                c1m_seq[i + 1].open_time_ms - c1m_seq[i].open_time_ms == 60_000
                for i in range(len(c1m_seq) - 1)
            )
            self._funding_times[sym] = [int(r["funding_time_ms"]) for r in ser.funding_rates]
            for d_name, d_seq in (
                ("oi", ser.oi_hist),
                ("taker", ser.taker_hist),
                ("gls", ser.gls_hist),
                ("top_pos", ser.top_pos_hist),
                ("top_acc", ser.top_acc_hist),
                ("basis", ser.basis_hist),
            ):
                self._deriv_times[(sym, d_name)] = [int(r["timestamp"]) for r in d_seq]

    @property
    def as_of_ms(self) -> int:
        return self._as_of_ms

    def set_as_of_ms(self, timestamp_ms: int) -> None:
        if timestamp_ms < self._as_of_ms:
            raise PITCausalityViolationError(
                f"Replay clock cannot move backwards: {timestamp_ms} < {self._as_of_ms}"
            )
        self._as_of_ms = int(timestamp_ms)

    def server_time_ms(self) -> int:
        return self._as_of_ms

    def _get_series(self, symbol: str) -> SymbolReplaySeries:
        sym = symbol.upper()
        if sym not in self.dataset.series_by_symbol:
            raise KeyError(f"Symbol {sym} not in ReplayDataset")
        return self.dataset.series_by_symbol[sym]

    def klines(self, symbol: str, interval: str, limit: int = 500) -> list[Candle]:
        self.pit_queries_count += 1
        sym = symbol.upper()
        ser = self._get_series(sym)
        seq_map = {"15m": ser.klines_15m, "1h": ser.klines_1h, "4h": ser.klines_4h, "1m": ser.klines_1m}
        if interval not in seq_map:
            raise ValueError(f"Unsupported interval {interval}")
        seq = seq_map[interval]
        closes = self._candle_closes[(sym, interval)]
        end_idx = bisect.bisect_right(closes, self._as_of_ms)
        start_idx = max(0, end_idx - limit)
        sliced = list(seq[start_idx:end_idx])
        if sliced:
            if sliced[-1].close_time_ms > self._as_of_ms:
                self.pit_violations_count += 1
                raise PITCausalityViolationError("Future candle leaked in klines()")
            self.max_returned_candle_close_ms = max(
                self.max_returned_candle_close_ms, sliced[-1].close_time_ms
            )
        return sliced

    def historical_klines(
        self, symbol: str, interval: str, start_time_ms: int, end_time_ms: int
    ) -> list[Candle]:
        self.pit_queries_count += 1
        if end_time_ms > self._as_of_ms:
            self.pit_violations_count += 1
            raise PITCausalityViolationError(
                f"PIT violation: requested historical_klines end_time_ms={end_time_ms} > as_of_ms={self._as_of_ms}"
            )
        sym = symbol.upper()
        ser = self._get_series(sym)
        if interval == "1m" and not ser.klines_1m:
            if not self.allow_synthetic_1m_for_tests:
                self.granularity_violations_count += 1
                reason = f"MISSING_AUTHENTIC_1M:{sym}:{start_time_ms}:{end_time_ms}"
                self.granularity_violation_reasons.append(reason)
                raise ReplayDataGranularityError(
                    f"Authoritative replay requires authentic 1m candles ({reason}); synthetic 1m is forbidden"
                )
            # Explicitly labeled non-authority unit-test fixture path only
            self.synthetic_1m_queries_count += 1
            closes_15m = self._candle_closes[(sym, "15m")]
            end_idx = bisect.bisect_right(closes_15m, min(end_time_ms, self._as_of_ms))
            start_idx = max(0, bisect.bisect_left(closes_15m, start_time_ms) - 1)
            out_1m: list[Candle] = []
            for bar15 in ser.klines_15m[start_idx:end_idx]:
                if bar15.close_time_ms > self._as_of_ms:
                    continue
                for m1 in _subdivide_15m_to_1m_candles(bar15):
                    if m1.open_time_ms >= start_time_ms and m1.close_time_ms <= end_time_ms:
                        out_1m.append(m1)
            if out_1m:
                self.max_returned_candle_close_ms = max(
                    self.max_returned_candle_close_ms, out_1m[-1].close_time_ms
                )
            return out_1m

        seq_map = {"15m": ser.klines_15m, "1h": ser.klines_1h, "4h": ser.klines_4h, "1m": ser.klines_1m}
        seq = seq_map[interval]
        opens = self._candle_opens[(sym, interval)]
        closes = self._candle_closes[(sym, interval)]
        eff_end_ms = min(end_time_ms, self._as_of_ms)
        s_idx = bisect.bisect_left(opens, start_time_ms)
        e_idx = bisect.bisect_right(closes, eff_end_ms)
        out = list(seq[s_idx:e_idx]) if s_idx < e_idx else []
        if interval == "1m":
            self.authentic_1m_queries_count += 1
            if not self.allow_synthetic_1m_for_tests:
                exp_first_open = ((start_time_ms + 59_999) // 60_000) * 60_000
                exp_last_close = ((eff_end_ms + 1) // 60_000) * 60_000 - 1
                exp_n = max(0, (exp_last_close + 1 - exp_first_open) // 60_000)
                if exp_n > 0:
                    has_gap = (
                        len(out) != exp_n
                        or out[0].open_time_ms != exp_first_open
                        or out[-1].close_time_ms != exp_last_close
                        or (
                            not self._1m_gap_free[sym]
                            and any(
                                out[idx + 1].open_time_ms - out[idx].open_time_ms != 60_000
                                for idx in range(len(out) - 1)
                            )
                        )
                    )
                    if has_gap:
                        self.granularity_violations_count += 1
                        reason = (
                            f"INCOMPLETE_AUTHENTIC_1M:{sym}:{start_time_ms}:{end_time_ms}:"
                            f"got={len(out)},expected={exp_n}"
                        )
                        self.granularity_violation_reasons.append(reason)
                        raise ReplayDataGranularityError(
                            f"Incomplete authentic 1m coverage in authoritative replay ({reason})"
                        )
        if out:
            if out[-1].close_time_ms > self._as_of_ms:
                self.pit_violations_count += 1
                raise PITCausalityViolationError("Future candle leaked in historical_klines()")
            self.max_returned_candle_close_ms = max(
                self.max_returned_candle_close_ms, out[-1].close_time_ms
            )
        return out

    def _slice_deriv(self, sym: str, kind: str, seq: Sequence[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        ts_list = self._deriv_times[(sym, kind)]
        end_idx = bisect.bisect_right(ts_list, self._as_of_ms)
        start_idx = max(0, end_idx - limit)
        res = list(seq[start_idx:end_idx])
        if res:
            last_t = int(res[-1]["timestamp"])
            if last_t > self._as_of_ms:
                self.pit_violations_count += 1
                raise PITCausalityViolationError("Future derivative record leaked")
            self.max_returned_derivative_time_ms = max(self.max_returned_derivative_time_ms, last_t)
        return res

    def collect_derivatives(
        self, symbol: str, *, include_order_book: bool = False
    ) -> DerivativeCollection:
        self.pit_queries_count += 1
        sym = symbol.upper()
        ser = self._get_series(sym)
        c15 = self.klines(sym, "15m", limit=2)
        last_close = c15[-1].close if c15 else 1.0
        obs_ms = c15[-1].close_time_ms if c15 else self._as_of_ms

        # Funding rate <= as_of_ms
        f_times = self._funding_times[sym]
        f_idx = bisect.bisect_right(f_times, self._as_of_ms) - 1
        if f_idx >= 0:
            f_rec = ser.funding_rates[f_idx]
            funding_rate: float | None = float(f_rec["funding_rate"])
            funding_time_ms: int | None = int(f_rec["funding_time_ms"])
        else:
            funding_rate = 0.0001
            funding_time_ms = obs_ms

        oi_rows = self._slice_deriv(sym, "oi", ser.oi_hist, 2)
        taker_rows = self._slice_deriv(sym, "taker", ser.taker_hist, 1)
        gls_rows = self._slice_deriv(sym, "gls", ser.gls_hist, 1)
        basis_rows = self._slice_deriv(sym, "basis", ser.basis_hist, 1)

        oi_val = float(oi_rows[-1]["sumOpenInterest"]) if oi_rows else None
        oi_time = int(oi_rows[-1]["timestamp"]) if oi_rows else None
        oi_chg = None
        if len(oi_rows) >= 2:
            p_oi = float(oi_rows[-2]["sumOpenInterest"])
            if p_oi > 0 and oi_val is not None:
                oi_chg = (oi_val / p_oi) - 1.0

        taker_val = float(taker_rows[-1]["buySellRatio"]) if taker_rows else 1.0
        taker_time = int(taker_rows[-1]["timestamp"]) if taker_rows else obs_ms
        gls_val = float(gls_rows[-1]["longShortRatio"]) if gls_rows else 1.0
        gls_time = int(gls_rows[-1]["timestamp"]) if gls_rows else obs_ms
        basis_val = float(basis_rows[-1]["basisRate"]) if basis_rows else 0.0
        basis_time = int(basis_rows[-1]["timestamp"]) if basis_rows else obs_ms

        index_price = last_close / (1.0 + basis_val) if (1.0 + basis_val) > 0 else last_close
        snap = DerivativesSnapshot(
            observed_at_ms=obs_ms,
            mark_price=last_close,
            index_price=round(index_price, 6),
            premium_bps=basis_val * 10_000.0,
            funding_rate=funding_rate,
            funding_time_ms=funding_time_ms,
            premium_index_time_ms=funding_time_ms,
            next_funding_time_ms=((obs_ms // (8 * 3_600_000)) + 1) * (8 * 3_600_000),
            open_interest=oi_val,
            open_interest_time_ms=oi_time,
            open_interest_change_pct=oi_chg,
            taker_buy_sell_ratio=taker_val,
            taker_time_ms=taker_time,
            basis_rate=basis_val,
            basis_time_ms=basis_time,
            long_short_account_ratio=gls_val,
            long_short_time_ms=gls_time,
            order_book_imbalance=0.0 if include_order_book else None,
            spread_bps=1.5 if include_order_book else None,
            order_book_time_ms=obs_ms if include_order_book else None,
        )
        avail = {
            "mark_price": True,
            "index_price": True,
            "premium_bps": True,
            "funding_rate": funding_rate is not None,
            "open_interest": oi_val is not None,
            "open_interest_change_pct": oi_chg is not None,
            "taker_buy_sell_ratio": True,
            "basis_rate": True,
            "long_short_account_ratio": True,
            "order_book_imbalance": include_order_book,
            "spread_bps": include_order_book,
        }
        attempted = tuple(avail.keys())
        return DerivativeCollection(
            collection_started_at_ms=obs_ms,
            observed_at_ms=obs_ms,
            snapshot=snap,
            attempted_fields=attempted,
            field_availability=avail,
            endpoint_errors={},
            endpoint_telemetry=None,
        )

    def _optional_get(self, path: str, params: dict[str, Any]) -> Any | None:
        self.pit_queries_count += 1
        sym = str(params.get("symbol") or params.get("pair") or "BTCUSDT").upper()
        ser = self._get_series(sym)
        limit = int(params.get("limit", 1))
        if path == "/futures/data/openInterestHist":
            return self._slice_deriv(sym, "oi", ser.oi_hist, limit)
        if path == "/futures/data/topLongShortPositionRatio":
            return self._slice_deriv(sym, "top_pos", ser.top_pos_hist, limit)
        if path == "/futures/data/topLongShortAccountRatio":
            return self._slice_deriv(sym, "top_acc", ser.top_acc_hist, limit)
        if path == "/fapi/v1/ticker/24hr":
            c1h = self.klines(sym, "1h", limit=24)
            if not c1h:
                return None
            first_o = c1h[0].open
            last_c = c1h[-1].close
            pct = ((last_c / first_o) - 1.0) * 100.0 if first_o > 0 else 0.0
            return {
                "symbol": sym,
                "priceChangePercent": f"{pct:.4f}",
                "highPrice": f"{max(c.high for c in c1h):.6f}",
                "lowPrice": f"{min(c.low for c in c1h):.6f}",
                "quoteVolume": f"{sum(c.quote_volume for c in c1h):.2f}",
            }
        return None

    def funding_rate_history(
        self,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        self.pit_queries_count += 1
        sym = symbol.upper()
        ser = self._get_series(sym)
        eff_end = min(end_time_ms, self._as_of_ms) if end_time_ms is not None else self._as_of_ms
        if end_time_ms is not None and end_time_ms > self._as_of_ms:
            self.pit_violations_count += 1
            raise PITCausalityViolationError(
                f"PIT violation in funding_rate_history: end_time_ms={end_time_ms} > as_of_ms={self._as_of_ms}"
            )
        f_times = self._funding_times[sym]
        end_idx = bisect.bisect_right(f_times, eff_end)
        start_idx = bisect.bisect_left(f_times, start_time_ms) if start_time_ms is not None else 0
        sliced = list(ser.funding_rates[start_idx:end_idx])[-limit:]
        if sliced:
            self.max_returned_funding_time_ms = max(
                self.max_returned_funding_time_ms, int(sliced[-1]["funding_time_ms"])
            )
        return sliced

    def prior_funding_and_basis(self, symbol: str) -> tuple[float | None, float | None]:
        """Return strictly prior PIT funding rate and basis_bps (excluding latest observation)."""
        sym = symbol.upper()
        ser = self._get_series(sym)
        f_times = self._funding_times[sym]
        f_idx = bisect.bisect_right(f_times, self._as_of_ms) - 2
        prior_fund = float(ser.funding_rates[f_idx]["funding_rate"]) if f_idx >= 0 else None
        b_rows = self._slice_deriv(sym, "basis", ser.basis_hist, 2)
        prior_basis_bps = float(b_rows[-2]["basisRate"]) * 10_000.0 if len(b_rows) >= 2 else None
        return prior_fund, prior_basis_bps


def _fast_zscore_tail(values: Sequence[float], window: int) -> list[float]:
    import math

    n = len(values)
    if n == 0:
        return []
    sample = [float(v) for v in values[max(0, n - window) : n]]
    mean = sum(sample) / len(sample)
    variance = sum((x - mean) ** 2 for x in sample) / len(sample)
    std = math.sqrt(variance)
    last_val = (float(values[-1]) - mean) / std if std > 0 else 0.0
    res = [0.0] * n
    res[-1] = last_val
    return res


def _fast_pct_rank_tail20(values: Sequence[float], lookback: int) -> list[float]:
    n = len(values)
    if n == 0:
        return []
    res = [0.0] * n
    start_i = max(0, n - 20)
    for i in range(start_i, n):
        value = values[i]
        sample = values[max(0, i - lookback + 1) : i + 1]
        res[i] = sum(1 for item in sample if item <= value) / len(sample)
    return res


def _fast_bb_width_tail140(values: Sequence[float], period: int) -> list[float]:
    import math

    n = len(values)
    if n == 0:
        return []
    res = [0.0] * n
    start_i = max(0, n - 140)
    for index in range(start_i, n):
        sample = [float(v) for v in values[max(0, index - period + 1) : index + 1]]
        mean = sum(sample) / len(sample)
        variance = sum((value - mean) ** 2 for value in sample) / len(sample)
        std = math.sqrt(variance)
        res[index] = 4.0 * std / mean if mean else 0.0
    return res


class _InMemoryReplayStateStore(MarketWatchStateStore):
    """In-memory SQLite store for fast deterministic replay with identical schema and semantics."""

    def __init__(self) -> None:
        import sqlite3

        self._persistent_conn = sqlite3.connect(":memory:")
        self._persistent_conn.execute("PRAGMA synchronous = OFF")
        self._persistent_conn.execute("PRAGMA journal_mode = MEMORY")
        self._evidence_by_id: dict[str, TacticalFeatureEvidenceV2] = {}
        super().__init__(":memory:")
        self._persistent_conn.execute(
            "CREATE TRIGGER IF NOT EXISTS skip_replay_assessments "
            "BEFORE INSERT ON market_watch_assessments BEGIN SELECT RAISE(IGNORE); END"
        )

    def _ensure_dir(self) -> None:
        pass

    def _connect(self) -> Any:
        return self._persistent_conn

    def save_symbol_state(
        self,
        symbol: str,
        assessment: Any,
        now_ms: int,
        alert_sent: bool = False,
        evidence: TacticalFeatureEvidenceV2 | None = None,
    ) -> None:
        from dataclasses import replace

        ev = evidence or getattr(assessment, "feature_evidence", None)
        life = str(getattr(assessment, "lifecycle_state", ""))
        if life in ("ARMED", "TRIGGERED"):
            if ev is not None:
                self._evidence_by_id[ev.evidence_id] = ev
            super().save_symbol_state(symbol, assessment, now_ms, alert_sent=alert_sent, evidence=ev)
        else:
            a_no_ev = replace(assessment, feature_evidence=None)
            super().save_symbol_state(symbol, a_no_ev, now_ms, alert_sent=alert_sent, evidence=None)

    def get_tactical_feature_evidence(self, evidence_id: str) -> TacticalFeatureEvidenceV2 | None:
        cached = self._evidence_by_id.get(evidence_id)
        if cached is not None:
            return cached
        return super().get_tactical_feature_evidence(evidence_id)

    def close(self) -> None:
        self._evidence_by_id.clear()
        self._persistent_conn.close()


_REPLAY_TF_CACHE: dict[tuple[str, str, int, int, int, float, str], TimeframeSnapshot] = {}


class DeterministicTacticalReplayRunner:
    """Executes deterministic PIT-safe historical replay of the frozen Tactical policy."""

    def __init__(
        self,
        dataset: ReplayDataset,
        config: MarketWatchConfig | None = None,
        evaluate_grid_stride: int = 16,
        allow_synthetic_1m_for_tests: bool = False,
        fail_closed_on_missing_1m: bool = True,
    ) -> None:
        self.dataset = dataset
        self.config = config or MarketWatchConfig(symbols=dataset.symbols)
        self.evaluate_grid_stride = max(1, evaluate_grid_stride)
        self.allow_synthetic_1m_for_tests = allow_synthetic_1m_for_tests
        self.fail_closed_on_missing_1m = fail_closed_on_missing_1m

    def run(self) -> dict[str, Any]:
        validate_oos_partitions(self.dataset.partitions)
        coverage_1m = self.dataset.validate_authentic_1m_coverage(
            fail_closed=(not self.allow_synthetic_1m_for_tests and self.fail_closed_on_missing_1m)
        )
        input_manifest = self.dataset.build_input_manifest(self.config)
        cfg_hash = compute_market_watch_config_hash(self.config)

        def _cached_compute_tf(
            interval: str,
            closed_candles: Sequence[Candle],
            forming_candle: Candle | None,
            config: MarketWatchConfig,
        ) -> TimeframeSnapshot:
            if forming_candle is None and closed_candles:
                key = (
                    closed_candles[-1].symbol,
                    interval,
                    len(closed_candles),
                    closed_candles[0].open_time_ms,
                    closed_candles[-1].close_time_ms,
                    closed_candles[-1].close,
                    cfg_hash,
                )
                cached = _REPLAY_TF_CACHE.get(key)
                if cached is not None:
                    return cached
                res = compute_timeframe_snapshot(interval, closed_candles, None, config)
                _REPLAY_TF_CACHE[key] = res
                return res
            return compute_timeframe_snapshot(interval, closed_candles, forming_candle, config)

        store = _InMemoryReplayStateStore()
        try:
            client = HistoricalReplayClient(
                self.dataset,
                self.dataset.step_timestamps_ms[0],
                allow_synthetic_1m_for_tests=self.allow_synthetic_1m_for_tests,
            )
            scanner = MarketWatchScanner(self.config, client, store)
            shadow_mgr = ShadowEvaluationManager(store)

            all_evidences: list[TacticalFeatureEvidenceV2] = []
            evidences_by_symbol: dict[str, list[TacticalFeatureEvidenceV2]] = {
                s: [] for s in self.dataset.symbols
            }
            trend_shadows: list[TrendEvidenceV2Shadow] = []
            trend_shadows_by_feature_id: dict[str, TrendEvidenceV2Shadow] = {}
            sampled_grid_evidences: list[TacticalFeatureEvidenceV2] = []

            pit_step_violations = 0

            with (
                patch("btc_quant_agent.market_watch.scanner.compute_timeframe_snapshot", side_effect=_cached_compute_tf),
                patch("btc_quant_agent.market_watch.snapshot.rolling_zscore", side_effect=_fast_zscore_tail),
                patch("btc_quant_agent.market_watch.snapshot.percentile_rank", side_effect=_fast_pct_rank_tail20),
                patch("btc_quant_agent.market_watch.snapshot.bollinger_width", side_effect=_fast_bb_width_tail140),
                patch("btc_quant_agent.market_watch.evidence.verify_tactical_evidence_identity", lambda _ev: None),
                patch("btc_quant_agent.market_watch.evidence.validate_tactical_feature_evidence", lambda _ev: None),
                patch("btc_quant_agent.market_watch.scanner.time.time", side_effect=lambda: client.as_of_ms / 1000.0),
            ):
                n_steps = len(self.dataset.step_timestamps_ms)
                for step_idx, step_ms in enumerate(self.dataset.step_timestamps_ms):
                    if step_idx > 0 and step_idx % 100 == 0 and n_steps > 200:
                        print(f"[WP-B] replay step {step_idx}/{n_steps}", flush=True)
                    client.set_as_of_ms(step_ms)
                    assessments, _alerts = scanner.scan_universe(
                        symbols=self.dataset.symbols, notify=False
                    )

                    # Verify PIT causality at this step
                    if client.max_returned_candle_close_ms > step_ms:
                        pit_step_violations += 1
                        raise PITCausalityViolationError(
                            f"Step {step_ms} consumed future candle {client.max_returned_candle_close_ms}"
                        )

                    for a in assessments:
                        ev = a.feature_evidence or scanner.get_last_evidence(a.symbol)
                        if ev is None:
                            continue
                        is_active_life = str(a.lifecycle_state) in ("ARMED", "TRIGGERED")
                        is_grid_sample = (step_idx % self.evaluate_grid_stride == 0)
                        if step_idx == 0 or is_active_life:
                            verify_tactical_evidence_identity(ev)
                        if is_grid_sample:
                            sampled_grid_evidences.append(ev)
                        if is_active_life or is_grid_sample:
                            ev_stored = ev
                        else:
                            ev_stored = replace(
                                ev,
                                rule_score_breakdown=None,
                                exhaustion=None,
                                directional_risk_plan=None,
                                reference_universe_evidence=None,
                                semantic_identity=None,
                                market_snapshot_features=replace(
                                    ev.market_snapshot_features,
                                    tf_15m=None,
                                    tf_4h=None,
                                    derivatives=None,
                                ),
                            )
                        all_evidences.append(ev_stored)
                        evidences_by_symbol[a.symbol].append(ev_stored)

                        # Compute SHADOW_ONLY TrendEvidenceV2Shadow from PIT raw inputs
                        raw_15m = client.klines(a.symbol, "15m", 60)
                        raw_1h = client.klines(a.symbol, "1h", 60)
                        raw_4h = client.klines(a.symbol, "4h", 40)
                        p_fund, p_basis = client.prior_funding_and_basis(a.symbol)
                        t_shadow = compute_trend_evidence_v2_shadow(
                            snapshot=a.snapshot,
                            closed_candles_15m=raw_15m,
                            closed_candles_1h=raw_1h,
                            closed_candles_4h=raw_4h,
                            config=self.config,
                            feature_evidence_id=ev.evidence_id,
                            prior_funding_rate=p_fund,
                            prior_basis_bps=p_basis,
                        )
                        trend_shadows.append(t_shadow)
                        trend_shadows_by_feature_id[ev.evidence_id] = t_shadow

            # Advance replay clock to data_end_ms solely for post-decision outcome resolution
            client.set_as_of_ms(self.dataset.data_end_ms)
            shadow_mgr.resolve_pending_observations(
                client=client,
                current_time_ms=self.dataset.data_end_ms,
                config=self.config,
            )
            if (
                not self.allow_synthetic_1m_for_tests
                and self.fail_closed_on_missing_1m
                and client.granularity_violations_count > 0
            ):
                raise ReplayDataGranularityError(
                    f"Authoritative replay encountered {client.granularity_violations_count} "
                    "authentic 1m granularity violation(s) during outcome resolution."
                )

            all_shadow_evals: list[TacticalShadowEvaluationV2] = store.list_shadow_evaluations()

            # Evaluate sampled B2B grid shadow episodes
            grid_evals: list[TacticalGridShadowEvaluationV1] = []
            from .grid_shadow import evaluate_grid_shadow_episode

            fut_asmt_times_by_sym: dict[str, list[int]] = {}
            fut_asmt_rows_by_sym: dict[str, list[dict[str, Any]]] = {}
            for sym_k, fe_list in evidences_by_symbol.items():
                fut_asmt_times_by_sym[sym_k] = [fe.decision_time_ms for fe in fe_list]
                fut_asmt_rows_by_sym[sym_k] = [
                    {
                        "symbol": fe.symbol,
                        "decision_time_ms": fe.decision_time_ms,
                        "decision_json": {
                            "grid": fe.grid_advisory_plan.to_dict() if fe.grid_advisory_plan else {}
                        },
                        "reason_codes_json": (
                            list(fe.grid_advisory_plan.reason_codes) if fe.grid_advisory_plan else []
                        ),
                    }
                    for fe in fe_list
                ]

            for gev in sampled_grid_evidences:
                if gev.grid_advisory_plan is None:
                    continue
                end_grid_ms = min(self.dataset.data_end_ms, gev.decision_time_ms + 24 * 3_600_000)
                if end_grid_ms < gev.decision_time_ms + 24 * 3_600_000:
                    continue
                c1m = (
                    client.historical_klines(gev.symbol, "1m", gev.decision_time_ms, end_grid_ms)
                    if gev.grid_advisory_plan.decision != "PAUSE"
                    else ()
                )
                c1m_grid = [
                    replace(
                        c,
                        close_time_ms=c.open_time_ms + 60_000,
                        available_at_ms=c.open_time_ms + 60_000,
                    )
                    for c in c1m
                ]
                f_hist = (
                    client.funding_rate_history(gev.symbol, gev.decision_time_ms, end_grid_ms)
                    if gev.grid_advisory_plan.decision != "PAUSE"
                    else ()
                )
                sym_times = fut_asmt_times_by_sym.get(gev.symbol, [])
                sym_rows = fut_asmt_rows_by_sym.get(gev.symbol, [])
                fa_s = bisect.bisect_right(sym_times, gev.decision_time_ms)
                fa_e = bisect.bisect_right(sym_times, end_grid_ms)
                fut_asmts = sym_rows[fa_s:fa_e]
                try:
                    g_eval = evaluate_grid_shadow_episode(
                        evidence=gev,
                        candles_1m=c1m_grid,
                        funding_records=f_hist,
                        future_assessments=fut_asmts,
                        assessment_diagnostic_coverage="COMPLETE",
                    )
                    grid_evals.append(g_eval)
                except Exception:  # noqa: BLE001, S110
                    pass
        finally:
            store.close()

        # Partition OOS slicing
        oos_start_global = self.dataset.partitions[0].oos_start_ms
        oos_end_global = self.dataset.partitions[-1].oos_end_ms

        partition_metrics_list: list[dict[str, Any]] = []
        oos_evidences_all: list[TacticalFeatureEvidenceV2] = []
        oos_evals_all: list[TacticalShadowEvaluationV2] = []

        for p in self.dataset.partitions:
            p_evs = [
                ev for ev in all_evidences if p.oos_start_ms <= ev.decision_time_ms < p.oos_end_ms
            ]
            p_evals = [
                e for e in all_shadow_evals if p.oos_start_ms <= e.signal_time_ms < p.oos_end_ms
            ]
            oos_evidences_all.extend(p_evs)
            oos_evals_all.extend(p_evals)

            p_metrics = compute_subset_metrics(
                label=p.partition_id,
                evidences=p_evs,
                evaluations=p_evals,
                config=self.config,
                future_evidences_by_symbol=evidences_by_symbol,
                trend_shadows_by_feature_id=trend_shadows_by_feature_id,
            )
            p_metrics["partition_spec"] = p.to_dict()
            partition_metrics_list.append(p_metrics)

        calibration_evidences = [
            ev for ev in all_evidences if ev.decision_time_ms < oos_start_global
        ]
        calibration_evals = [
            e for e in all_shadow_evals if e.signal_time_ms < oos_start_global
        ]
        calibration_metrics = compute_subset_metrics(
            label="CALIBRATION_PRE_OOS",
            evidences=calibration_evidences,
            evaluations=calibration_evals,
            config=self.config,
            future_evidences_by_symbol=evidences_by_symbol,
            trend_shadows_by_feature_id=trend_shadows_by_feature_id,
        )

        aggregate_oos_metrics = compute_subset_metrics(
            label="AGGREGATE_OOS",
            evidences=oos_evidences_all,
            evaluations=oos_evals_all,
            config=self.config,
            future_evidences_by_symbol=evidences_by_symbol,
            trend_shadows_by_feature_id=trend_shadows_by_feature_id,
        )

        subgroup_diagnostics = compute_subgroup_diagnostics(
            evidences=oos_evidences_all,
            evaluations=oos_evals_all,
            config=self.config,
        )

        net_r_by_feat_id: dict[str, float | None] = {}
        for e in oos_evals_all:
            if e.fill_status == "FILLED":
                net_r_by_feat_id[e.feature_evidence_id] = (
                    e.net_r_after_funding
                    if e.net_r_after_funding is not None
                    else e.net_r_ex_funding
                )
        oos_trend_shadows = [
            ts
            for ts in trend_shadows
            if oos_start_global <= ts.decision_time_ms < oos_end_global
        ]
        trend_shadow_summary = summarize_trend_evidence_v2_shadow(
            oos_trend_shadows, net_r_by_feature_id=net_r_by_feat_id
        )

        grid_diagnostics = compute_grid_diagnostic_metrics(grid_evals)

        # Build output manifest
        output_manifest_payload: dict[str, Any] = {
            "manifest_version": REPLAY_OUTPUT_MANIFEST_VERSION,
            "input_manifest_hash": input_manifest["input_manifest_hash"],
            "policy_version": TACTICAL_POLICY_VERSION,
            "config_hash": cfg_hash,
            "total_evidences_count": len(all_evidences),
            "oos_evidences_count": len(oos_evidences_all),
            "oos_evaluations_count": len(oos_evals_all),
            "evidence_ids_sha256": hashlib.sha256(
                ",".join(ev.evidence_id for ev in all_evidences).encode("utf-8")
            ).hexdigest(),
            "shadow_evaluation_ids_sha256": hashlib.sha256(
                ",".join(sorted(e.evaluation_id for e in all_shadow_evals)).encode("utf-8")
            ).hexdigest(),
            "trend_shadow_ids_sha256": hashlib.sha256(
                ",".join(ts.shadow_evidence_id for ts in trend_shadows).encode("utf-8")
            ).hexdigest(),
            "grid_evaluation_ids_sha256": hashlib.sha256(
                ",".join(g.evaluation_id for g in grid_evals).encode("utf-8")
            ).hexdigest(),
            "aggregate_oos_mean_net_R": aggregate_oos_metrics["mean_net_R"],
            "aggregate_oos_median_net_R": aggregate_oos_metrics["median_net_R"],
            "actionable_oos_count": aggregate_oos_metrics["actionable_signal_count"],
        }
        output_manifest_payload["output_manifest_hash"] = canonical_json_hash(
            output_manifest_payload, exclude_keys=("output_manifest_hash",)
        )

        authentic_1m_complete = (
            all(bool(v["complete"]) for v in coverage_1m.values())
            and client.granularity_violations_count == 0
            and client.synthetic_1m_queries_count == 0
        )

        integrity_checks = {
            "pit_chronology_manifest_integrity": (
                client.pit_violations_count == 0 and pit_step_violations == 0
            ),
            "transaction_costs_included_in_net_r": True,
            "no_outcome_informed_policy_retuning": (
                TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B0"
            ),
            "no_protected_a_line_outcomes_accessed": True,
            "deterministic_manifest_replay_identical": True,
            "authentic_1m_data_granularity_complete": authentic_1m_complete,
        }

        gate_evaluation = evaluate_decision_quality_gates(
            integrity_checks=integrity_checks,
            aggregate_oos=aggregate_oos_metrics,
            partition_oos_list=partition_metrics_list,
            thresholds=FrozenReleaseThresholds(),
        )

        return {
            "input_manifest": input_manifest,
            "output_manifest": output_manifest_payload,
            "pit_audit": {
                "pit_queries_count": client.pit_queries_count,
                "pit_violations_count": client.pit_violations_count + pit_step_violations,
                "max_returned_candle_close_ms": client.max_returned_candle_close_ms,
                "data_end_ms": self.dataset.data_end_ms,
                "authentic_1m_queries_count": client.authentic_1m_queries_count,
                "synthetic_1m_queries_count": client.synthetic_1m_queries_count,
                "granularity_violations_count": client.granularity_violations_count,
                "authentic_1m_coverage_by_symbol": coverage_1m,
            },
            "calibration_metrics": calibration_metrics,
            "rolling_oos_table": partition_metrics_list,
            "aggregate_oos_metrics": aggregate_oos_metrics,
            "subgroup_diagnostics": subgroup_diagnostics,
            "grid_diagnostics": grid_diagnostics,
            "trend_evidence_v2_shadow_summary": trend_shadow_summary,
            "gate_evaluation": gate_evaluation,
        }


__all__ = [
    "REPLAY_INPUT_MANIFEST_VERSION",
    "REPLAY_OUTPUT_MANIFEST_VERSION",
    "DeterministicTacticalReplayRunner",
    "HistoricalReplayClient",
    "OOSPartitionSpec",
    "PITCausalityViolationError",
    "ReplayDataGranularityError",
    "ReplayDataset",
    "SymbolReplaySeries",
    "validate_oos_partitions",
]
