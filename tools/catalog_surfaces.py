"""Catalog current tracked surfaces without opening stores or sealed evidence.

Engineering inventory only; never protocol or promotion authority.
Historical proposals live in Git history, not active-path metadata.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "2.0.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPOSITORY_ROOT, text=True,
    ).strip()


def _module(path: str) -> str:
    return path.removeprefix("src/").removesuffix(".py").replace("/", ".").removesuffix(
        ".__init__"
    )


def find_imports_in_file(path: Path) -> list[str]:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    module = _module(relative)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    imported = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                parts = package.split(".")
                target = ".".join(
                    parts[:len(parts) - node.level + 1] + ([target] if target else [])
                )
            imported.append(target)
            imported.extend(f"{target}.{alias.name}" for alias in node.names)
    return sorted(set(imported))


def get_cli_entrypoints() -> list[str]:
    # Parser construction only: no service, network, SQLite, scan or dispatch.
    from btc_quant_agent.cli import build_parser

    def walk(parser: argparse.ArgumentParser, prefix: str = "") -> list[str]:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                return [
                    leaf
                    for name, child in action.choices.items()
                    for leaf in walk(child, f"{prefix} {name}".strip())
                ]
        return [prefix]

    return sorted(walk(build_parser()))


def get_api_routes() -> list[dict[str, str]]:
    tree = ast.parse((REPOSITORY_ROOT / "src/btc_quant_agent/api.py").read_text())
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"get", "post", "put", "delete", "patch"}
                    and decorator.args and isinstance(decorator.args[0], ast.Constant)):
                routes.append({"method": decorator.func.attr.upper(),
                               "path": str(decorator.args[0].value)})
    return sorted(routes, key=lambda route: (route["path"], route["method"]))


def _classification(path: str, machine_evidence: set[str]) -> tuple[str, str]:
    if path in machine_evidence:
        return "DEFER_PROTECTED", "Machine-read runtime registry evidence; safety validation requires it."
    if (path.startswith(("src/btc_quant_agent/h39_", "tools/run_h39_", "configs/forward/",
                         "configs/research/"))
            or path in {"src/btc_quant_agent/microstructure_research.py",
                        "src/btc_quant_agent/backtest.py",
                        "src/btc_quant_agent/research.py",
                        "src/btc_quant_agent/mechanism_research.py",
                        "configs/frozen/v0.2.2.toml",
                        "configs/research_registry.json"}):
        return "DEFER_PROTECTED", "Frozen scientific, operational or compatibility guard surface."
    if path.startswith("deliverables/"):
        version = int(path.split("/")[1].rsplit(".", 1)[1])
        if version >= 22:
            return "DEFER_PROTECTED", "H39 evidence/context; metadata only, not opened."
        return "DEFER_UNCERTAIN", "Forward evidence lineage; authority split not attempted."
    if path == "docs/OPTIMIZED_DESIGN.md" or path.startswith("scripts/maintenance/"):
        return "DEFER_UNCERTAIN", "Independent design/maintenance scope not proven dead."
    return "KEEP_CURRENT", "Retained current code, tests, packaging or support."


def generate_catalog() -> dict[str, Any]:
    registry = json.loads((REPOSITORY_ROOT / "configs/research_registry.json").read_text())
    machine_evidence = {path for component in registry["components"]
                        for path in component["evidence_paths"]}
    tracked = sorted(set(_git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()))
    files = [path for path in tracked if (REPOSITORY_ROOT / path).is_file()]
    python = [path for path in files if path.endswith(".py")
              and path.startswith(("src/", "tools/", "tests/", "skill-template/"))]
    modules = {_module(path): path for path in python}
    consumers: dict[str, list[str]] = {path: [] for path in python}
    dangling = []
    for consumer in python:
        for imported in find_imports_in_file(REPOSITORY_ROOT / consumer):
            target = imported
            while target and target not in modules:
                target = target.rpartition(".")[0]
            if target:
                provider = modules[target]
                if provider != consumer and consumer not in consumers[provider]:
                    consumers[provider].append(consumer)
            if imported.startswith("btc_quant_agent."):
                parts = imported.split(".")
                # A missing top-level internal module cannot be a package attribute.
                if ".".join(parts[:2]) not in modules and not any(
                    name.startswith(".".join(parts[:2]) + ".") for name in modules
                ) and parts[1] != "__version__":
                    dangling.append({"consumer": consumer, "import": imported})
    inventory = []
    for path in files:
        classification, reason = _classification(path, machine_evidence)
        item: dict[str, Any] = {"path": path, "classification": classification, "reason": reason}
        if path in consumers:
            item["physical_loc"] = len((REPOSITORY_ROOT / path).read_bytes().splitlines())
            item["active_importers_or_consumers"] = sorted(consumers[path])
        inventory.append(item)
    return {"schema_version": SCHEMA_VERSION, "generated_from_git_sha": _git("rev-parse", "HEAD"),
            "classification_buckets": ["KEEP_CURRENT", "DELETE_R01", "DEFER_PROTECTED", "DEFER_UNCERTAIN"],
            "surface_inventory": inventory, "protected_evidence_paths": sorted(machine_evidence),
            "cli_entrypoints": get_cli_entrypoints(),
            "api_routes": get_api_routes(), "dangling_internal_imports": sorted(
                dangling, key=lambda item: (item["consumer"], item["import"])),
            "summary": {"tracked_files": len(files), "python_files": len(python),
                        "active_import_edges": sum(len(value) for value in consumers.values())}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", type=Path, help="Explicit engineering JSON path; default stdout")
    args = parser.parse_args()
    content = json.dumps(generate_catalog(), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(content, end="")
    else:
        output = args.output.resolve()
        for forbidden in (REPOSITORY_ROOT / "prompts", REPOSITORY_ROOT / "reviews"):
            if output.is_relative_to(forbidden):
                parser.error("agent documents belong on v0.5-refactor-docs, not the code branch")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
