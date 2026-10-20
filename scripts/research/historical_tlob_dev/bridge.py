"""Proposed historical transaction controls exercised exclusively on generated fixtures.

No market-source loader, real Owner-scope verifier, or real evaluation entry point exists
here. Fixture attestations are not Owner decisions. The artificial trade policy is not
the candidate's missing primary execution/exit contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from scripts.research.bline_r4_novel.adapter import evaluate_origin_feature
from scripts.research.cross_venue.normalized_sources import directory_fd, published_file
from scripts.research.strategy_eval.costs import CostAssumptions, Outcome, Settlement, economics

KIND = "TEST_ONLY_SYNTHETIC"
SCOPE_SCHEMA = "historical-tlob-dev.synthetic-scope.v1"
REGISTRATION = "62332f599cb1a643cb1575c6b7b4aaebe174dbe7daffe21d0f903fc50092eacc"
PARTITIONS = ("A_LINE", "FINAL_HOLDOUT", "FORWARD", "OOS", "H41")
HOLDS = (
    "P3_ACCESS_SCOPE_HOLD", "SOURCE_NOT_ADMITTED", "PIT_UNKNOWN", "COST_INCOMPLETE",
    "UTILITY_NOT_IDENTIFIED", "NO_ALPHA_ESTABLISHED", "G2_ALPHA_NO_GO", "G4_TESTNET_NO_GO",
    "LIVE_NO_GO", "REAL_FUNDS_WRITE_NONE",
)
HOUR = 3600
US = 1_000_000


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def integer(value: Any) -> bool:
    return type(value) is int


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def ranges(value: Any) -> list[tuple[int, int]]:
    require(type(value) is list and 0 < len(value) <= 32, "EXACT_RANGES_REQUIRED")
    for item in value:
        require(type(item) in (list, tuple) and len(item) == 2
                and all(integer(t) for t in item) and item[0] < item[1], "UTC_SECONDS_REQUIRED")
    result = sorted(tuple(r) for r in value)
    require(all(a[1] <= b[0] for a, b in pairwise(result)), "OVERLAPPING_RANGES")
    return result


def inside(left: int, right: int, windows: list) -> bool:
    return any(a <= left < right <= b for a, b in windows)


def clear(left: int, right: int, exclusions: list) -> bool:
    return not any(max(left, a) < min(right, b) for a, b in exclusions)


def hash_string(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def gate(scope: dict | None, policy: dict) -> None:
    """Reject missing/real/unattested scope before even generating synthetic source rows."""
    require(type(scope) is dict, "SCOPE_REQUIRED_REAL_ACCESS_DISABLED")
    require(scope.get("schema") == SCOPE_SCHEMA and scope.get("data_kind") == KIND,
            "REAL_ACCESS_DISABLED")
    require(scope.get("fixture_attestation") == "TEST_FIXTURE_ONLY_NOT_OWNER_AUTHORITY",
            "UNATTESTED_FIXTURE")
    require(scope.get("source_identity") == {
        "venue": "binance", "product": "USD_M_PERPETUAL", "symbol": "BTCUSDT",
        "oi_field": "sum_open_interest", "oi_unit": "native_base_BTC",
    }, "SOURCE_MAPPING_MISMATCH")
    require(scope.get("registration_sha256") == REGISTRATION, "REGISTRATION_HASH_MISMATCH")
    require(scope.get("fold_binding") == "NOT_APPLICABLE_DETERMINISTIC_NO_FIT",
            "FITTED_FOLD_BINDING_FORBIDDEN")
    require(integer(scope.get("year")) and scope["year"] in range(2021, 2025)
            and integer(scope.get("seed")) and 0 <= scope["seed"] <= 1000, "FIXTURE_IDENTITY")
    for key in ("source_sha256", "feature_sha256"):
        require(hash_string(scope.get(key)), "INPUT_HASH_REQUIRED")
    for key in ("archive_windows", "feature_windows", "label_windows", "origin_ranges"):
        ranges(scope.get(key))
    exclusions = ranges(scope.get("exclusions"))
    attestations = scope.get("private_partition_attestations")
    require(type(attestations) is dict and set(attestations) == set(PARTITIONS),
            "PRIVATE_PARTITIONS_REQUIRED")
    for item in attestations.values():
        require(type(item) is dict and item.get("status") == "TEST_ONLY_CONFIRMED"
                and isinstance(item.get("reference"), str) and item["reference"].startswith("fixture:")
                and type(item.get("date_exclusions")) is list, "PRIVATE_ATTESTATION_REQUIRED")
        if item["date_exclusions"]:
            for a, b in ranges(item["date_exclusions"]):
                require(inside(a, b, exclusions), "PRIVATE_EXCLUSION_NOT_COVERED")
    for a, b in scope["archive_windows"]:
        require(clear(a, b, exclusions), "FULL_ARCHIVE_PROTECTED_OVERLAP")
    origins = scope.get("origins")
    require(type(origins) is list and 0 < len(origins) <= 1000
            and all(integer(t) and t % HOUR == 60 and inside(t, t + 1, scope["origin_ranges"])
                    for t in origins), "ORIGIN_SCOPE_OR_CLOCK")
    require(policy.get("schema") == "historical-tlob-dev.fixture-trade.v1"
            and policy.get("purpose") == "TEST_POLICY_ONLY_NOT_PRIMARY_CONTRACT"
            and integer(policy.get("direction")) and policy["direction"] == -1
            and integer(policy.get("leverage")) and policy["leverage"] == 1,
            "FIXTURE_TRADE_POLICY_REQUIRED")
    require(integer(policy.get("delay_s")) and policy["delay_s"] >= 60
            and integer(policy.get("holding_h")) and policy["holding_h"] in (4, 8, 12, 24)
            and policy.get("exit") == "FIXED_TIME_NO_STOP_NO_TARGET", "FIXTURE_ENTRY_EXIT_REQUIRED")
    require(integer(policy.get("max_concurrent")) and 1 <= policy["max_concurrent"] <= 64
            and finite(policy.get("allocation")) and finite(policy.get("capital_cap"))
            and 0 < policy["allocation"] <= policy["capital_cap"] <= 1, "CAPITAL_MODEL_INVALID")
    require(policy.get("entry_order") in ("maker", "taker")
            and policy.get("exit_order") in ("maker", "taker")
            and policy.get("fills") == "ARTIFICIAL_CONFIRMED_FIXTURE_FILLS", "FILL_POLICY_REQUIRED")
    require(type(policy.get("fee_bp")) is dict and set(policy["fee_bp"]) == {"maker", "taker"}
            and all(finite(v) and v >= 0 for v in policy["fee_bp"].values()), "FEE_MODEL_INVALID")
    require(all(finite(policy.get(k)) and policy[k] >= 0 for k in ("spread_bp", "slippage_bp")),
            "COST_MODEL_INVALID")


@dataclass(frozen=True)
class Tape:
    """Only the deterministic generator below creates this in the supported API."""

    features: tuple  # origin, X4h, original-style 24h dependency start, end, known-at
    oi: tuple  # exact label, content upper bound, known-at, native base OI
    opens: tuple  # execution timestamp, artificial opening price
    settlements: tuple  # settlement UTC seconds, signed rate, mark
    funding_calendar: tuple  # independent fixture calendar, including missing observations
    window: tuple
    data_kind: str = KIND


def synthetic_tape(year: int, seed: int) -> Tape:
    """Generate all values locally; no path, data loader, network or account parameter."""
    start = int(datetime(year, 1, 1, tzinfo=UTC).timestamp())
    end = start + 96 * HOUR

    def price(t):
        h = (t - start) / HOUR
        return 100 * math.exp(-0.003 * h + 0.035 * math.sin(h / 4 + seed / 10))

    features = tuple((t, math.log(price(t - 120) / price(t - 120 - 4 * HOUR)),
                      t - 60 - 24 * HOUR - 60, t - 120, t - 120)
                     for t in range(start + 26 * HOUR + 60, start + 50 * HOUR + 60, HOUR))
    oi = tuple((t, t + 300, t + 300,
                1000 * math.exp(0.001 * ((t - start) / HOUR)
                                + 0.015 * math.sin((t - start) / HOUR / 8 + 1)))
               for t in range(start, end, 300))
    opens = tuple((t, price(t)) for t in range(start, end, 60))
    calendar = tuple(range(start, end + 1, 8 * HOUR))
    funding = tuple((t, 0.0001 if i % 2 else -0.0002, price(t))
                    for i, t in enumerate(calendar))
    return Tape(features, oi, opens, funding, calendar, (start, end))


def fixture(year: int = 2021, seed: int = 7) -> tuple[dict, dict]:
    require(integer(year) and year in range(2021, 2025)
            and integer(seed) and 0 <= seed <= 1000, "FIXTURE_IDENTITY")
    tape = synthetic_tape(year, seed)
    start, end = tape.window
    scope = {
        "schema": SCOPE_SCHEMA, "data_kind": KIND,
        "fixture_attestation": "TEST_FIXTURE_ONLY_NOT_OWNER_AUTHORITY",
        "source_identity": {"venue": "binance", "product": "USD_M_PERPETUAL", "symbol": "BTCUSDT",
                            "oi_field": "sum_open_interest", "oi_unit": "native_base_BTC"},
        "registration_sha256": REGISTRATION, "fold_binding": "NOT_APPLICABLE_DETERMINISTIC_NO_FIT",
        "year": year, "seed": seed,
        "archive_windows": [[start, end]], "feature_windows": [[start, end]],
        "label_windows": [[start, end]], "origin_ranges": [[start, end]],
        "exclusions": [[end + HOUR, end + 2 * HOUR]],
        "private_partition_attestations": {p: {"status": "TEST_ONLY_CONFIRMED",
            "reference": "fixture:" + p, "date_exclusions": []} for p in PARTITIONS},
        "origins": [r[0] for r in tape.features], "source_sha256": digest(asdict(tape)),
        "feature_sha256": digest([tape.features, tape.oi]),
    }
    policy = {
        "schema": "historical-tlob-dev.fixture-trade.v1",
        "purpose": "TEST_POLICY_ONLY_NOT_PRIMARY_CONTRACT", "direction": -1, "leverage": 1,
        "delay_s": 60, "holding_h": 4, "exit": "FIXED_TIME_NO_STOP_NO_TARGET",
        "allocation": 0.4, "capital_cap": 0.8, "max_concurrent": 2,
        "fee_bp": {"maker": 1.0, "taker": 5.0}, "entry_order": "taker", "exit_order": "taker",
        "spread_bp": 1.0, "slippage_bp": 2.0, "fills": "ARTIFICIAL_CONFIRMED_FIXTURE_FILLS",
    }
    return scope, policy


def plan(scope: dict, policy: dict, tape: Tape) -> list[dict]:
    features = {r[0]: r for r in tape.features}
    require(len(features) == len(tape.features), "DUPLICATE_FEATURE_ORIGIN")
    oi = {r[0]: r for r in tape.oi}
    prices = dict(tape.opens)
    require(len(oi) == len(tape.oi) and len(prices) == len(tape.opens), "DUPLICATE_SOURCE_TIME")
    result = []
    for t in sorted(set(scope["origins"])):
        cutoff = t - 60
        entry = t + policy["delay_s"]
        exit_t = entry + policy["holding_h"] * HOUR
        row = {"origin": t, "entry": entry, "exit": exit_t, "eligible": False,
               "X": False, "TLOB": False, "reason": "FEATURE_WINDOW"}
        result.append(row)
        left = cutoff - 24 * HOUR - 600
        if not (inside(left, cutoff, scope["feature_windows"])
                and clear(left, exit_t + 1, scope["exclusions"])):
            continue
        f = features.get(t)
        labels = [cutoff - 600, cutoff - 600 - 24 * HOUR, cutoff - 600 - 4 * HOUR]
        stocks = [oi.get(label) for label in labels]
        if (f is None or not finite(f[1]) or f[2] != cutoff - 24 * HOUR - 60
                or f[3] != cutoff - 60 or not f[3] <= f[4] < cutoff
                or any(s is None or s[1] != s[0] + 300 or not s[1] <= s[2] < cutoff
                       or not finite(s[3]) or s[3] <= 0 for s in stocks)):
            row["reason"] = "FEATURE_MISSING_OR_LATE"
            continue
        flags = evaluate_origin_feature(t, {"x_eligible": True, "log_return_4h": f[1]},
                                        {s[0] * US: s[3] for s in stocks}, {}, REGISTRATION)
        if not inside(entry, exit_t + 1, scope["label_windows"]):
            row["reason"] = "EXIT_WINDOW"
            continue
        if any(not finite(prices.get(stamp)) or prices[stamp] <= 0 for stamp in (entry, exit_t)):
            row["reason"] = "MISSING_EXECUTION_PRICE"
            continue
        expected = [s for s in tape.funding_calendar if entry < s <= exit_t]
        actual = [s[0] for s in tape.settlements if entry < s[0] <= exit_t]
        if (actual != expected or any(not finite(r) or not finite(m) or m <= 0
                                     for stamp, r, m in tape.settlements if entry < stamp <= exit_t)):
            row["reason"] = "MISSING_FUNDING"
            continue
        row.update(eligible=True, X=flags["paired_baseline_action"] == "SHORT",
                   TLOB=flags["trigger"], reason="PAIRED_ELIGIBLE")
    return result


def bindings(scope: dict, policy: dict, tape: Tape, mask: list) -> dict:
    repo = Path(__file__).resolve().parents[3]
    code = {}
    for file in (
        "scripts/research/historical_tlob_dev/bridge.py",
        "scripts/research/bline_r4_novel/adapter.py",
        "scripts/research/bline_r4_novel/contracts.py",
        "scripts/research/bline_multiyear/contracts.py",
        "scripts/research/strategy_eval/costs.py",
        "scripts/research/strategy_eval/__init__.py",
        "scripts/research/cross_venue/normalized_sources.py",
    ):
        with published_file(repo / file, 1024**2) as stream:
            code[file] = hashlib.sha256(stream.read()).hexdigest()
    return {"scope_sha256": digest(scope), "policy_sha256": digest(policy),
            "source_sha256": digest(asdict(tape)),
            "feature_sha256": digest([tape.features, tape.oi]), "sample_mask_sha256": digest(mask),
            "registration_sha256": REGISTRATION, "code_sha256": code}


@dataclass
class Run:
    scope: dict
    policy: dict
    tape: Tape
    mask: list
    freeze: dict
    result: dict
    result_sha256: str

    def verify(self) -> None:
        gate(self.scope, self.policy)
        require(bindings(self.scope, self.policy, self.tape, self.mask) == self.freeze,
                "FROZEN_INPUT_CHANGED")
        require(plan(self.scope, self.policy, self.tape) == self.mask, "SAMPLE_MASK_CHANGED")
        require(digest(self.result) == self.result_sha256, "RESULT_CHANGED")


def simulate(scope: dict | None, policy: dict) -> Run:
    gate(scope, policy)
    tape = synthetic_tape(scope["year"], scope["seed"])
    require(type(tape) is Tape and tape.data_kind == KIND, "SYNTHETIC_TAPE_REQUIRED")
    require(digest(asdict(tape)) == scope["source_sha256"], "SOURCE_HASH_MISMATCH")
    require(digest([tape.features, tape.oi]) == scope["feature_sha256"], "FEATURE_HASH_MISMATCH")
    require(inside(*tape.window, scope["archive_windows"]), "COMPLETE_ARCHIVE_WINDOW_REQUIRED")
    require(list(tape.funding_calendar) == sorted(set(tape.funding_calendar))
            and all(integer(t) and tape.window[0] <= t <= tape.window[1]
                    for t in tape.funding_calendar), "FUNDING_CALENDAR_INVALID")
    require([s[0] for s in tape.settlements] == sorted({s[0] for s in tape.settlements}),
            "FUNDING_CHRONOLOGY_INVALID")
    mask = plan(scope, policy, tape)
    frozen = bindings(scope, policy, tape, mask)  # Before any return/cost arithmetic.
    prices = dict(tape.opens)
    assumptions = CostAssumptions("SYNTHETIC_ASSUMED_CONFIRMED_FILLS",
        policy["fee_bp"][policy["entry_order"]], policy["fee_bp"][policy["exit_order"]],
        policy["spread_bp"], policy["spread_bp"], policy["slippage_bp"], policy["slippage_bp"])
    arms = {}
    for arm in ("X", "TLOB"):
        active, trades, rejected = [], [], []
        for row in mask:
            if not row["eligible"] or not row[arm]:
                continue
            active = [t for t in active if t > row["entry"]]
            if (len(active) >= policy["max_concurrent"]
                    or (len(active) + 1) * policy["allocation"] > policy["capital_cap"] + 1e-12):
                rejected.append(row["origin"])
                continue
            outcome = Outcome(row["entry"], row["exit"], prices[row["entry"]], prices[row["exit"]],
                tuple(Settlement(t * US, r, m) for t, r, m in tape.settlements),
                tuple(t * US for t in tape.funding_calendar), tuple(t * US for t in tape.window))
            # Shared arithmetic for already confirmed artificial fills. This does not infer
            # any real maker fill; native economics(maker=True) remains unchanged/unresolved.
            costs = economics(outcome, -1, policy["holding_h"], assumptions)
            require(costs["status"] == "RESOLVED", "SYNTHETIC_COST_UNRESOLVED")
            # Native P1 allocation is not this fixture's capital model.
            for key in ("capital_sleeve", "sleeve_pnl", "turnover"):
                costs.pop(key)
            active.append(row["exit"])
            trades.append({"origin": row["origin"], "entry": row["entry"], "exit": row["exit"],
                "allocation": policy["allocation"], "concurrent_after_entry": len(active),
                "artificial_accounting": costs,
                "initial_capital_return": costs["net_return"] * policy["allocation"]})
        arms[arm] = {"eligible_origins": [r["origin"] for r in mask if r["eligible"]],
                     "valid_no_signal_origins": [r["origin"] for r in mask if r["eligible"] and not r[arm]],
                     "synthetic_trades": trades, "capital_rejected_origins": rejected}
    result = {"schema": "historical-tlob-dev.synthetic-panel.v1", "data_kind": KIND,
              "freeze": frozen, "freeze_sha256": digest(frozen), "sample_mask": mask, "arms": arms,
              "duplicate_origins_removed": len(scope["origins"]) - len(set(scope["origins"])),
              "real_outcome_payload_reads": 0, "real_labels_materialized": 0,
              "real_pnl_computed": False, "outcome_authorized": False, "holds": HOLDS}
    run = Run(scope, policy, tape, mask, frozen, result, digest(result))
    run.verify()
    return run


def publish(run: Run, output: Path, *, before_revalidation=None) -> None:
    """Exclusive synthetic transaction; existing output roots are never reused."""
    output = Path(output).absolute()
    require(not os.path.lexists(output) and all(not p.is_symlink() for p in output.parents),
            "FRESH_OUTPUT_REQUIRED")
    run.verify()
    raw = canonical(run.result)
    stage_name, final_name = ".synthetic-panel.stage", "synthetic_panel.json"
    output.mkdir(mode=0o700)
    with directory_fd(output) as directory:
        try:
            fd = os.open(stage_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                info = os.fstat(stream.fileno())
                identity = (info.st_dev, info.st_ino)
            if before_revalidation is not None:
                before_revalidation(output / stage_name)
            run.verify()
            with published_file(output / stage_name, len(raw)) as stream:
                info = os.fstat(stream.fileno())
                require((info.st_dev, info.st_ino) == identity, "STAGED_IDENTITY_CHANGED")
                require(stream.read() == raw, "STAGED_HASH_MISMATCH")
            with directory_fd(output) as current:
                a, c = os.fstat(directory), os.fstat(current)
                require((a.st_dev, a.st_ino) == (c.st_dev, c.st_ino), "OUTPUT_DIRECTORY_CHANGED")
            # Atomic publication without replacing a concurrently created file.
            os.link(stage_name, final_name, src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False)
        finally:
            try:
                os.unlink(stage_name, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.fsync(directory)


def verify_publication(output: Path, year: int, seed: int) -> None:
    """Independent deterministic replay; accept only the expected synthetic fixture bytes."""
    scope, policy = fixture(year, seed)
    expected = canonical(simulate(scope, policy).result)
    path = Path(output) / "synthetic_panel.json"
    with published_file(path, max(len(expected), 1)) as stream:
        require(stream.read() == expected, "SYNTHETIC_REPLAY_MISMATCH")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("demo", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--year", type=int, choices=range(2021, 2025), default=2021)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    if args.command == "demo":
        scope, policy = fixture(args.year, args.seed)
        publish(simulate(scope, policy), args.output_dir)
    else:
        verify_publication(args.output_dir, args.year, args.seed)
    print(f"{KIND}: {args.command} PASS; real outcomes=0; P3_ACCESS_SCOPE_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
