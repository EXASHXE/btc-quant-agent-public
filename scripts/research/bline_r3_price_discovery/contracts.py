"""One immutable exploratory definition. Never a parameter-search interface."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from scripts.research.bline_multiyear.contracts import X_NAMES
from scripts.research.bline_r2_expanded_oi.contracts import LABELS, canonical, digest

TASK = "V065-BLINE-R3-CAUSAL-MECHANISM-FEASIBILITY-01"
REPO = Path(__file__).resolve().parents[3]
LAKE = Path("/root/workspace/project/crypto-data/lakehouse")
OUTPUT = LAKE / "research-bline-r3-price-discovery"
C1 = LAKE / "c1/canonical_v1"
R1 = LAKE / "research-bline-r1"
R2 = LAKE / "research-bline-r2"
OI = LAKE / "research-bline-r2-oi-expanded-20261019"
MINUTE = 60_000_000
HOUR = 60 * MINUTE


def us(text):
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("EXPLICIT_UTC_REQUIRED")
    delta = dt - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def iso(t):
    return datetime.fromtimestamp(t // 1_000_000, UTC).isoformat()


def protected(origin):
    cutoff = origin - MINUTE
    left = cutoff - 24 * HOUR - 2 * MINUTE
    return (
        us("2025-02-01T00:00:00Z") <= origin < us("2026-02-01T00:00:00Z")
        or max(left, us("2025-02-01T00:00:00Z")) < min(cutoff, us("2026-02-01T00:00:00Z"))
        or origin >= us("2026-09-01T00:00:00Z")
    )


def immutable(path, value):
    data = canonical(value)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("IMMUTABLE_ARTIFACT_MISMATCH:" + str(path))
    else:
        with path.open("xb") as stream:
            stream.write(data)


def registration(binding):
    return {
        "task": TASK,
        "version": 1,
        "state": "EXPLORATORY_FEATURE_ONLY",
        "labels": LABELS,
        "candidate": "SPOT_LED_DOWNWARD_PRICE_DISCOVERY_PARTIAL_PERP_CATCHUP",
        "instrument": ["binance", "BTCUSDT", "SPOT", "USD_M_PERPETUAL", "1m", "native Last close"],
        "input_binding": binding,
        "schedule": {
            "left": "2021-01-01T00:00:00Z",
            "right_exclusive": "2025-01-01T00:00:00Z",
            "cadence": "UTC HH:01; cutoff C=HH:00; all scheduled hours retained",
        },
        "X": {
            "fields": X_NAMES,
            "source": "unchanged frozen R1 HISTORICAL_FEATURE_ONLY X",
            "comparator": "SHORT iff frozen log_return_4h <= -0.01",
            "pairing": "Mask BOTH comparator and candidate on identical complete X AND observable Z",
        },
        "clock": {
            "endpoints": "e_j=C-16m+j*m, j=0..15; all 16 consecutive closes required in BOTH markets",
            "native_bar": "[open,open+1m); event_ts=end; source_native_ts=open epoch; no interval-end label shifting",
            "strict": "Every bar interval_end < C. C-1m is last endpoint; first native interval starts C-17m.",
            "ordering": "Crossing is observable only at distinct bar ends; never infer intra-minute trade ordering",
            "PIT": "UNKNOWN; native bar clocks do not establish receiver-first-known or structural causality",
        },
        "formulas": {
            "s_j": "log(spot_close(e_j)/spot_close(e_0))",
            "p_j": "log(perp_close(e_j)/perp_close(e_0))",
            "g_j": "p_j-s_j; relative change in basis, no static basis-level condition",
            "tS": "First j in 1..15 with s_j <= -0.001; require tS<=5",
            "tP": "First j in 1..15 with p_j <= -0.001; require tS<tP<=15",
            "lead": "p_tS > -0.0005 AND g_tS >= 0.0005",
            "partial_recovery": "0.25 <= g_15/g_tS <= 0.75 AND p_15 < p_tS",
            "spot_persistence": "s_15 <= -0.001 AND abs(s_15-s_tS)<=0.0005",
            "Z": "ALL temporal-order, lead, partial-recovery and spot-persistence conditions",
            "action": "SHORT iff paired eligible AND X comparator condition AND Z; otherwise NO_ACTION",
        },
        "constant_rationale": {
            "10bp": "Fixed round-number log displacement, distinct from 1% four-hour X, not fitted to data or assumed profitable",
            "5bp": "Half displacement separates early lag and limits later spot reversal as alternate explanation",
            "5m_15m": "First third leads, remaining two thirds allow catchup; exact minute order is necessary",
            "25_75_percent": "Middle half of remaining initial displacement excludes no recovery and completed recovery",
            "limitations": "Economically plausible underreaction is untested at 4–24h. Common latent news and last-trade staleness can explain apparent leadership.",
        },
        "exclusions": [
            ["2025-02-01T00:00:00Z", "2026-02-01T00:00:00Z"],
            ["2026-09-01T00:00:00Z", "unbounded"],
        ],
        "development_only": "2021–2024 are exposed descriptive development, never pristine OOS or outcome authorized",
        "horizons": {
            "primary_hours": 8,
            "diagnostic_hours": [4, 12, 24],
            "episodes": "Existing EventClusterer; first trigger anchors [T0,T0+H); no sliding extension",
            "weeks": "Distinct ISO weeks of episode starts; count is not independent observations or statistical power",
        },
        "gate": {
            "minimum_trigger_hours": 30,
            "minimum_nonoverlap_8h_episodes": 30,
            "minimum_episode_start_weeks": 12,
            "minimum_years_with_episodes": 3,
            "maximum_year_trigger_share": 0.70,
            "episodes_per_eligible_48h_range": [0.5, 2.0],
            "density_rationale": "Approximately one setup per 48 eligible hours, fixed factor-two feasibility band; no calibration",
            "minimum_paired_fraction": 0.80,
            "falsifiers": [
                "Non-novel renamed frozen family",
                "Clock or source identity failure",
                "Physical paired coverage below 80%",
                "Effective sample floors fail",
                "Episode density outside [0.5,2] per 48 paired eligible hourly origins",
                "Fewer than 3 years or >70% triggers in one year",
            ],
        },
        "missing": "No imputation, forward fill, nearby substitution, other venue, taker-flow synthesis or synthetic OI",
        "budget": {
            "threshold_search": 0,
            "direction_search": 0,
            "horizon_search": 0,
            "exit_search": 0,
        },
        "scope": {
            "outcome_access": False,
            "real_returns": False,
            "PnL": False,
            "network_data": False,
            "protected_sqlite": False,
            "executable": False,
            "source_admitted": False,
        },
    }


def freeze(out, value):
    immutable(out / "exploratory_registration.v1.json", value)
    return digest(out / "exploratory_registration.v1.json")


def novelty():
    rows = [
        (
            "H32/H33/H34 taker-flow spread",
            "H32 inconclusive; H33/H34 falsified",
            "No signed/taker flow used. Reordering minute prices with fixed endpoints changes Z.",
        ),
        (
            "Price breakout/retest; Goal-B",
            "No promotable candidate / costs and support fail",
            "No local high/low breakout, support/retest or range trigger. Cross-product ordered crossings are essential.",
        ),
        (
            "Funding/Mark R3/R3.1",
            "Source/causality blocked; exposed development only",
            "No funding, Mark or settlement observations; native Last closes from matched spot/perp only.",
        ),
        (
            "PA-B T6",
            "STOP: empirically infeasible for frozen design",
            "No price-action structure or exit adaptation. Spot-first then perpetual crossing and partial recovery is required.",
        ),
        (
            "F3 basis",
            "Increment untested / PIT unknown; descriptive only",
            "Static end basis is insufficient. A prefix-order counterexample keeps end basis and X fixed but reverses Z.",
        ),
        (
            "R1 Funding/Premium Release",
            "168 hours / 113 8h episodes / 44 weeks; support and concentration limitations",
            "No premium/index/Mark/funding compression. Temporal ordering of native Last prices is observable separately.",
        ),
        (
            "R1/R2 OI deleveraging",
            "4/2/2 original; exploratory R2 89/38/22 with 2024 concentration",
            "No OI or trader ratio. Same frozen X controls, independent minute-price sequence Z.",
        ),
    ]
    return {
        "rows": [
            dict(zip(["prior_family", "frozen_disposition", "distinguishing_observable"], r))
            for r in rows
        ],
        "novelty_claim": "Functionally distinct pre-cutoff observable, NOT proven incremental predictive information",
        "proof": "Focused test holds X and terminal basis fixed and changes only earlier temporal order; Z changes",
        "structural_causal_identification": False,
    }
