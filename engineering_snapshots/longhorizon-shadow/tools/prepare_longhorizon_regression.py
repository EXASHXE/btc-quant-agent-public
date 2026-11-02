"""Source-only offline regression fixture; no old runtime store or payload copy."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "artifacts/engineering/regression"
BASE = ROOT.parent / "l4-readonly-source-canary-01"
copied = {}
for folder in ("src", "tests", "configs", "tools"):
    for path in (ROOT / folder).rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        relative = path.relative_to(ROOT)
        target = TARGET / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        copied[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
for name in ("pyproject.toml", "L4_BC_OWNER_ATTESTATION_20261029.md", "L4_BC_WINDOW_AMENDMENT_20261029.md"):
    path = ROOT / name if name == "pyproject.toml" else BASE / name
    shutil.copyfile(path, TARGET / name)
(TARGET / "configs/canary/session02_owner_keys.json").write_text(
    json.dumps({"version": "L4_SESSION02_OWNER_KEYS_V1", "keys": {}}, indent=2) + "\n")
code = '''
import json
from btc_quant_agent.platform.canary import public_policy as p
from btc_quant_agent.platform.core import fingerprint
hashes = p.current_source_hashes()
binding = json.loads(p.SOURCE_BINDING.read_text())
binding['files'] = hashes
p.SOURCE_BINDING.write_text(json.dumps(binding, indent=2)+'\\n')
scope = json.loads(p.DEFAULT_GRANT.read_text())
scope['policy']['source_fingerprint'] = fingerprint(hashes)
scope['source_grant']['policy_hash'] = fingerprint(scope['policy'])
scope['source_grant']['output_path'] = str(p.OUTPUT)
p.DEFAULT_GRANT.write_text(json.dumps(scope, indent=2)+'\\n')
p.OUTPUT.mkdir(parents=True, exist_ok=True)
p.load_scope()
'''
subprocess.run([sys.executable, "-c", code], cwd=TARGET, check=True,
               env={**os.environ, "PYTHONPATH": str(TARGET / "src"), "PYTHONDONTWRITEBYTECODE": "1"})
receipt = {"purpose": "Unchanged inherited tests on the new code; source-only offline fixture",
           "copied_files": copied, "original_tests_modified": False, "native_activation": False,
           "raw_payloads_copied": False, "runtime_stores_copied": False,
           "fixture_changes": ["Relocate copied OFFLINE scope output_path to fixture root",
               "Rebind copied offline source manifest to modified isolated code",
               "Use empty copied Session02 trust store matching its original offline preparation fixture"],
           "original_key_store_modified": False}
(ROOT / "artifacts/engineering/regression_fixture.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({"source_only_fixture": str(TARGET), "files": len(copied), "native_activation": False}))
