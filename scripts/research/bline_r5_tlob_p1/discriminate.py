"""Compare frozen TLOB with its paired X; explicitly stop unavailable P1 tests."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

BASELINE = "39a68a1c8b3490a5a3826d2fab6a7e3f0e441dc2"
REGISTRATION = "62332f599cb1a643cb1575c6b7b4aaebe174dbe7daffe21d0f903fc50092eacc"
MANIFEST = "34f03cd1f267684ffa3eb9980573df36256b5ddded9d213cd0472b6a1eb158d5"
START, END = 1609459200, 1735689600
HOUR, US = 3600, 1_000_000
LABELS = [
    "P3_ACCESS_SCOPE_HOLD", "SOURCE_NOT_ADMITTED", "PIT_UNKNOWN", "COST_INCOMPLETE",
    "UTILITY_NOT_IDENTIFIED", "NO_ALPHA_ESTABLISHED", "G2_ALPHA_NO_GO",
    "G4_TESTNET_NO_GO", "LIVE_NO_GO", "REAL_FUNDS_WRITE_NONE",
]
KEYS = {
    "action", "archive_sha256", "base_open_interest", "content_upper_us", "cutoff", "cutoff_us",
    "delta_log_oi_24h", "delta_log_oi_4h", "expected_native_label_us", "log_return_4h",
    "no_action_reasons", "origin_utc", "paired_baseline_action", "paired_xz_eligible",
    "pred_24h_base_open_interest", "pred_24h_label_us", "pred_4h_base_open_interest",
    "pred_4h_label_us", "receiver_pit", "registration_sha256", "source_status", "t", "trigger",
    "x_condition", "x_eligible", "z_condition", "z_eligible",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def frozen_hashes(root):
    """Pin the manifest itself before trusting its fourteen explicit file names."""
    require(digest(root / "manifest.json") == MANIFEST, "R4_MANIFEST_IDENTITY")
    manifest = json.loads((root / "manifest.json").read_text())
    require(len(manifest["outputs"]) == 14, "R4_OUTPUT_COUNT")
    result = {"manifest.json": MANIFEST}
    for name, entry in manifest["outputs"].items():
        require(Path(name).name == name, "UNSAFE_MANIFEST_PATH")
        path = root / name
        require(not path.is_symlink(), "SYMLINK_INPUT")
        actual = digest(path)
        require(actual == entry["sha256"], f"R4_FREEZE_CHANGED:{name}")
        require(path.stat().st_size == entry["bytes"], "R4_SIZE_CHANGED")
        result[name] = actual
    require(result["exploratory_registration.v1.json"] == REGISTRATION, "R4_REGISTRATION")
    return result


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def validate_row(r):
    """Reject extra content and recompute every saved decision from original fields."""
    require(set(r) == KEYS, "FEATURE_SCHEMA_ONLY")
    t = r["t"]
    require(type(t) is int and START <= t < END and t % HOUR == 60, "BOUNDED_ORIGIN")
    require(r["registration_sha256"] == REGISTRATION, "ROW_FREEZE_IDENTITY")
    cutoff = t - 60
    require(r["cutoff"] == cutoff and r["cutoff_us"] == cutoff * US, "CUTOFF_UNITS")
    require(datetime.fromisoformat(r["origin_utc"]).timestamp() == t, "ORIGIN_UTC")
    label = (cutoff - 600) * US
    require(r["expected_native_label_us"] == label, "OI_LABEL_CLOCK")
    require(r["content_upper_us"] == label + 300 * US < cutoff * US, "OI_CONTENT_CLOCK")
    require(r["pred_24h_label_us"] == label - 24 * HOUR * US, "PREDECESSOR_24H")
    require(r["pred_4h_label_us"] == label - 4 * HOUR * US, "PREDECESSOR_4H")
    require(r["receiver_pit"] == "PIT_UNKNOWN", "PIT_LABEL")
    require(r["source_status"] == "SOURCE_NOT_ADMITTED", "SOURCE_LABEL")
    for key in ("x_eligible", "z_eligible", "paired_xz_eligible", "x_condition",
                "z_condition", "trigger"):
        require(type(r[key]) is bool, "BOOLEAN_FLAG")
    values = [r[k] for k in ("base_open_interest", "pred_24h_base_open_interest",
                             "pred_4h_base_open_interest")]
    require(all(v is None or (finite(v) and v > 0) for v in values), "INVALID_OI")
    require(all(v is None or START * US <= stamp < END * US for v, stamp in zip(
        values, (label, r["pred_24h_label_us"], r["pred_4h_label_us"]))), "BOUNDED_NATIVE_VALUE")
    zok = all(v is not None for v in values)
    require(zok == r["z_eligible"], "Z_MISSINGNESS")
    if zok:
        d24, d4 = math.log(values[0] / values[1]), math.log(values[0] / values[2])
        require(r["delta_log_oi_24h"] == d24 and r["delta_log_oi_4h"] == d4, "OI_REPLAY")
        z = d24 >= 0.015 and d4 >= -0.005
    else:
        require(r["delta_log_oi_24h"] is None and r["delta_log_oi_4h"] is None, "NO_IMPUTATION")
        z = False
    require((finite(r["log_return_4h"]) if r["x_eligible"] else
             r["log_return_4h"] is None), "X_MISSINGNESS")
    x = r["x_eligible"] and r["log_return_4h"] <= -0.01
    paired = r["x_eligible"] and zok
    trigger = paired and x and z
    require((r["x_condition"], r["z_condition"], r["paired_xz_eligible"], r["trigger"])
            == (x, z, paired, trigger), "ORIGINAL_RULE_REPLAY")
    require(r["action"] == ("SHORT" if trigger else "NO_ACTION"), "TLOB_ACTION")
    require(r["paired_baseline_action"] == ("SHORT" if paired and x else "NO_ACTION"),
            "PAIRED_X_ACTION")


def load_panel(root):
    frozen_hashes(root)
    rows, seen = [], set()
    with (root / "feature_panel.jsonl").open() as stream:
        for line in stream:
            r = json.loads(line)
            validate_row(r)
            require(r["t"] not in seen, "DUPLICATE_ORIGIN")
            seen.add(r["t"])
            rows.append(r)
    require([r["t"] for r in rows] == list(range(START + HOUR + 60, END, HOUR)),
            "FROZEN_SCHEDULE")
    return rows


def episodes(times):
    """Original fixed 8h greedy half-open calendar, independently for each arm."""
    starts = []
    for t in sorted(set(times)):
        if not starts or t >= starts[-1] + 8 * HOUR:
            starts.append(t)
    return starts


def intersection(a, b):
    a, b = set(a), set(b)
    return {"both": len(a & b), "tlob_only": len(a - b), "x_only": len(b - a),
            "union": len(a | b), "jaccard": len(a & b) / len(a | b) if a | b else None}


def counts(rows):
    paired = [r for r in rows if r["paired_xz_eligible"]]
    a = {r["t"] for r in paired if r["trigger"]}
    b = {r["t"] for r in paired if r["x_condition"]}
    return {"scheduled": len(rows), "x_eligible": sum(r["x_eligible"] for r in rows),
            "z_eligible": sum(r["z_eligible"] for r in rows), "matched": len(paired),
            "x_events": len(b), "tlob_events": len(a), "tlob_no_action": len(paired) - len(a),
            "scheduled_tlob_no_action": len(rows) - len(a),
            "x_episodes_8h": len(episodes(b)), "tlob_episodes_8h": len(episodes(a)),
            "tlob_density_per_48_eligible_hours": len(episodes(a)) * 48 / len(paired)
            if paired else None}


def analyze(rows):
    seen = set()
    for row in rows:
        validate_row(row)
        require(row["t"] not in seen, "DUPLICATE_ORIGIN")
        seen.add(row["t"])
    matched = [r for r in rows if r["paired_xz_eligible"]]
    a = {r["t"] for r in matched if r["trigger"]}
    b = {r["t"] for r in matched if r["x_condition"]}
    ea, eb = episodes(a), episodes(b)
    # Half-open episode calendars; exact starts are counted separately.
    covered_a = {t + i * HOUR for t in ea for i in range(8)}
    covered_b = {t + i * HOUR for t in eb for i in range(8)}
    overlaps = [(t, u) for t in ea for u in eb if max(t, u) < min(t, u) + 8 * HOUR]
    categories = {f"X_{x}/OI24_{p}/OI4_{q}": 0
                  for x in (False, True) for p in (False, True) for q in (False, True)}
    examples = {}
    for r in matched:
        key = (f"X_{r['x_condition']}/OI24_{r['delta_log_oi_24h'] >= 0.015}"
               f"/OI4_{r['delta_log_oi_4h'] >= -0.005}")
        categories[key] += 1
        examples.setdefault(key, {k: r[k] for k in (
            "t", "origin_utc", "log_return_4h", "delta_log_oi_24h", "delta_log_oi_4h", "trigger")})
    years = {str(y): counts([r for r in rows if datetime.fromtimestamp(r["t"], UTC).year == y])
             for y in range(2021, 2025)}
    months = {f"{y}-{m:02}": counts([r for r in rows if
              datetime.fromtimestamp(r["t"], UTC).strftime("%Y-%m") == f"{y}-{m:02}"])
              for y in range(2021, 2025) for m in range(1, 13)}
    return {
        "scientific_terminal": "R5_INCONCLUSIVE_P1_COMPARATOR_UNAVAILABLE",
        "r5_full_acceptance": False, "labels": LABELS,
        "population": {**counts(rows), "calendar_hours": (END - START) // HOUR,
            "omitted_opening_calendar_hours": 1, "duplicates": 0,
            "x_events_before_z_mask": sum(r["x_condition"] for r in rows),
            "x_events_excluded_by_z_mask": sum(r["x_condition"] and not r["z_eligible"] for r in rows),
            "missing_X_only": sum(not r["x_eligible"] and r["z_eligible"] for r in rows),
            "missing_Z_only": sum(r["x_eligible"] and not r["z_eligible"] for r in rows),
            "missing_both": sum(not r["x_eligible"] and not r["z_eligible"] for r in rows),
            "missing_reasons_nonexclusive": dict(Counter(s for r in rows
                for s in r["no_action_reasons"] if s not in ("X_THRESHOLD_NOT_MET", "Z_THRESHOLD_NOT_MET"))),
            "definition": "Frozen recorded R4 schedule intersect complete saved X and native base-OI current/24h/4h; no imputation",
            "three_way_matched_denominator": None,
            "timestamp_units": "t/cutoff: UTC Unix seconds; native labels/content/predecessors: UTC Unix microseconds",
            "clock": "origin HH:01; cutoff HH:00; OI label cutoff-10m, content upper cutoff-5m; X strictly before cutoff",
            "causal_qualification": "Event-time order only; receiver first-known PIT is not established"},
        "event_hours": {**intersection(a, b), "neither": len(matched) - len(a | b)},
        "episode_calendar": {
            "horizon_hours": 8, "rule": "Greedy [start,start+8h); no outcome or trade interpretation",
            "exact_starts": intersection(ea, eb), "overlapping_interval_pairs": len(overlaps),
            "tlob_episodes_overlapping_x": len({t for t, _ in overlaps}),
            "x_episodes_overlapping_tlob": len({u for _, u in overlaps}),
            "covered_hour_slots": intersection(covered_a, covered_b),
            "end_overhang_slots_after_scope": sum(t >= END for t in covered_a | covered_b),
            "qualification": "Calendars may extend 8h beyond last origin; slots are window geometry, never eligible observations",
            "tlob_episode_starts": ea, "x_episode_starts": eb,
            "tlob_episode_start_iso_weeks": len({datetime.fromtimestamp(t, UTC).isocalendar()[:2] for t in ea})},
        "original_threshold_categories": categories, "first_example_per_category": examples,
        "negative_OI": {"24h_negative": sum(r["delta_log_oi_24h"] < 0 for r in matched),
            "4h_negative": sum(r["delta_log_oi_4h"] < 0 for r in matched),
            "tlob_with_4h_negative": sum(r["trigger"] and r["delta_log_oi_4h"] < 0 for r in matched)},
        "yearly": years, "monthly": months,
        "concentration": {"max_event_year_share": max(v["tlob_events"] for v in years.values()) / len(a) if a else None,
            "max_episode_start_year_share": max(Counter(datetime.fromtimestamp(t, UTC).year for t in ea).values()) / len(ea) if ea else None,
            "regime_definition": "Calendar year and original X threshold strata only; no outcome-defined bull/bear labels",
            "monthly_episode_counts": "Reclustered within month; do not sum them as the global calendar"},
        "P1": {
            "status": "COMPARATOR_UNAVAILABLE", "actions": None, "scores": None,
            "event_intersection": None, "episode_intersection": None, "eligible_origins": None,
            "frozen_specification": "scripts/research/strategy_eval/__init__.py PLAN at baseline SHA; no independent historical model freeze located in assigned roots",
            "mechanism": "A_POSITION_OVERHANG",
            "feature": "(log(top-position long/short ratio)-training mean) * max(delta log base OI 4h,0)",
            "fit": "Training-only standardization; ridge lambda selected by inner label MSE; score coefficient <=0; fold/horizon-specific beta",
            "decision": "sign(prediction) only above nominal round-trip cost + 1bp buffer + 5bp/day reserve; no action otherwise",
            "required_artifacts": ["Authenticated fold boundaries and train-time hashes", "Training center, means, scales, beta and selected lambda per fold/horizon", "Authentic P1 ten-control feature panel and native ratio timing", "Frozen eligibility/exposure mask without outcome contents"],
            "blocker": "No separately bound authentic P1 historical parameters/scores/feature population supplied or located. Re-fitting needs prohibited labels. Saved R4 lacks P1 ratio and several P1 X controls.",
            "x_schema_difference": "P1 includes quote taker imbalance, centered 24h range, spot/perp basis; R4 inherited R1 includes 1h range and log base volume instead. Equal vector length does not establish identity.",
            "eligible_definition": "P1 ready: 10 finite original X, x_complete, x_end_us<cutoff; observed native 5m Z with exact 4h predecessor, label in [cutoff-600,cutoff-300], finite OI-growth and ratio; fitted validation folds additionally require outcome completeness, unavailable here",
            "stop": "No proxy rule, synthetic model transfer, retraining, P1 actions or denominator fabricated"},
        "claims": [
            {"claim": "TLOB adds event timestamps beyond paired X", "verdict": "FALSIFIED_BY_CONSTRUCTION", "evidence": "TLOB = X AND Z; every TLOB event is an exact X event"},
            {"claim": "Z changes the observable selection within X", "verdict": "DESCRIPTIVE_SELECTION_ESTABLISHED", "evidence": "Original threshold categories show both included and excluded X events; no conditional independence or economic claim"},
            {"claim": "Independent TLOB-specific mechanism versus P1", "verdict": "INCONCLUSIVE", "evidence": "Authentic P1 fitted comparator unavailable; shared OI-growth observable; non-fitted implementation is insufficient novelty evidence"},
            {"claim": "New LONG inventory, forced liquidation or profitable edge", "verdict": "NOT_IDENTIFIED", "evidence": "Unsigned aggregate OI lacks inventory direction, position entry identity and liquidation observations; no outcomes studied"}],
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r4-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output_root.resolve().is_relative_to(args.r4_root.resolve()), "OUTPUT_IS_FROZEN_ROOT")
    args.output_root.mkdir(parents=True, exist_ok=True)
    before = frozen_hashes(args.r4_root)
    evidence = analyze(load_panel(args.r4_root))
    require(before == frozen_hashes(args.r4_root), "R4_CHANGED_DURING_ANALYSIS")
    evidence["frozen_input_hashes"] = before
    dump(args.output_root / "EVIDENCE_MATRIX.json", evidence)
    print(json.dumps({"terminal": evidence["scientific_terminal"], "population": evidence["population"],
                      "events": evidence["event_hours"]}, sort_keys=True))


if __name__ == "__main__":
    main()
