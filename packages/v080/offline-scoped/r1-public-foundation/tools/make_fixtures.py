"""Fabricated, deterministic QA only. Never acquires market data or generates research signals."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

from program_c.integrity import WORKSPACE, digest, sha, without, write_json
from program_c.protocol import DAY, HOUR, SEED, load_protocol
from program_c.validation import C_SCHEMA, default_costs, seal_episode

START = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def seal_fact(bar: dict) -> dict:
    bar["fact_sha256"] = digest(without(bar, "fact_sha256"))
    return bar


def fact(start: int, interval: int = 1, symbol: str = "BTCUSDT", prices: tuple = (100, 101, 99, 100)) -> dict:
    end = start + interval * HOUR
    return seal_fact({"symbol": symbol, "price_unit": "USDT_PER_BASE", "open_ms": start, "end_ms": end,
                      "interval_hours": interval, "closed": True, "revision": 0, "source_event_ms": end + 10,
                      "received_ms": end + 20, "available_ms": end + 30, "durable_ms": end + 40,
                      **dict(zip(["open", "high", "low", "close"], prices))})


def make_episode(name: str, review: int, horizon: int = 4, interval: int = 1, length: int = 8,
                 symbol: str = "BTCUSDT") -> dict:
    decision = review - 1000
    row = {
        "strategy_version": "PROGRAM_A_S1_CAUSAL_V1", "symbol": symbol, "direction": "LONG", "regime": "TREND_UP",
        "volatility_bucket": "MEDIUM", "source_path_id": digest(["FABRICATED", name, review]),
        "source_facts": [fact(review - 2 * HOUR, symbol=symbol)],
        "source_manifest_sha256": "", "causal_prefix_sha256": "", "trigger_close_ms": review - HOUR,
        "decision_ms": decision, "scheduled_review_ms": review, "reviewed_ms": review,
        "entry_region": [99.0, 100.0], "structural_stop": 90.0, "volatility_buffer": 1.0, "execution_buffer": 1.0,
        "fixed_preobservable_target_zones": [130.0], "expiry_ms": review + max(2, interval) * HOUR,
        "holding_horizon_hours": horizon, "interval_hours": interval, "price_unit": "USDT_PER_BASE",
        "costs": default_costs(decision), "entry_premise": "CONDITIONAL_ONLY_NOT_A_FILL", "administrative_censor_ms": None,
        "path": [fact(review + i * interval * HOUR, interval, symbol) for i in range(length // interval)],
        "coverage_start_ms": review, "coverage_end_ms": review + length * HOUR, "right_censored": False,
        "source_kind": "SOURCE_SYNTHETIC", "fixture_name": name,
    }
    return seal_episode(row)


def change_bar(row: dict, index: int, prices: tuple) -> None:
    row["path"][index].update(dict(zip(["open", "high", "low", "close"], prices)))
    seal_fact(row["path"][index])


def envelope(rows: list[dict], protocol: dict, controls: list[dict] | None = None, no_setup: int = 2) -> dict:
    all_rows = rows + (controls or [])
    end = max((r["coverage_end_ms"] for r in all_rows), default=START)
    value = {
        "schema_version": C_SCHEMA, "protocol_sha256": protocol["protocol_sha256"], "source_kind": "SOURCE_SYNTHETIC",
        "native_admission": None, "synthetic_manifest": {
            "seed": SEED, "origin": "FABRICATED_QA_NO_MARKET_DATA", "clock": "FABRICATED_2030_UTC",
            "generator_sha256": sha(Path(__file__).read_bytes()),
            "meaning": "Controlled QA geometry and paths, not actual S1 signals or market outcomes",
        },
        "evaluation_asof_ms": end + 1000, "historical_bounded": False, "episodes": rows,
        "control_pool": controls or [], "no_setup_decision_count": no_setup,
    }
    value["export_sha256"] = digest(value)
    return value


def reseal(value: dict) -> dict:
    for row in value["episodes"] + value["control_pool"]:
        seal_episode(row)
    value["export_sha256"] = digest(without(value, "export_sha256"))
    return value


def main() -> None:
    protocol = load_protocol()
    target = WORKSPACE / "fixtures"
    target.mkdir(exist_ok=True)
    entries = []

    def save(name: str, value: dict, outcomes: list[str], validation: str = "VALID") -> None:
        reseal(value)
        path = target / (name + ".json")
        write_json(path, value)
        entries.append({"name": name, "path": str(path.relative_to(WORKSPACE)), "sha256": sha(path.read_bytes()),
                        "expected_validation": validation, "expected_outcomes": outcomes})

    names = ["winning_unambiguous", "stop_first", "precise_time_stop", "unfilled_entry", "delayed_missed_entry",
             "both_hit_same_bar", "entry_exit_order_ambiguous", "missing_interval", "right_censoring",
             "insufficient_horizon", "future_leaking_receipt", "corrected_revision", "overlapping_multi_symbol_shock",
             "fee_spread_stress", "adverse_jump_gap", "cost_unknown", "historical_bounded_embargo", "all_no_setup",
             "open_bar", "duplicate_bars", "stale_observation", "clock_drift", "coverage_4H_24h", "coverage_1D_5d",
             "three_hours_cannot_prove_5d", "native_string_not_authority", "unqualified_source", "late_entry_full_horizon",
             "late_entry_insufficient_horizon", "review_inside_bar"]
    for i, name in enumerate(names):
        review = START + i * 2 * DAY
        row = make_episode(name, review)
        controls = []
        expected, validation = ["TIME_STOP"], "VALID"
        if name in {"winning_unambiguous", "fee_spread_stress", "cost_unknown"}:
            change_bar(row, 1, (100, 131, 99, 100))
            expected = ["TARGET_FIRST"]
        if name == "winning_unambiguous":
            row["path"] += [fact(review + j * HOUR) for j in range(8, 48)]
            row["coverage_end_ms"] = review + 48 * HOUR
            for hours in [12, 24]:
                ctrl_review = review + hours * HOUR
                ctrl = make_episode("timing_control", ctrl_review, length=48 - hours)
                ctrl["source_path_id"] = row["source_path_id"]
                ctrl["source_facts"] = copy.deepcopy([b for b in row["path"] if b["end_ms"] <= ctrl["trigger_close_ms"]])
                ctrl["path"] = copy.deepcopy([b for b in row["path"] if b["open_ms"] >= ctrl_review])
                ctrl["coverage_end_ms"] = row["coverage_end_ms"]
                controls.append(seal_episode(ctrl))
        if name == "stop_first":
            change_bar(row, 1, (100, 101, 89, 91))
            expected = ["STOP_FIRST"]
        if name == "precise_time_stop":
            change_bar(row, 3, (100, 106, 99, 105))
        if name == "unfilled_entry":
            for j in range(8):
                change_bar(row, j, (98, 98.5, 96, 98))
            expected = ["NO_FILL"]
        if name == "delayed_missed_entry":
            row["reviewed_ms"] += HOUR
            change_bar(row, 1, (110, 112, 109, 110))
            expected = ["MISSED_ENTRY"]
        if name == "both_hit_same_bar":
            change_bar(row, 1, (100, 131, 89, 100))
            expected = ["AMBIGUOUS_OHLC_ORDER_UNKNOWN"]
        if name == "entry_exit_order_ambiguous":
            change_bar(row, 0, (98, 131, 98, 100))
            expected = ["AMBIGUOUS_OHLC_ORDER_UNKNOWN"]
        if name == "missing_interval":
            del row["path"][2]
            expected = ["MISSING_COVERAGE"]
        if name in {"right_censoring", "insufficient_horizon", "late_entry_insufficient_horizon"}:
            row["path"] = row["path"][:2 if name != "late_entry_insufficient_horizon" else 4]
            row["coverage_end_ms"] = row["path"][-1]["end_ms"]
            expected = ["INSUFFICIENT_FUTURE_HORIZON"]
            if name == "right_censoring":
                row["right_censored"] = True
                row["administrative_censor_ms"] = row["coverage_end_ms"]
                expected = ["RIGHT_CENSORED"]
        if name == "corrected_revision":
            row["path"][1]["revision"] = 1
            seal_fact(row["path"][1])
            expected, validation = [], "REVISION_REQUIRES_NEW_VERSION"
        if name == "fee_spread_stress":
            row["costs"].update({"taker_fee_each_side_bps": 50.0, "spread_round_trip_bps": 100.0,
                                 "entry_slippage_bps": 100.0, "exit_slippage_bps": 100.0})
        if name == "adverse_jump_gap":
            change_bar(row, 1, (85, 86, 84, 85))
            expected = ["STOP_FIRST"]
        if name == "cost_unknown":
            row["costs"] = None
        if name == "open_bar":
            row["path"][1]["closed"] = False
            seal_fact(row["path"][1])
            expected, validation = [], "OPEN_BAR_FORBIDDEN"
        if name == "duplicate_bars":
            row["path"].insert(2, copy.deepcopy(row["path"][1]))
            expected, validation = [], "DUPLICATE_OR_UNORDERED_BARS"
        if name == "stale_observation":
            row["path"][1].update(available_ms=row["path"][1]["end_ms"] + 300_001,
                                  durable_ms=row["path"][1]["end_ms"] + 300_002)
            seal_fact(row["path"][1])
            expected, validation = [], "STALE_OBSERVATION"
        if name == "clock_drift":
            for j, key in enumerate(["source_event_ms", "received_ms", "available_ms", "durable_ms"]):
                row["path"][1][key] = row["path"][1]["end_ms"] + 1001 + j
            seal_fact(row["path"][1])
            expected, validation = [], "CLOCK_DRIFT"
        if name in {"coverage_4H_24h", "coverage_1D_5d"}:
            interval, horizon, length = (4, 24, 48) if name == "coverage_4H_24h" else (24, 120, 168)
            row = make_episode(name, review, horizon, interval, length)
            change_bar(row, 1, (100, 131, 99, 100))
            expected = ["TARGET_FIRST"]
        if name == "three_hours_cannot_prove_5d":
            row["holding_horizon_hours"] = 120
            row["path"] = row["path"][:3]
            row["coverage_end_ms"] = row["path"][-1]["end_ms"]
            expected = ["INSUFFICIENT_FUTURE_HORIZON"]
        if name in {"late_entry_full_horizon", "late_entry_insufficient_horizon"}:
            change_bar(row, 0, (98, 98.5, 97, 98))
            change_bar(row, 1, (99.5, 101, 99, 100))
        if name == "review_inside_bar":
            row["reviewed_ms"] += 300_000
            expected = ["AMBIGUOUS_OHLC_ORDER_UNKNOWN"]
        rows = [row]
        if name == "all_no_setup":
            rows, expected = [], []
        if name == "overlapping_multi_symbol_shock":
            rows = [row]
            for symbol in ["ETHUSDT", "SOLUSDT"]:
                other = copy.deepcopy(row)
                other["symbol"] = symbol
                for bar in other["source_facts"] + other["path"]:
                    bar["symbol"] = symbol
                    seal_fact(bar)
                rows.append(seal_episode(other))
        value = envelope(rows, protocol, controls, 3 if name == "all_no_setup" else 2)
        if name == "future_leaking_receipt":
            bar = row["path"][1]
            bar["available_ms"] = value["evaluation_asof_ms"] + 100
            bar["durable_ms"] = value["evaluation_asof_ms"] + 110
            seal_fact(bar)
            expected, validation = [], "FUTURE_RECEIPT_AFTER_ASOF"
        if name == "historical_bounded_embargo":
            value["historical_bounded"] = True
            expected, validation = [], "HISTORICAL_BOUNDED_EMBARGO"
        if name in {"native_string_not_authority", "unqualified_source"}:
            value["source_kind"] = "NATIVE_QUALIFIED" if name == "native_string_not_authority" else "NATIVE_UNQUALIFIED"
            for r in value["episodes"]:
                r["source_kind"] = value["source_kind"]
            if name == "native_string_not_authority":
                value["native_admission"] = {"qualified": True, "origin": "FABRICATED_QA_ONLY"}
                expected, validation = [], "NATIVE_ADMISSION_UNAVAILABLE"
            else:
                expected = ["SOURCE_UNQUALIFIED"]
        save(name, value, expected, validation)
    manifest = {"schema_version": "C_FABRICATED_FIXTURE_SUITE_V1", "seed": SEED,
                "protocol_sha256": protocol["protocol_sha256"], "source": "FABRICATED_QA_NO_MARKET_DATA",
                "clock": "FABRICATED_2030_UTC", "fixtures": entries}
    manifest["manifest_sha256"] = digest(manifest)
    write_json(target / "suite.json", manifest)
    print(f"Wrote {len(entries)} fabricated QA fixtures; zero native economic observations")


if __name__ == "__main__":
    main()
