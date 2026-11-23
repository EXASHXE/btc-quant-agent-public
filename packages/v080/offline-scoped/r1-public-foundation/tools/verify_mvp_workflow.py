"""Exercise the installed manual MVP CLI with finite deterministic offline data."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

from btc_quant_agent.platform.mvp.models import Dataset, IMPORTED
from btc_quant_agent.platform.mvp.source import Source
from btc_quant_agent.platform.mvp.product import Product


def main(output):
    output = Path(output)
    output.mkdir(exist_ok=False)
    quant = str(Path(sys.executable).parent / "quant")
    receipts = {}

    def call(name, args, expected=0):
        r = subprocess.run([quant] + args, capture_output=True, text=True, timeout=120)
        (output / (name + ".stdout.json")).write_text(r.stdout)
        (output / (name + ".stderr.log")).write_text(r.stderr)
        assert r.returncode == expected, (name, r.returncode, r.stderr[-500:], r.stdout[-500:])
        return json.loads(r.stdout)

    for name, scenario in [
        ("positive", "positive"),
        ("no_setup", "all-no-setup"),
        ("reconciled", "clock-reconciled"),
        ("blocked", "clock-blocked"),
    ]:
        receipts[name] = call(name, ["mvp", "demo", "--output", str(output / name), "--scenario", scenario])
    assert receipts["positive"]["states"] == ["ARMED", "NO_SETUP", "NO_SETUP"]
    assert receipts["no_setup"]["states"] == ["NO_SETUP"] * 3
    assert receipts["reconciled"]["clock_hold_before_reconciliation"]["status"] == "MVP_DATA_NOT_READY"
    assert receipts["reconciled"]["states"][0] == "ARMED"
    assert receipts["blocked"]["states"] == ["MVP_DATA_NOT_READY"] * 3
    blocked = Source(output / "blocked")
    witness = Dataset.model_validate_json((output / "reconciled/witness.json").read_text())
    try:
        blocked.reconcile(witness)
    except ValueError as e:
        receipts["irreconcilable_retry_reason"] = str(e)
    assert "irreconcilable_retry_reason" in receipts
    positive = output / "positive"
    before = [d.model_dump(mode="json") for d in Product(Source(positive)).decisions()]
    call("manual_review", ["mvp", "review", "--output", str(positive)])
    call("status", ["mvp", "status", "--output", str(positive)])
    call("episodes", ["mvp", "episodes", "--output", str(positive)])
    receipts["followup"] = call("followup", ["mvp", "demo-followup", "--output", str(positive)])
    assert receipts["followup"]["restart_original_plan_unchanged"]
    restored = Product(Source(positive))
    assert [d.model_dump(mode="json") for d in restored.decisions()] == before
    identity = next(d.episode_id for d in restored.decisions() if d.episode_id)
    call("repeat_observation", ["mvp", "observe", "--output", str(positive), "--episode-id", identity])
    call("recover", ["mvp", "recover", "--output", str(positive)])
    receipts["explicit_evaluation"] = call(
        "explicit_evaluation",
        ["mvp", "evaluate", "--output", str(positive), "--report-output", str(output / "manual_evaluation")],
    )
    assert receipts["explicit_evaluation"]["scientific_decision"] == "INSUFFICIENT_SUPPORT"
    call("no_data_init", ["mvp", "init", "--output", str(output / "actual_data_absent")])
    receipts["actual_data_review"] = call(
        "no_data_review", ["mvp", "review", "--output", str(output / "actual_data_absent")], 2
    )
    # A rejected fixture is not a genuine dataset or permission.
    attempted = Dataset.model_validate_json((positive / "dataset.json").read_text()).model_copy(
        update={"evidence_class": IMPORTED, "fixture_id": None}
    )
    path = output / "FABRICATED_IMPORT_PERMISSION_NEGATIVE_ONLY.json"
    path.write_text(attempted.model_dump_json(indent=2))
    receipts["unpermitted_import"] = call(
        "unpermitted_import",
        ["mvp", "import", "--output", str(output / "actual_data_absent"), "--dataset", str(path)],
        2,
    )
    receipts["strict"] = call("strict_doctor", ["--mode", "STRICT_RESEARCH", "doctor"])
    assert receipts["strict"]["mode"] == "STRICT_RESEARCH" and not receipts["strict"]["source_qualified"]
    result = {
        "status": "PASS_INSTALLED_OFFLINE_MVP_WORKFLOW",
        "mode": "EXPLORATORY_MVP",
        "evidence": "DETERMINISTIC_SYNTHETIC_ONLY",
        "demonstrations": {
            k: {
                key: val
                for key, val in v.items()
                if key
                in ("states", "data_status", "dashboard", "evaluation", "clock_hold_before_reconciliation")
            }
            for k, v in receipts.items()
            if isinstance(v, dict) and k in ("positive", "no_setup", "reconciled", "blocked")
        },
        "shadow_original_plans_unchanged": True,
        "later_market_outcome": receipts["followup"]["observation"]["outcome"],
        "later_lifecycle": receipts["followup"]["episode"]["state"]["status"],
        "scientific_decision": "INSUFFICIENT_SUPPORT",
        "actual_data_status": "MVP_DATA_NOT_READY",
        "lawful_eligible_real_datasets": 0,
        "native_market_requests": 0,
        "SOURCE_QUALIFIED": False,
        "SHADOW_QUALIFIED": False,
        "ECONOMICALLY_VALIDATED": False,
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        "receipts_directory": str(output),
    }
    (output / "WORKFLOW_ACCEPTANCE.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    main(a.output)
