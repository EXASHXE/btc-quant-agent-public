"""Audit the isolated installed B2 distribution and pinned dependency graph."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

PKG = "quant_personal_decision_b2"
B1 = "quant_personal_public_b1"
B1_PIN = "19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f"


def main() -> None:
    b1_wheel = Path(sys.argv[1])
    b1 = metadata.distribution("quant-personal-public-b1")
    b2 = metadata.distribution("quant-personal-decision-b2")
    assert hashlib.sha256(b1_wheel.read_bytes()).hexdigest() == B1_PIN
    assert b2.requires == ["quant-personal-public-b1==0.8.0b1"] and b1.version == "0.8.0b1"
    assert [(e.group, e.name, e.value) for e in b2.entry_points] == [
        ("console_scripts", "quant-decision-b2", f"{PKG}.cli:main"),
    ]
    assert not (b1.requires or [])
    with zipfile.ZipFile(b1_wheel) as z:
        for path in z.namelist():
            if path.startswith(B1 + "/") and path.endswith(".py"):
                assert z.read(path) == Path(b1.locate_file(path)).read_bytes()
    files = sorted(str(path) for path in b2.files or [])
    source = [path for path in files if path.endswith(".py")]
    assert source and all(path.startswith(PKG + "/") for path in source)
    assert not any("btc_quant_agent" in path for path in files)
    graph = {}
    for path in source:
        tree = ast.parse(Path(b2.locate_file(path)).read_text(), filename=path)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1
                    imports.extend(f"{PKG}.{node.module or name.name}" for name in node.names)
                elif node.module:
                    imports.append(node.module)
            elif isinstance(node, ast.Call):
                assert not isinstance(node.func, ast.Name) or node.func.id not in {"__import__", "exec", "eval"}
                assert not isinstance(node.func, ast.Attribute) or node.func.attr != "import_module"
        allowed = (sys.stdlib_module_names - {"socket", "ssl", "http", "urllib", "subprocess", "ctypes"}) | {PKG, B1}
        assert all(name.split(".")[0] in allowed for name in imports)
        graph[path] = sorted(set(imports))

    from quant_personal_decision_b2.engine import Engine

    assert Engine.__module__.startswith(PKG)
    assert not any(key == "btc_quant_agent" or key.startswith("btc_quant_agent.") for key in sys.modules)
    print(json.dumps({
        "distribution": b2.metadata["Name"], "version": b2.version, "runtime_dependencies": b2.requires,
        "b1_wheel_sha256": B1_PIN, "b1_installed_source_byte_match": True,
        "b2_file_inventory": files, "b2_import_graph": graph, "isolated": bool(sys.flags.isolated),
        "legacy_installed": importlib.util.find_spec("btc_quant_agent") is not None, "legacy_imported": False,
    }, indent=2))


if __name__ == "__main__":
    main()
