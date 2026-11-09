from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from btc_quant_agent.platform.qualification.clock_diagnostics import run  # noqa: E402

output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
result = run(int(sys.argv[2]) if len(sys.argv) > 2 else 15)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({k: v for k, v in result.items() if k not in {"samples", "cross_process", "clock_info"}}))
