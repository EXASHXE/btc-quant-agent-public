"""Read-only final source/wheel/config binding receipt; never signs or acquires."""

from pathlib import Path
import hashlib
import json
import sys

from btc_quant_agent.platform.native.contract import Policy, digest, source_hash, strict

policy = Policy.model_validate(strict(Path(sys.argv[1]).read_bytes()))
print(
    json.dumps(
        {
            "source_sha256": source_hash(),
            "executable_sha256": hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest(),
            "config_sha256": digest(policy.model_dump(mode="json")),
            "authorization": False,
        },
        sort_keys=True,
    )
)
