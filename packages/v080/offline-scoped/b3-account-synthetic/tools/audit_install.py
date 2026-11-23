"""Audit the isolated installed B3 distribution, hash-pinned dependency graph, and AST isolation."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

PKG = "quant_personal_account_b3"
B2 = "quant_personal_decision_b2"
B1 = "quant_personal_public_b1"
B1_PIN = "19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f"
B2_PIN = "29cce34ff2b751ef9a9d305d3b7591281a6028c0057e360c9eb666b0840fed64"

FORBIDDEN_STDLIB = {"socket", "ssl", "http", "urllib", "subprocess", "ctypes"}


def main() -> None:
    b1_wheel = Path(sys.argv[1])
    b2_wheel = Path(sys.argv[2])
    b1 = metadata.distribution("quant-personal-public-b1")
    b2 = metadata.distribution("quant-personal-decision-b2")
    b3 = metadata.distribution("quant-personal-account-b3")

    assert hashlib.sha256(b1_wheel.read_bytes()).hexdigest() == B1_PIN
    assert hashlib.sha256(b2_wheel.read_bytes()).hexdigest() == B2_PIN
    assert b1.version == "0.8.0b1" and not (b1.requires or [])
    assert b2.version == "0.8.0b2" and b2.requires == ["quant-personal-public-b1==0.8.0b1"]
    assert b3.version == "0.8.0b3" and b3.requires == ["quant-personal-decision-b2==0.8.0b2"]
    assert [(e.group, e.name, e.value) for e in b3.entry_points] == [
        ("console_scripts", "quant-account-b3", f"{PKG}.cli:main"),
    ]

    for wheel_path, dist, ns in ((b1_wheel, b1, B1), (b2_wheel, b2, B2)):
        with zipfile.ZipFile(wheel_path) as z:
            for item in z.namelist():
                if item.startswith(ns + "/") and item.endswith(".py"):
                    assert z.read(item) == Path(dist.locate_file(item)).read_bytes()

    files = sorted(str(path) for path in b3.files or [])
    source = [path for path in files if path.endswith(".py")]
    assert source and all(path.startswith(PKG + "/") for path in source)
    assert not any("btc_quant_agent" in path or B1 in path or B2 in path for path in files)

    allowed_roots = (sys.stdlib_module_names - FORBIDDEN_STDLIB) | {PKG, B2}
    graph: dict[str, list[str]] = {}
    for path in source:
        tree = ast.parse(Path(b3.locate_file(path)).read_text(encoding="utf-8"), filename=path)
        imports: list[str] = []
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
                assert not isinstance(node.func, ast.Attribute) or node.func.attr not in {"import_module", "getenv"}
            elif isinstance(node, ast.Attribute):
                assert node.attr != "environ"
        assert all(name.split(".")[0] in allowed_roots for name in imports), f"Disallowed import in {path}: {imports}"
        graph[path] = sorted(set(imports))

    from quant_personal_account_b3.client import PrivateUserDataClient
    from quant_personal_account_b3.overlay import build_account_overlay

    assert PrivateUserDataClient.__module__.startswith(PKG)
    assert build_account_overlay.__module__.startswith(PKG)
    assert not any(key == "btc_quant_agent" or key.startswith("btc_quant_agent.") for key in sys.modules)

    print(
        json.dumps(
            {
                "distribution": b3.metadata["Name"],
                "version": b3.version,
                "runtime_dependencies": b3.requires,
                "b1_wheel_sha256": B1_PIN,
                "b2_wheel_sha256": B2_PIN,
                "b1_installed_source_byte_match": True,
                "b2_installed_source_byte_match": True,
                "b3_file_inventory": files,
                "b3_import_graph": graph,
                "isolated": bool(sys.flags.isolated),
                "legacy_installed": importlib.util.find_spec("btc_quant_agent") is not None,
                "legacy_imported": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
