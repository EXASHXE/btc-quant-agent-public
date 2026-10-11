"""No-market-body registry preflight; method conflicts stop real recomputation."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ORIGINAL_SHA = "a37721eaa1f3cd176146df6bdb63fbd17746189e"
EVIDENCE = "evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1"
FREEZES = (
    "5295eff5c63797fd28a5b7b5733a009536e4fdf3",
    "f82eda7d930e5e158be7cc2fa60967b871e84f0f",
    "99b443b87a0551519c87df28d63edc8e56808b98",
    "8b7b4318db3f1f8344653cb649f2dd05b5ca9dd4",
)


def git_bytes(sha: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{sha}:{path}"], cwd=ROOT)


def preflight() -> dict:
    """Inspect only frozen repository code/registries; no source/cache inspection."""
    signal_path = "scripts/strategy_research/g2_gemini_goal_trend_flow_r1/signals.py"
    signal_tree = ast.parse(git_bytes(ORIGINAL_SHA, signal_path))
    local_tree = ast.parse((ROOT / signal_path).read_text())
    # Ruff import cleanup may differ, but every signal function must be identical.
    original_functions = [ast.dump(n) for n in signal_tree.body if isinstance(n, ast.FunctionDef)]
    current_functions = [ast.dump(n) for n in local_tree.body if isinstance(n, ast.FunctionDef)]
    assert original_functions == current_functions, "Signal semantics changed"
    implemented = {}
    for node in ast.walk(signal_tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        test = node.test
        if not isinstance(test.left, ast.Name) or test.left.id != "cand_id":
            continue
        candidate_id = ast.literal_eval(test.comparators[0])
        params = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        params[target.id] = stmt.value.value
        implemented[candidate_id] = params
    candidates = []
    freezes = []
    for wave, sha in enumerate(FREEZES, 1):
        path = f"{EVIDENCE}/WAVE_{wave:02d}_FROZEN_REGISTRY.json"
        raw = (ROOT / path).read_bytes()
        assert raw == git_bytes(sha, path) == git_bytes(ORIGINAL_SHA, path)
        registry = json.loads(raw)
        assert registry["candidate_count"] == len(registry["candidates"]) == 6
        freezes.append({"wave": wave, "sha": sha, "path": path,
                        "sha256": hashlib.sha256(raw).hexdigest()})
        old = json.loads(git_bytes(ORIGINAL_SHA, f"{EVIDENCE}/WAVE_{wave:02d}_RESULT.json"))
        for candidate in registry["candidates"]:
            candidate_id = candidate["id"]
            values = implemented[candidate_id]
            assert values["horizon_hours"] == candidate["horizon_hours"]
            assert values["stop_mult"] == candidate["stop_atr_multiplier"]
            assert values["target_r"] == candidate["target_R"]
            candidates.append({"id": candidate_id, "registered_parameters": candidate,
                               "original_published_stress_metrics_untrusted":
                                   old["candidates"][candidate_id]["stress_metrics"],
                               "corrected_empirical_metrics": None})
    assert len(candidates) == len({c["id"] for c in candidates}) == 24
    signal_source = git_bytes(ORIGINAL_SHA, signal_path).decode()
    replay_path = "scripts/strategy_research/g2_gemini_goal_trend_flow_r1/replay.py"
    replay_source = git_bytes(ORIGINAL_SHA, replay_path).decode()
    flow_line = 'flow_4h_cum = np.sum(agg60["signed_flow_ratio"][h4_idx - 3 : h4_idx + 1])'
    assert flow_line in signal_source
    assert 'if minute >= deadline:' in replay_source
    assert 'raw_exit = min(op, target) if side > 0 else max(op, target)' in replay_source
    registry_one = candidates[5]["registered_parameters"]
    assert "cumulative 4h signed taker volume" in registry_one["math_formulation"]["long_entry"]
    registry = json.loads(git_bytes(FREEZES[0], f"{EVIDENCE}/WAVE_01_FROZEN_REGISTRY.json"))
    time_cap = registry["protocol"]["execution_rules"]["time_cap"]
    assert "bar close" in time_cap
    entry_rule = registry["protocol"]["execution_rules"]["decision_to_entry"]
    assert "next open t+60000ms" in entry_rule
    assert '"event_time": t_round - 60000' in signal_source
    assert '"entry_at": t_round + 60000' in signal_source
    return {
        "original_sha": ORIGINAL_SHA,
        "registered_candidate_ids_verified": 24,
        "parameter_checks_passed": 72,
        "signal_function_ast_unchanged": True,
        "four_original_freezes": freezes,
        "candidate_comparison": candidates,
        "method_conflicts": [
            {"id": "W1_C06_FLOW_CLOCK_AND_DIMENSION", "candidate": candidates[5]["id"],
             "frozen": registry_one["math_formulation"], "original_code": flow_line,
             "reason": "4h bar index selects old 1h bars; summing normalized ratios is not cumulative signed base volume",
             "resolution_needed": "Controller must choose frozen textual formula versus original executable identity"},
            {"id": "TIME_CAP_OPEN_VERSUS_CLOSE", "frozen": time_cap,
             "original_code": "minute>=deadline: raw_exit=min(op,target) for LONG/max(op,target) for SHORT; exit_at=minute",
             "reason": "Registered horizon-bar close and implemented horizon-bar open have different price and fill clocks",
             "resolution_needed": "Controller must authorize exact temporal semantics before empirical recomputation"},
            {"id": "FIRST_ELIGIBLE_OPEN_VERSUS_SECOND_OPEN", "frozen": entry_rule,
             "original_code": "event_time=t_round-60000; decision_at=t_round; entry_at=t_round+60000",
             "reason": "Actual entry is one minute later than frozen next-open clock for the last closed 1m signal bar",
             "resolution_needed": "Controller must choose frozen next-open versus original 60-second additional delay"},
        ],
        "complete_formula_and_execution_identity_verified": False,
        "source_bodies_read_this_task": 0,
        "source_cache_stat_or_list_this_task": "Existence/count only of authorized A-owned 2021-2023 scratch; no body/header/footer reads",
        "real_recompute_status": "NOT_STARTED_BLOCKED_FIXED_REGISTRY_REPLAY",
        "terminal": "CORRECTION_INCOMPLETE_FAIL_CLOSED",
    }


if __name__ == "__main__":
    print(json.dumps(preflight(), indent=2, allow_nan=False))
