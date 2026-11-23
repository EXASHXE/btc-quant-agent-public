"""B2 market-only contracts and exact numeric helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

D = Decimal
HOUR = 3_600_000
MINUTE = 60_000
VENUE = "BINANCE_USDM_USDT_PERPETUAL"
STRATEGY = "B2_TREND_SETUP_V1"
FEATURES = "B2_EMA_ATR_PIVOT_V1"
ADAPTER = "B2_MARKET_SNAPSHOT_ADAPTER_V1"
CARD = "B2_MARKET_CARD_V1"
RECEIPT = "B2_EVALUATION_RECEIPT_V1"
EPISODE = "B2_SIGNAL_EPISODE_V1"
ACCOUNT = {"account_context_status": "UNAVAILABLE", "account_overlay": "MANUAL_ACCOUNT_CHECK_REQUIRED",
           "portfolio_exposure_limits": "UNKNOWN"}
SYNTHETIC = "SYNTHETIC_QA_ONLY"
RAW_DECIMAL = re.compile(r"[+-]?\d{1,30}(?:\.\d{1,30})?")


class DecisionError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail

    def data(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def check(ok: object, code: str, detail: str = "") -> None:
    if not ok:
        raise DecisionError(code, detail)


def decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not RAW_DECIMAL.fullmatch(value):
        raise DecisionError("INVALID_DECIMAL", field)
    result = D(value)
    check(not positive or result > 0, "INVALID_DECIMAL", field)
    return result


def integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value < 2**63:
        raise DecisionError("INVALID_INTEGER", field)
    return value


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(type(value).__name__)


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_json_default)


def digest(value: object) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


@dataclass(frozen=True)
class Policy:
    holding_hours: int = 6
    expiry_minutes: int = 120
    trigger_minutes: int = 90
    reference_base: Decimal = D("0.100")
    fee_rate: Decimal = D("0.0005")
    slippage_bps: Decimal = D("1.5")
    stop_stress_atr: Decimal = D("0.15")
    funding_stress_rate: Decimal = D("0.00010")
    min_tp1_after_cost_r: Decimal = D("0.80")
    min_obstacle_after_cost_r: Decimal = D("0.85")
    max_basis_bps: Decimal = D("30")
    max_quote_depth_gap_bps: Decimal = D("10")
    max_5m_adverse_atr: Decimal = D("0.65")
    tp_multiples: tuple[Decimal, ...] = (D("1.25"), D("1.85"), D("2.60"))
    exit_fractions: tuple[Decimal, ...] = (D("0.50"), D("0.30"), D("0.20"))

    def __post_init__(self) -> None:
        check(type(self.holding_hours) is int and 2 <= self.holding_hours <= 12, "INVALID_POLICY_HORIZON")
        check(type(self.trigger_minutes) is int and type(self.expiry_minutes) is int
              and 30 <= self.trigger_minutes < self.expiry_minutes <= 240, "INVALID_POLICY_WINDOWS")
        for key, value in asdict(self).items():
            if isinstance(value, Decimal):
                check(value.is_finite() and value >= 0, "INVALID_POLICY_NUMBER", key)
            elif key not in {"holding_hours", "expiry_minutes", "trigger_minutes", "tp_multiples", "exit_fractions"}:
                raise DecisionError("INVALID_POLICY_NUMBER", key)
        check(self.reference_base > 0 and self.fee_rate < 1 and self.funding_stress_rate < 1
              and self.slippage_bps < 10_000 and self.stop_stress_atr > 0, "INVALID_POLICY_COSTS")
        check(len(self.tp_multiples) == len(self.exit_fractions) == 3
              and all(isinstance(x, Decimal) and x.is_finite() and x > 0
                      for x in (*self.tp_multiples, *self.exit_fractions))
              and tuple(sorted(set(self.tp_multiples))) == self.tp_multiples
              and sum(self.exit_fractions) == 1, "INVALID_POLICY_TARGETS")

    def data(self) -> dict[str, Any]:
        return json.loads(encode(asdict(self)))


DEFAULT_POLICY = Policy()


@dataclass(frozen=True)
class Bar:
    open_ms: int
    end_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: dict[str, Any]

    def row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Market:
    symbol: str
    evaluated_ms: int
    cutoff_ms: int
    source: dict[str, Any]
    bars: dict[str, tuple[Bar, ...]]
    context: dict[str, Any]
    warm: bool
