"""Execute analysis and required focused checks, recording actual exit codes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .discriminate import BASELINE, LABELS, digest, dump, frozen_hashes, require

CODE = "scripts/research/bline_r5_tlob_p1"
TESTS = "tests/research/bline_r5_tlob_p1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r4-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    root, out = args.r4_root.resolve(), args.output_root.resolve()
    require(out != root and not out.is_relative_to(root), "FROZEN_OUTPUT_PATH")
    require(not out.is_symlink(), "OUTPUT_SYMLINK")
    out.mkdir(parents=True, exist_ok=True)
    previous_receipt = out / "RUN_RECEIPT.json"
    history = []
    if previous_receipt.exists():
        previous = json.loads(previous_receipt.read_text())
        history = previous.get("previous_attempts", []) + [{
            "commands": previous["commands"], "engineering_checks_passed": previous["engineering_checks_passed"],
            "new_local_code_sha256": previous["new_local_code_sha256"],
            "created_at_utc": previous["created_at_utc"],
        }]
    commands = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src:.",
           "BLINE_R4_ROOT": str(root)}

    def run(command):
        result = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True, check=False)
        commands.append({"command": command, "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        print(f"exit={result.returncode}: {' '.join(command)}", flush=True)
        return result

    head = run(["git", "rev-parse", "HEAD"])
    require(head.returncode == 0 and head.stdout.strip() == BASELINE, "BASELINE_MISMATCH")
    initial_status = run(["git", "status", "--porcelain=v1", "--untracked-files=all"]).stdout
    before = frozen_hashes(root)
    # Hash only: never deserialize the mixed-year R1 feature panel.
    binding = json.loads((root / "input_binding.json").read_text())
    r1_path = Path(binding["r1_panel"]["path"])
    r1_before = digest(r1_path)
    require(r1_before == binding["r1_panel"]["sha256"], "R1_BINDING_IDENTITY")
    analysis = run([sys.executable, "-m", "scripts.research.bline_r5_tlob_p1.discriminate",
                    "--r4-root", str(root), "--output-root", str(out)])
    tests = run([sys.executable, "-m", "pytest", TESTS, "--import-mode=importlib",
                 "-p", "no:cacheprovider", "--basetemp", str(out / ".pytest-tmp"), "-q", "--tb=short"])
    lint = run([sys.executable, "-m", "ruff", "check", "--no-cache", CODE, TESTS])
    final_status = run(["git", "status", "--porcelain=v1", "--untracked-files=all"]).stdout
    after = frozen_hashes(root)
    r1_after = digest(r1_path)
    evidence = json.loads((out / "EVIDENCE_MATRIX.json").read_text()) if analysis.returncode == 0 else None
    passed = all(r.returncode == 0 for r in (analysis, tests, lint)) and before == after and r1_before == r1_after
    if evidence is not None:
        p, ev, ep = evidence["population"], evidence["event_hours"], evidence["episode_calendar"]
        years = "\n".join(f"| {y} | {v['matched']} | {v['x_events']} | {v['tlob_events']} | "
                          f"{v['tlob_episodes_8h']} | {v['tlob_density_per_48_eligible_hours']:.6f} |"
                          for y, v in evidence["yearly"].items())
        report = f"""# R5 focused scientific discriminator

Candidate scientific terminal: **R5_INCONCLUSIVE_P1_COMPARATOR_UNAVAILABLE**.
Engineering checks: **{'PASS' if passed else 'FAILED'}**. Full R5 acceptance: **false**.
Baseline: `{BASELINE}`. No commit or push performed; Controller B retains acceptance/publication.

## Matched feature-only comparison actually executed

The exact frozen R4 schedule has {p['scheduled']:,} hourly origins in 2021–2024,
versus {p['calendar_hours']:,} calendar hours: its first calendar hour is omitted.
The matched X/TLOB denominator is {p['matched']:,}; it is not a P1 denominator.
The original frozen rule is X: log_return_4h <= -0.01; Z:
delta_log_oi_24h >= 0.015 AND delta_log_oi_4h >= -0.005; TLOB = X AND Z.
X eligible: {p['x_eligible']:,}; Z eligible: {p['z_eligible']:,}.
Missing X only: {p['missing_X_only']}; missing Z only: {p['missing_Z_only']};
missing both: {p['missing_both']}. Missing reasons overlap and are separately tabulated.
The {p['x_events_before_z_mask']:,} complete-X events reduce to {p['x_events']:,}
under the matched mask: {p['x_events_excluded_by_z_mask']} X events are excluded for missing Z.
Both arms use exactly the same complete observations; missing values are never negative controls.
TLOB NO_ACTION is {p['tlob_no_action']:,} on the matched population and
{p['scheduled_tlob_no_action']:,} on the recorded schedule, including missing observations.
No native input directories or Parquet payloads were scanned by this implementation.

Origin/cutoff are UTC Unix seconds; OI labels, content upper bounds and predecessors are
UTC microseconds. Origin HH:01, cutoff HH:00, OI label HH:50 of the preceding hour,
content upper HH:55, exact 24h and 4h predecessors. X is frozen historical data strictly
before cutoff. This is event-time causality; receiver-first-known remains PIT_UNKNOWN.
Every saved rule flag and action was replayed from saved price/OI values; all 14 frozen
R4 output hashes and their pinned manifest were checked before/after, plus R1 hash identity.
Native OI source correctness is inherited from the hash-bound prior revalidation, not
independently replayed again here. Saved R4 x_eligible is inherited; its entire ten-control
X vector is not present in R4, and the mixed-year R1 panel was not deserialized for this run.

Exact event timestamps: both {ev['both']:,}, TLOB-only {ev['tlob_only']},
X-only {ev['x_only']:,}, neither {ev['neither']:,}. TLOB selects
{p['tlob_events'] / p['x_events']:.6%} of paired X events. Thus Z observably filters X,
but creates zero additional event timestamps. This does not establish statistical
independence, a new causal family, conditional incremental value, or economic utility.

Independent original greedy 8h calendars yield {p['tlob_episodes_8h']} TLOB episodes and
{p['x_episodes_8h']} X episodes. Exact start intersection: {ep['exact_starts']['both']};
TLOB-only starts: {ep['exact_starts']['tlob_only']}; X-only starts: {ep['exact_starts']['x_only']}.
Overlapping half-open interval pairs: {ep['overlapping_interval_pairs']};
{ep['tlob_episodes_overlapping_x']} TLOB and {ep['x_episodes_overlapping_tlob']} X episodes overlap.
Distinct starts are not necessarily new calendar exposure. Covered hourly slot
intersection/differences are in EVIDENCE_MATRIX.json; slots are geometry, not eligible origins.
Events/episodes are never trades; eight-hour geometry uses no future outcomes.

| Year | Matched | X events | TLOB events | TLOB 8h episodes | Episodes / 48 eligible hours |
|---|---:|---:|---:|---:|---:|
{years}

Maximum event-year share: {evidence['concentration']['max_event_year_share']:.6%}.
Maximum episode-start-year share: {evidence['concentration']['max_episode_start_year_share']:.6%}.
Calendar years and original X-threshold strata are descriptive regimes; no outcome-defined
bull/bear segmentation. 2023 is sparse. Monthly denominators, original-threshold eight-cell
contingency counts, negative OI, missing categories, and first counterexamples per cell are
in the evidence matrix. Monthly episode calendars restart each month and must not be summed
as the global calendar. TLOB can fire while 4h OI is negative; this directly weakens an
unqualified current-position-growth description. OI-positive states without the X drop
and X drops rejected by either OI condition are retained as disconfirming observations.

## Authentic P1 mechanism and exact stopping boundary

Frozen executable specification: `scripts/research/strategy_eval/__init__.py` PLAN at
the baseline SHA; source `pipeline.py` design/fit/predict/tune and
`clocked_dataset.py` select_z/controls/ready, plus `costs.py` policy_action.
No P1 evaluator was imported or executed. P1 uses
`(log(top-position ratio) - training mean) * max(delta_log_base_OI_4h, 0)`;
training-only standardized ridge, inner label-MSE lambda selection, nonpositive
interaction coefficient, fold/horizon-specific beta and a cost-buffer action threshold.
Positive growth is an input to a fitted interaction, not an authentic binary P1 event rule.
The training mean is not recoverable by averaging this R4 comparison population.

P1's ten X controls differ from R4/R1's ten X controls, including quote taker imbalance,
centered 24h range and spot/perp basis. P1 native Z sampling allows cutoff minus 10 to 5
minutes, whereas TLOB requires exactly minus 10 minutes. P1 readiness requires original
complete finite X, causal x_end_us, observed finite ratio/OI Z and exact 4h predecessor;
validation folds additionally depend on label-completeness and training/exposure masks.
The saved R4 panel lacks P1 native ratio, fitted centers/scales/beta, original P1 X schema
and eligible fold masks. No independently hash-bound historical P1 model/score registration
or feature-only decision artifact was supplied or located in the assigned roots.
P1 run outputs such as metrics/origins/trades embed outcomes and were not opened.
Re-fitting would require prohibited return labels and selection, so this subtest stops
**COMPARATOR_UNAVAILABLE**. Three-way denominator, P1 scores/actions and intersections
are **null/unresolved**, not zero. No renamed proxy, synthetic-model transfer or new
threshold was substituted. Full R5 completion/novelty acceptance is not claimed.

## Scientific disposition

The claim of additional event timestamps beyond matched X is false by construction.
Observable Z selection within X is established descriptively. Independent TLOB-specific
novelty versus P1 remains unestablished. Both share aggregate increasing-OI information;
fixed thresholds versus fitting alone cannot certify a distinct mechanism.
Unsigned base OI does not identify newly opened LONG positions, directional inventory,
forced liquidation, leverage/margin state, or profitable edges. Consolidation, trapped
inventory and liquidation flow in the original narrative are not independently observed.
No outcomes, PnL, new candidate registration, tuning, source-rights preflight, market-data
downloads, account access, automated trading, TESTNET or LIVE were performed.

## Execution qualification

During preliminary R1 schema inspection, a search for the first observed Z parsed mixed-year
saved feature rows and displayed a 2026-04-01 05:01 UTC pure-feature row. This exceeded the
intended 2021–2024 feature-inspection bound; it was not used in analysis and no outcomes or
protected native partitions were read. The path was stopped, and all analyzed origins are
validated 2021–2024 R4 rows. Do not certify zero out-of-range preliminary feature reads.
An attempted local Git object lookup triggered an unsuccessful lazy fetch via an unavailable
proxy; no object was obtained. Read-only GitHub document retrieval then supplied Controller
role/policy/roadmap on docs/engineering; DOCUMENT_AUTHORITY.json records content and blob SHAs.
Market input bytes and all original artifacts remain unchanged. Scope/status receipts
cover this isolated worktree; the original dirty checkout was never modified.

Next information-changing input is a separately authenticated, feature-only P1 model,
native-feature and eligible-fold bundle, with freeze identity and without outcome content.
Absent that input, retain this terminal; do not broaden access or retune the hypothesis.

{' / '.join(LABELS)}
"""
        (out / "R5_DECISION.md").write_text(report)
    code_paths = sorted([*repo.glob(f"{CODE}/*.py"), *repo.glob(f"{TESTS}/*.py")])
    input_paths = [root / name for name in before]
    input_paths += [root / "revalidation-20261020" / name for name in
                    ("NEXT_DECISION.md", "REVALIDATION_RECEIPT.json", "SOURCE_SHA_MANIFEST.json")]
    input_paths += [repo / f"scripts/research/strategy_eval/{name}" for name in
                    ("__init__.py", "pipeline.py", "clocked_dataset.py", "costs.py")]
    input_paths += [r1_path]
    receipt = {
        "task": "V065-BLINE-R5-TLOB-P1-DISCRIMINATION-01", "baseline_sha": BASELINE,
        "created_at_utc": datetime.now(UTC).isoformat(), "labels": LABELS,
        "invocation": [sys.executable, "-m", "scripts.research.bline_r5_tlob_p1.run", *sys.argv[1:]],
        "commands": commands, "previous_attempts": history, "environment": {k: env[k] for k in
            ("PYTHONDONTWRITEBYTECODE", "PYTHONPATH", "BLINE_R4_ROOT")},
        "input_sha256": {str(p): digest(p) for p in input_paths},
        "frozen_r4_before": before, "frozen_r4_after": after,
        "r1_hash_before": r1_before, "r1_hash_after": r1_after,
        "all_14_frozen_r4_outputs_unchanged": before == after,
        "initial_git_status": initial_status, "final_git_status": final_status,
        "new_local_code_sha256": {str(p.relative_to(repo)): digest(p) for p in code_paths},
        "engineering_checks_passed": passed, "full_R5_acceptance": False,
        "candidate_scientific_terminal": "R5_INCONCLUSIVE_P1_COMPARATOR_UNAVAILABLE",
        "actual_comparison": evidence["population"] if evidence else None,
        "P1_comparator": "COMPARATOR_UNAVAILABLE", "P1_population_or_actions_fabricated": False,
        "real_outcome_labels_read": 0, "PnL_computed": False,
        "native_parquet_payloads_read": 0, "market_data_downloads": 0,
        "new_registrations_or_parameter_sweeps": 0, "commit_push_performed": False,
        "preliminary_scope_deviation": "Mixed-year R1 feature schema inspection parsed rows outside 2021-2024 and displayed a 2026-04-01 pure-feature row; excluded from analysis; no outcome or protected native partitions read",
        "documentation": "Read-only GitHub connector document snapshots/blob SHAs in DOCUMENT_AUTHORITY.json; no market-data download",
        "failed_lookup": "Local git object ca82edb9 was absent; implicit lazy fetch failed at unavailable proxy; no object obtained",
        "limitations": ["No authenticated P1 historical fitted comparator or eligible fold population available",
            "R4 X validity inherited from frozen saved panel and prior revalidation, not a fresh full-X reconstruction",
            "Event-time causal order is not receiver PIT or source admission",
            "Calendar differences are not independent mechanisms, trades or utility",
            "No complete R5 three-way comparison or novelty PASS"],
    }
    dump(out / "RUN_RECEIPT.json", receipt)
    outputs = [out / name for name in ("R5_DECISION.md", "EVIDENCE_MATRIX.json", "RUN_RECEIPT.json",
                                      "DOCUMENT_AUTHORITY.json") if (out / name).exists()]
    dump(out / "PATH_MANIFEST.json", {
        "baseline_sha": BASELINE, "repository_write_paths": [str(p.relative_to(repo)) for p in code_paths],
        "output_root": str(out), "outputs": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size}
                                                for p in outputs},
        "self_hash": "Excluded to avoid recursive hashing", "input_paths": [str(p) for p in input_paths],
        "temporary_test_root": str(out / ".pytest-tmp"), "publish": "Controller B review only; no commit/push"})
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
