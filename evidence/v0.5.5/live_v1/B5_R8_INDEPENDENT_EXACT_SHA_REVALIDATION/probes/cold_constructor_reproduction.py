"""Unmodified concurrent cold constructors, target/parent differential probe."""
import hashlib
import json
import subprocess
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor.supervisor import PositionSupervisor

source = Path.cwd()
records = []
for repetition in range(3):
    with tempfile.TemporaryDirectory(prefix="b5-r8-cold-repeat-") as tmp:
        path = Path(tmp) / "new.sqlite"
        barrier = Barrier(6)

        def construct(index):
            barrier.wait(timeout=20)
            try:
                PositionSupervisor(path)
                return {"index": index, "status": "PASS"}
            except Exception as exc:
                return {"index": index, "status": "FAIL", "error": repr(exc),
                        "traceback": traceback.format_exc()}

        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(construct, range(6)))
        with connection(path) as db:
            columns = [r["name"] for r in db.execute("PRAGMA table_info(live_position_events)")]
            triggers = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")]
            recursive = db.execute("PRAGMA recursive_triggers").fetchone()[0]
        records.append({"repetition": repetition, "constructors": outcomes,
                        "final_event_columns": columns, "final_triggers": triggers,
                        "recursive_triggers": recursive,
                        "successful_constructors": sum(r["status"] == "PASS" for r in outcomes)})

sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
result = {"source_checkout": str(source), "sha": sha, "python": sys.version,
          "import": sys.modules[PositionSupervisor.__module__].__file__,
          "script_sha256": script_hash, "records": records,
          "failed_constructors": sum(r["status"] == "FAIL" for record in records for r in record["constructors"])}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"sha": sha, "failed_constructors": result["failed_constructors"],
                  "repetitions": len(records)}))
