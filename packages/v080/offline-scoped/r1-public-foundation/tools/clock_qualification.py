"""One bounded read-only epoch qualification attempt; a stop never resets the epoch."""

from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from btc_quant_agent.platform.native.clock import Clock  # noqa:E402

clock = Clock()
start = time.monotonic()
samples = []
failure = None
while time.monotonic() - start < 15:
    try:
        samples.append(clock.sample())
    except ValueError as error:
        failure = str(error)
        break
    time.sleep(0.01)
value = {
    "status": "HOST_CLOCK_UNQUALIFIED",
    "duration_seconds": time.monotonic() - start,
    "max_seconds": 15,
    "samples": samples,
    "failure": failure,
    "failure_evidence": clock.failure_evidence,
    "epoch_resets": 0,
    "absolute_UTC_uncertainty_ms": None,
    "native_probes": "NOT_RUN",
    "qualified": False,
    "E_performance_reclassified_PASS": False,
}
Path(sys.argv[1]).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
print(json.dumps({k: v for k, v in value.items() if k != "samples"}))
