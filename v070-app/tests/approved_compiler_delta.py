"""Verify exactly the separately versioned policy-injection delta, nothing else."""

import ast
import hashlib
import json


def assert_original_s1_ast(root):
    tree = ast.parse((root / "src/btc_quant_agent/platform/rc_strategy.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "compile_s1")
    assert fn.args.kwonlyargs[-1].arg == "bar_policy"
    assert ast.dump(fn.args.kw_defaults[-1]) == "Constant(value=None)"
    fn.args.kwonlyargs.pop()
    fn.args.kw_defaults.pop()
    assignment = next(
        n
        for n in fn.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "policy" for t in n.targets)
    )
    assert ast.dump(assignment.value) == ast.dump(
        ast.parse("SwingPolicy() if bar_policy is None else bar_policy", mode="eval").body
    )
    assignment.value = ast.parse("SwingPolicy()", mode="eval").body
    expected = json.loads((root / "contracts/l_compiler_invariance.json").read_text())
    assert (
        hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
        == expected["original_J_AST_SHA256"]
    )
