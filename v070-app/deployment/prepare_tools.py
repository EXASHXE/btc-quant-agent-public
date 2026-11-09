"""Freeze existing installed/cached build/QA artifacts; never downloads packages."""

from __future__ import annotations

import importlib.metadata as metadata
import json
from pathlib import Path
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_release import cached_wheel, rewheel  # noqa:E402


def main():
    runtime = json.loads((ROOT / "release/dependency_provenance.json").read_text())
    selected = {canonicalize_name(r["name"]): r for r in runtime}
    pending = ["setuptools", "wheel", "packaging", "pytest", "ruff", "mypy"]
    seen = set()
    wheelhouse = ROOT / "release/wheelhouse"
    while pending:
        name = canonicalize_name(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        dist = metadata.distribution(name)
        if name not in selected:
            # Ruff's standalone executable is outside site-packages: its original
            # wheel must be used, rather than silently dropping that entrypoint.
            if name == "ruff":
                row = cached_wheel(name, dist.version, wheelhouse)
            else:
                try:
                    row = rewheel(name, dist, wheelhouse)
                except ValueError as exc:
                    if not str(exc).startswith(
                        ("DEPENDENCY_RECORD_MISMATCH:", "DEPENDENCY_FILE_WITHOUT_RECORD_HASH:")
                    ):
                        raise
                    row = cached_wheel(name, dist.version, wheelhouse)
            selected[name] = row
        for text in dist.requires or []:
            req = Requirement(text)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                dependency = canonicalize_name(req.name)
                version = (
                    selected[dependency]["version"] if dependency in selected else metadata.version(req.name)
                )
                if not req.specifier.contains(version):
                    raise ValueError("TOOLCHAIN_DEPENDENCY_CONFLICT:" + dependency)
                pending.append(req.name)
    rows = [selected[n] for n in sorted(selected)]
    (ROOT / "release/toolchain_provenance.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    (ROOT / "release/toolchain-lock.txt").write_text(
        "".join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}\n" for r in rows)
    )
    print(
        json.dumps(
            {
                "status": "FROZEN_OFFLINE",
                "runtime_plus_build_QA_distributions": len(rows),
                "network_requests": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
