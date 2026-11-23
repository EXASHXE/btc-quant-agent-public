"""Audit the installed B1 artifact without importing any legacy package."""

from __future__ import annotations

import ast
import importlib.metadata as md
import importlib.util
import json
import sys
from pathlib import Path

PACKAGE = "quant_personal_public_b1"
DISTRIBUTION = "quant-personal-public-b1"


def main() -> None:
    dist = md.distribution(DISTRIBUTION)
    location = Path(dist.locate_file(PACKAGE)).resolve()
    spec = importlib.util.find_spec(PACKAGE)
    assert spec is not None and spec.origin is not None and Path(spec.origin).resolve().is_relative_to(location)
    assert dist.requires is None or not dist.requires
    assert [(ep.group, ep.name, ep.value) for ep in dist.entry_points] == [
        ("console_scripts", "quant-public-b1", f"{PACKAGE}.cli:main")
    ]
    installed = sorted(str(path) for path in dist.files or [])
    modules = sorted(path for path in installed if path.endswith(".py"))
    assert modules and all(path.split("/")[0] == PACKAGE for path in modules)
    assert not any("btc_quant_agent" in path for path in installed)
    graph = {}
    for module in modules:
        tree = ast.parse(Path(dist.locate_file(module)).read_text(), filename=module)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1
                    imports.extend(f"{PACKAGE}.{node.module or alias.name}" for alias in node.names)
                elif node.module:
                    imports.append(node.module)
            elif isinstance(node, ast.Call):
                assert not isinstance(node.func, ast.Name) or node.func.id not in {"__import__", "exec", "eval"}
                assert not isinstance(node.func, ast.Attribute) or node.func.attr != "import_module"
        assert all(name.split(".")[0] in (*sys.stdlib_module_names, PACKAGE) for name in imports)
        graph[module] = sorted(set(imports))
    from quant_personal_public_b1.cli import main as cli_entrypoint
    from quant_personal_public_b1.runtime import Runtime

    assert Runtime.__module__.split(".")[0] == PACKAGE and callable(cli_entrypoint)
    assert not any(key == "btc_quant_agent" or key.startswith("btc_quant_agent.") for key in sys.modules)
    audit = {
        "distribution": dist.metadata["Name"], "version": dist.version, "runtime_dependencies": dist.requires or [],
        "installed_file_inventory": installed, "import_graph": graph,
        "legacy_package_loaded": False, "legacy_package_available": importlib.util.find_spec("btc_quant_agent") is not None,
        "isolated_interpreter": bool(sys.flags.isolated),
    }
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
