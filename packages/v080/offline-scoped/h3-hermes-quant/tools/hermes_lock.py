"""Fingerprint the preinstalled, independently accepted Hermes Python environment."""

import json
import re
import sys
from hashlib import sha256
from importlib import metadata
from pathlib import Path

library = Path(sys.prefix) / "lib/python3.11/site-packages"
packages = []
for dist in metadata.distributions(path=[str(library)]):
    name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
    entry = {"name": name, "version": dist.version}
    for file in ("METADATA", "RECORD"):
        contents = dist.read_text(file)
        entry[file.lower() + "_sha256"] = (
            sha256(contents.encode()).hexdigest() if contents else None
        )
    packages.append(entry)
packages.sort(key=lambda item: (item["name"], item["version"]))
if not any(p["name"] == "hermes-agent" and p["version"] == "0.16.0" for p in packages):
    raise SystemExit("PINNED_HERMES_NOT_FOUND")
if not any(p["name"] == "lark-oapi" and p["version"] == "1.5.3" for p in packages):
    raise SystemExit("PINNED_LARK_NOT_FOUND")
print(
    json.dumps(
        {
            "schema": "H3_HERMES_INSTALLED_METADATA_LOCK_V1",
            "python": sys.version.split()[0],
            "packages": packages,
        },
        indent=2,
        sort_keys=True,
    )
)
