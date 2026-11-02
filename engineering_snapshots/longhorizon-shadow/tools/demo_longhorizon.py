"""Create a clearly synthetic local source/shadow report. No native network calls."""
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def deny(*args, **kwargs):
    raise AssertionError("DEMO_NATIVE_NETWORK_FORBIDDEN")


socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.getaddrinfo = deny

from longhorizon.fixtures import structural_replay  # noqa: E402
from btc_quant_agent.platform.canary.longhorizon_runtime import save_dashboard  # noqa: E402
from btc_quant_agent.platform.canary.public_data import normalize  # noqa: E402

root = Path(__file__).resolve().parents[1] / "artifacts/engineering/synthetic_demo"
if root.exists():
    raise SystemExit("Existing synthetic demo is immutable; inspect its report instead.")
c, scope, store, journal, engine = structural_replay(root, count=66)
model = engine.report()
value = {"exposure": "SYNTHETIC", "model": model, "replay": journal.audit_replay(normalize),
         "native_market_calls": 0, "source_qualified": False, "shadow_advisory_qualified": False}
(root / "report.json").write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
save_dashboard(root, value)
print(json.dumps({"report": str(root / "report.json"), "dashboard": str(root / "dashboard_final.html"),
                  "native_market_calls": 0, "exposure": "SYNTHETIC"}))
