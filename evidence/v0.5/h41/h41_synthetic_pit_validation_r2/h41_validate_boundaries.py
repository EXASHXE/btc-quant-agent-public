"""Exact Git-tree and execution-fence checks; no real source is opened."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from btc_quant_agent.execution import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
)

PARENT = "a3235fbc39667ca2a624faebd3cf9ee8a4b442de"
HEAD = "8ecff4ec4b25bf73a35309689fd3ecfacc0d3399"
INFERENCE = "src/btc_quant_agent/h41/inference.py"
UNCHANGED = (
    "src/btc_quant_agent/h41/science.py",
    "src/btc_quant_agent/h41/authority.py",
    "src/btc_quant_agent/h41/frozen_bindings.py",
    "src/btc_quant_agent/h41/selection.py",
    "src/btc_quant_agent/h41/source.py",
)


def git(*args: str) -> bytes:
    return subprocess.check_output(("git", *args))


def function_text(revision: str, name: str) -> str:
    source = git("show", f"{revision}:{INFERENCE}").decode()
    node = next(item for item in ast.parse(source).body
                if isinstance(item, ast.FunctionDef) and item.name == name)
    result = ast.get_source_segment(source, node)
    assert result is not None
    return result


assert git("rev-parse", "HEAD").decode().strip() == HEAD
assert git("rev-parse", "HEAD^").decode().strip() == PARENT
unchanged = {
    path: git("rev-parse", f"{PARENT}:{path}") == git("rev-parse", f"{HEAD}:{path}")
    for path in UNCHANGED
}
assert all(unchanged.values())
h40_diff = git("diff", "--name-only", PARENT, HEAD, "--", "src/btc_quant_agent/h40/")
assert not h40_diff
r2_function_identical = function_text(PARENT, "run_joint_bootstrap_studentized") == function_text(
    HEAD, "run_joint_bootstrap_studentized",
)
assert r2_function_identical
assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None

h41_sources = tuple(Path("src/btc_quant_agent/h41").glob("*.py"))
execution_imports = []
entry_points = []
for file in h41_sources:
    tree = ast.parse(file.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "execution" in node.module:
            execution_imports.append((file.name, node.module))
        elif isinstance(node, ast.Import):
            execution_imports.extend((file.name, alias.name) for alias in node.names
                                     if "execution" in alias.name)
        elif (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
              and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
              and any(isinstance(value, ast.Constant) and value.value == "__main__"
                      for value in node.test.comparators)):
            entry_points.append(file.name)
assert not execution_imports
assert not entry_points

result = {
    "schema_id": "H41_EXACT_SHA_BOUNDARIES_R2",
    "head": HEAD,
    "parent": PARENT,
    "unchanged_scientific_modules": unchanged,
    "h40_diff": "ZERO",
    "r2_function_textually_identical": r2_function_identical,
    "execution_policy": CURRENT_EXECUTION_POLICY,
    "accepted_execution_write_authority": ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    "h41_execution_imports": execution_imports,
    "h41_main_guards": entry_points,
    "h41_modules": sorted(file.name for file in h41_sources),
}
Path(__file__).with_name("h41_boundaries_result.json").write_text(
    json.dumps(result, sort_keys=True, indent=2) + "\n",
)
print(json.dumps(result, sort_keys=True))
