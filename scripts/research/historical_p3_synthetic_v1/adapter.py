"""Artificial BTC experiment with feature-only permits and atomic synthetic publication.

All timestamps are artificial coordinates. No loader or real materialization mode exists.
The new 8h proposal is independent of the frozen R4 feature-only event geometry.
"""

from __future__ import annotations

import hashlib
import itertools
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from scripts.research.historical_tlob_dev.bridge import (
    HOUR,
    KIND,
    PARTITIONS,
    REGISTRATION,
    US,
    canonical,
    clear,
    digest,
    finite,
    hash_string,
    inside,
    publish,
    require,
)
from scripts.research.strategy_eval.costs import SCENARIOS, Outcome, Settlement, economics

TASK = "V065-R6-C-HISTORICAL-P3-ADAPTER-AND-SYNTHETIC-BACKTEST-01"
SCHEMA = "historical-p3.synthetic-only.v1"
SOURCE_METADATA = "5d1e0920d7999a2e21ef7bcf4aa28288c4a5c92bd3514c52983a442f0ef1ee4d"
TRADE_PROPOSAL = "404b66a8bcf2150ffbdcb40557a3e4d46e14dc61cafe5f5c6f0470276583bfa3"
COMPANION_PROPOSAL = "83e8173dd667714c5ca84072c6374fd75a47f8dc4654cfb19d32a2ac36d36666"
HOLDS = (
    "P3_ACCESS_SCOPE_HOLD", "SOURCE_NOT_ADMITTED", "PIT_UNKNOWN", "COST_INCOMPLETE",
    "COST_UNVALIDATED_REAL_FILL", "UTILITY_NOT_IDENTIFIED", "NO_ALPHA_ESTABLISHED",
    "G2_ALPHA_NO_GO", "G4_TESTNET_NO_GO", "LIVE_NO_GO", "REAL_FUNDS_WRITE_NONE",
)
IDENTITY = {"venue": "binance", "product": "USD_M_PERPETUAL", "symbol": "BTCUSDT",
            "oi_field": "sum_open_interest", "oi_unit": "native_base_BTC"}
SCOPE_KEYS = frozenset((
    "schema", "task", "data_kind", "authority", "source_identity", "origin_range",
    "source_envelope", "archive_windows", "exclusions", "protected_dates_complete",
    "private_partition_attestations", "registration_sha256", "metadata_sha256",
    "trade_proposal_sha256", "companion_sha256", "source_sha256", "feature_sha256", "origins",
))


def utc(text: str) -> int:
    return int(datetime.fromisoformat(text).timestamp())


ORIGINS = (utc("2021-04-02T00:00Z"), utc("2021-06-25T00:00Z"))
ENVELOPE = (utc("2021-04-01T00:00Z"), utc("2021-06-26T00:00Z"))


@dataclass(frozen=True)
class Fixture:
    # X row: origin, complete original controls, 4h return, 24h dependency start,
    # content end, artificial known-at. Known-at is NOT a receiver PIT attestation.
    features: tuple
    oi: tuple  # native label, content upper, artificial known-at, base BTC
    opens: tuple  # exact minute timestamp, positive price
    settlements: tuple  # exact settlement timestamp, signed rate, mark
    calendar: tuple  # independently specified, not inferred from observed settlements
    fills: tuple  # origin, CONFIRMED / NO_FILL / PARTIAL / UNKNOWN
    window: tuple
    convention: str = "ARTIFICIAL_POSITIVE_RATE_CREDITS_SHORT"
    data_kind: str = KIND


def artificial_fixture() -> Fixture:
    """Generate a small 2021-coordinate fixture entirely in memory, without input paths."""
    import math

    start, end = ENVELOPE[0], ENVELOPE[0] + 4 * 24 * HOUR

    def price(t):
        h = (t - start) / HOUR
        return 100 * math.exp(-0.001 * h + 0.02 * math.sin(h / 5))

    features = tuple((t, i != 6, -0.012 if i % 5 != 4 else -0.008,
                      t - 60 - 24 * HOUR - 60, t - 120, t - 120)
                     for i, t in enumerate(range(start + 25 * HOUR + 60,
                                                 start + 73 * HOUR + 60, HOUR)))
    # Missing one exact native label creates a separate complete-X denominator.
    missing = features[9][0] - 60 - 600
    oi = tuple((t, t + 300, t + 300,
                1000 * math.exp(0.0015 * (t - start) / HOUR
                                + 0.035 * math.sin((t - start) / HOUR / 8)))
               for t in range(start, end, 300) if t != missing)
    calendar = tuple(range(start, end, 8 * HOUR))
    return Fixture(features, oi, tuple((t, price(t)) for t in range(start, end, 60)),
                   tuple((t, 0.0001 if i % 2 else -0.0002, price(t))
                         for i, t in enumerate(calendar)), calendar,
                   tuple((f[0], "CONFIRMED") for f in features), (start, end))


def fixture_scope(tape: Fixture) -> dict:
    """TEST_ONLY attestations are invented fixture controls, never Owner evidence."""
    return {"schema": SCHEMA, "task": TASK, "data_kind": KIND,
            "authority": "TEST_FIXTURE_ONLY_NOT_OWNER_AUTHORITY", "source_identity": IDENTITY.copy(),
            "origin_range": ORIGINS, "source_envelope": ENVELOPE,
            "archive_windows": [tape.window], "exclusions": [],
            "protected_dates_complete": "TEST_ONLY",
            "private_partition_attestations": {p: {"status": "TEST_ONLY_CONFIRMED",
                "reference": "fixture:" + p, "date_exclusions": []} for p in PARTITIONS},
            "registration_sha256": REGISTRATION, "metadata_sha256": SOURCE_METADATA,
            "trade_proposal_sha256": TRADE_PROPOSAL, "companion_sha256": COMPANION_PROPOSAL,
            "source_sha256": digest(asdict(tape)),
            "feature_sha256": digest([tape.features, tape.oi]),
            "origins": [f[0] for f in tape.features]}


def intervals(value) -> list:
    require(isinstance(value, (list, tuple)), "INTERVALS_REQUIRED")
    for item in value:
        require(isinstance(item, (list, tuple)) and len(item) == 2
                and all(type(t) is int for t in item) and item[0] < item[1], "INTERVAL_INVALID")
    require(list(value) == sorted(value)
            and all(a[1] <= b[0] for a, b in itertools.pairwise(value)), "INTERVAL_ORDER")
    return value


def gate(scope: dict, tape: Fixture, *, verify_source: bool = False) -> None:
    require(type(scope) is dict and scope.get("schema") == SCHEMA
            and scope.get("data_kind") == KIND
            and scope.get("authority") == "TEST_FIXTURE_ONLY_NOT_OWNER_AUTHORITY",
            "REAL_ROUTE_DISABLED")
    require(scope.get("task") == TASK, "TASK_IDENTITY")
    require(type(tape) is Fixture and tape.data_kind == KIND, "SYNTHETIC_FIXTURE_REQUIRED")
    require(set(scope) == SCOPE_KEYS, "UNKNOWN_SCOPE_FIELDS")
    require(scope.get("source_identity") == IDENTITY, "SOURCE_IDENTITY")
    require(scope.get("origin_range") == ORIGINS and scope.get("source_envelope") == ENVELOPE,
            "PROPOSED_2021_ENVELOPE_REQUIRED")
    for key, expected in (("registration_sha256", REGISTRATION), ("metadata_sha256", SOURCE_METADATA),
                          ("trade_proposal_sha256", TRADE_PROPOSAL),
                          ("companion_sha256", COMPANION_PROPOSAL),
                          ("feature_sha256", digest([tape.features, tape.oi]))):
        require(scope.get(key) == expected, "HASH_IDENTITY:" + key)
    require(hash_string(scope.get("source_sha256")), "SOURCE_HASH_REQUIRED")
    if verify_source:
        require(scope["source_sha256"] == digest(asdict(tape)), "HASH_IDENTITY:source_sha256")
    exclusions = intervals(scope.get("exclusions"))
    archives = intervals(scope.get("archive_windows"))
    require(archives and inside(*tape.window, archives), "COMPLETE_ARCHIVE_REQUIRED")
    require(all(inside(a, b, [ENVELOPE]) and clear(a, b, exclusions) for a, b in archives),
            "ARCHIVE_OUTSIDE_SCOPE_OR_PROTECTED")
    attest = scope.get("private_partition_attestations")
    require(scope.get("protected_dates_complete") == "TEST_ONLY"
            and type(attest) is dict and set(attest) == set(PARTITIONS), "PRIVATE_ATTESTATIONS")
    for p, item in attest.items():
        require(type(item) is dict and item.get("status") == "TEST_ONLY_CONFIRMED"
                and item.get("reference") == "fixture:" + p, "PRIVATE_ATTESTATIONS")
        for a, b in intervals(item.get("date_exclusions")):
            require(inside(a, b, exclusions), "PRIVATE_EXCLUSION_NOT_COVERED")
    origins = scope.get("origins")
    require(type(origins) is list and origins and len(origins) <= 84 * 24
            and all(type(t) is int and t % HOUR == 60 and ORIGINS[0] <= t < ORIGINS[1]
                    for t in origins) and origins == sorted(set(origins)), "ORIGIN_SCOPE_CLOCK")
    require(inside(*tape.window, [ENVELOPE]), "FIXTURE_WINDOW")


def feature_masks(scope: dict, tape: Fixture) -> dict:
    """No prices, fills, settlements, rates or marks are consulted in this phase."""
    features = {r[0]: r for r in tape.features}
    stocks = {r[0]: r for r in tape.oi}
    require(len(features) == len(tape.features) and len(stocks) == len(tape.oi), "DUPLICATE_FEATURE")
    rows = []
    for origin in scope["origins"]:
        cutoff = origin - 60
        entry, exit_t = origin + 60, origin + 60 + 8 * HOUR
        # Warmup includes original X controls plus exact 24h OI predecessor.
        left = cutoff - 600 - 24 * HOUR
        covered = (inside(left, exit_t + 1, [tape.window])
                   and clear(left, exit_t + 1, scope["exclusions"]))
        x = features.get(origin)
        x_ok = bool(covered and x and x[1] is True and finite(x[2])
                    and x[3] == cutoff - 24 * HOUR - 60 and x[4] == cutoff - 60
                    and x[4] <= x[5] < cutoff)
        labels = (cutoff - 600, cutoff - 600 - 4 * HOUR, cutoff - 600 - 24 * HOUR)
        oi = [stocks.get(t) for t in labels]
        z_ok = bool(covered and all(r and r[1] == r[0] + 300
                                   and r[1] <= r[2] < cutoff and finite(r[3]) and r[3] > 0
                                   for r in oi))
        z = False
        if z_ok:
            import math
            z = math.log(oi[0][3] / oi[2][3]) >= 0.015 and math.log(oi[0][3] / oi[1][3]) >= -0.005
        rows.append({"origin": origin, "entry": entry, "exit": exit_t,
                     "X_full_eligible": x_ok, "common_eligible": x_ok and z_ok,
                     "X": bool(x_ok and x[2] <= -0.01), "Z": z if z_ok else None,
                     "XZ": bool(x_ok and z_ok and x[2] <= -0.01 and z),
                     "source_reason": "ELIGIBLE" if x_ok and z_ok else
                     "X_MISSING_LATE_OR_SCOPE" if not x_ok else "Z_MISSING_LATE"})
    common = [r["origin"] for r in rows if r["common_eligible"]]
    return {"rows": rows, "X_common": common, "XZ_common": common.copy(),
            "X_full": [r["origin"] for r in rows if r["X_full_eligible"]]}


def code_identity() -> dict:
    root = Path(__file__).resolve().parents[3]
    paths = ("scripts/research/historical_p3_synthetic_v1/adapter.py",
             "scripts/research/historical_tlob_dev/bridge.py",
             "scripts/research/strategy_eval/costs.py",
             "scripts/research/strategy_eval/__init__.py",
             "scripts/research/cross_venue/normalized_sources.py",
             "scripts/research/cross_venue/__init__.py")
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}


@dataclass(frozen=True)
class Permit:
    scope: dict
    masks: dict
    binding: dict

    def verify(self, tape: Fixture) -> None:
        gate(self.scope, tape, verify_source=True)
        require(self.masks == feature_masks(self.scope, tape), "MASK_CHANGED")
        require(self.binding == binding(self.scope, tape, self.masks), "FROZEN_INPUT_CHANGED")


def binding(scope: dict, tape: Fixture, masks: dict) -> dict:
    return {"scope": digest(scope), "source": scope["source_sha256"],
            "features": digest([tape.features, tape.oi]), "masks": digest(masks),
            "X_common_mask": digest(masks["X_common"]),
            "XZ_common_mask": digest(masks["XZ_common"]),
            "X_full_mask": digest(masks["X_full"]), "code": code_identity()}


def phase_one(scope: dict, tape: Fixture) -> Permit:
    """Structural synthetic authorization and pre-outcome mask freeze, no Owner authority."""
    gate(scope, tape)
    masks = feature_masks(scope, tape)
    return Permit(scope, masks, binding(scope, tape, masks))


def synthetic_outcome(tape: Fixture, row: dict) -> dict:
    require(tape.calendar == tuple(range(*tape.window, 8 * HOUR)),
            "ARTIFICIAL_NATIVE_CALENDAR_CHANGED")
    prices = dict(tape.opens)
    fills = dict(tape.fills)
    require(len(prices) == len(tape.opens) and len(fills) == len(tape.fills), "DUPLICATE_EXECUTION")
    fill = fills.get(row["origin"], "UNKNOWN")
    if fill != "CONFIRMED":
        return {"status": "INELIGIBLE" if fill == "NO_FILL" else "UNRESOLVED",
                "reason": "FILL_" + fill, "economics": None}
    if any(not finite(prices.get(t)) or prices[t] <= 0 for t in (row["entry"], row["exit"])):
        return {"status": "INELIGIBLE", "reason": "MISSING_EXACT_ENTRY_OR_EXIT", "economics": None}
    if tape.convention != "ARTIFICIAL_POSITIVE_RATE_CREDITS_SHORT":
        return {"status": "UNRESOLVED", "reason": "FUNDING_CONVENTION_UNKNOWN", "economics": None}
    outcome = Outcome(row["entry"], row["exit"], prices[row["entry"]], prices[row["exit"]],
                      tuple(Settlement(t * US, r, m) for t, r, m in tape.settlements),
                      tuple(t * US for t in tape.calendar), tuple(t * US for t in tape.window))
    values = {c.name: economics(outcome, -1, 8, c) for c in SCENARIOS}
    if any(v["status"] != "RESOLVED" for v in values.values()):
        return {"status": "UNRESOLVED", "reason": next(iter(values.values()))["reason"],
                "economics": None}
    # The shared evaluator uses 1/h sleeves. This experiment is unit nominal, no compounding.
    for value in values.values():
        for key in ("capital_sleeve", "sleeve_pnl", "turnover"):
            value.pop(key)
        value["funding_credit"] = -value.pop("funding_debit")
        value["turnover"] = 1 + outcome.exit_price / outcome.entry_price
    return {"status": "RESOLVED", "reason": "ARTIFICIAL_CONFIRMED_FILL", "economics": values}


def metrics(ledger: list, start: int, end: int) -> dict:
    trades = [r for r in ledger if r["status"] == "RESOLVED"]
    summary = {}
    for scenario in SCENARIOS:
        values = [r["economics"][scenario.name] for r in trades]
        nets = [v["net_return"] for v in values]
        wins, losses = [v for v in nets if v > 0], [v for v in nets if v < 0]
        equity = peak = 1.0
        dd = 0.0
        for net in nets:
            equity += net
            peak = max(peak, equity)
            dd = max(dd, peak - equity)
        mean_win = sum(wins) / len(wins) if wins else None
        mean_loss = sum(losses) / len(losses) if losses else None
        totals = {k: sum(v[k] for v in values) for k in
                  ("gross_return", "net_return", "entry_fee", "exit_fee", "entry_spread",
                   "exit_spread", "entry_slippage", "exit_slippage", "funding_credit", "turnover")}
        summary[scenario.name] = {**totals, "wins": len(wins), "losses": len(losses),
            "mean_win": mean_win, "mean_loss": mean_loss,
            "payoff_ratio": mean_win / -mean_loss if wins and losses else None,
            "profit_factor": sum(wins) / -sum(losses) if losses else None,
            "expectancy": sum(nets) / len(nets) if nets else None,
            "drawdown_initial_equity_units_realized_only": dd,
            "drawdown_intratrade": "NOT_COMPUTED_NO_MARK_TO_MARKET_LEDGER"}
    occupied = [r for r in ledger if r.get("capital_reserved")]
    hours = sum((r["exit"] - r["entry"]) / HOUR for r in occupied)
    blocks = sorted({r["entry"] // (24 * HOUR) for r in trades})
    return {"scenarios": summary, "resolved_trades": len(trades),
            "aggregate_status": "PARTIAL_RESOLVED_SUBSET" if any(
                r["status"] in ("INELIGIBLE", "UNRESOLVED") for r in ledger) else "RESOLVED",
            "sum_interpretation": "RESOLVED_TRADES_ONLY_NOT_IMPUTED_FULL_POPULATION_PNL",
            "exposure_hours": hours, "exposure_fraction": hours * HOUR / (end - start),
            "max_concurrent_positions": int(bool(occupied)), "effective_events": len(trades),
            "effective_calendar_day_blocks": len(blocks),
            "event_calendar_block_uncertainty": "DESCRIPTIVE_ONLY_NO_INFERENCE_OR_ALPHA",
            "year_regime": {"2021": {"resolved_trades": len(trades),
                                    "regime": "ARTIFICIAL_ONLY_NO_HISTORICAL_REGIME_LABEL"}},
            "missingness": dict(Counter(r["reason"] for r in ledger
                                         if r["status"] in ("INELIGIBLE", "UNRESOLVED")))}


@dataclass
class Run:
    permit: Permit
    tape: Fixture
    result: dict
    result_sha256: str

    def verify(self) -> None:
        self.permit.verify(self.tape)
        require(digest(self.result) == self.result_sha256, "RESULT_CHANGED")
        require(self.result == phase_two(self.permit, self.tape).result, "RESULT_NOT_DERIVED")


def phase_two(permit: Permit, tape: Fixture) -> Run:
    """Evaluate only the explicit artificial tape; real P3 remains unimplemented/disabled."""
    permit.verify(tape)
    arms = {}
    for arm in ("X_common", "XZ_common", "X_full"):
        ledger, busy_until = [], 0
        for row in permit.masks["rows"]:
            event = {**row, "capital_reserved": False, "economics": None}
            eligible = row["X_full_eligible"] if arm == "X_full" else row["common_eligible"]
            if not eligible:
                event.update(status="SOURCE_INELIGIBLE", reason=row["source_reason"])
            elif not row["XZ" if arm == "XZ_common" else "X"]:
                event.update(status="NO_ACTION", reason="VALID_NO_SIGNAL")
            elif row["entry"] < busy_until:
                event.update(status="IGNORED_CAPITAL", reason="SAME_ARM_POSITION_OPEN")
            else:
                event.update(synthetic_outcome(tape, row))
                # A confirmed fill with unknown exit/funding holds capital to the fixed exit;
                # unknown/partial entry conservatively reserves the full unit too.
                event["capital_reserved"] = event["reason"] not in ("FILL_NO_FILL",) and (
                    event["reason"] != "MISSING_EXACT_ENTRY_OR_EXIT"
                    or dict(tape.opens).get(row["entry"]) is not None)
                if event["capital_reserved"]:
                    busy_until = row["exit"]
            ledger.append(event)
        arms[arm] = {"eligible_origins": permit.masks[arm],
                     "eligible_denominator": len(permit.masks[arm]), "ledger": ledger,
                     "status_counts": dict(Counter(r["status"] for r in ledger)),
                     "metrics": metrics(ledger, ORIGINS[0], ORIGINS[1])}
    result = {"schema": SCHEMA, "task": TASK, "data_kind": KIND,
              "interpretation": "SYNTHETIC_PERFORMANCE_NOT_HISTORICAL_NET_PNL",
              "pre_outcome_bindings": permit.binding, "arms": arms, "holds": HOLDS,
              "exposure_denominator": "PROPOSED_84_DAY_ORIGIN_WINDOW",
              "fixture_coverage_seconds": tape.window[1] - tape.window[0],
              "outcome_authorized": False, "real_route_enabled": False,
              "real_source_payload_reads": 0, "real_pnl_computed": False}
    return Run(permit, tape, result, digest(result))


def run_fixture() -> Run:
    tape = artificial_fixture()
    return phase_two(phase_one(fixture_scope(tape), tape), tape)


def replay(output: Path) -> None:
    require((output / "synthetic_panel.json").read_bytes() == canonical(run_fixture().result),
            "SYNTHETIC_REPLAY_MISMATCH")


__all__ = ["phase_one", "phase_two", "publish", "replay", "run_fixture"]
