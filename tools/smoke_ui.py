"""Short-lived loopback-only UI smoke. Always terminates its own server child."""

from http.client import HTTPConnection
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
child = subprocess.Popen(
    [sys.executable, "-m", "btc_quant_agent.platform", "ui", "--port", str(port)],
    cwd=root,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
)
results = {}
try:
    for attempt in range(40):
        try:
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", "/")
            response = connection.getresponse()
            markup = response.read().decode()
            assert response.status == 200 and "local synthetic workbench" in markup
            results["page"] = response.status
            connection.close()
            break
        except OSError:
            if child.poll() is not None:
                raise RuntimeError("UI server exited before loopback smoke")
            time.sleep(0.1)
    else:
        raise RuntimeError("UI server did not become ready")
    connection = HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request("GET", "/api/catalog")
    response = connection.getresponse()
    catalog = json.loads(response.read())
    assert response.status == 200 and "trend_breakout" in catalog["strategies"]
    results["catalog"] = {"strategies": len(catalog["strategies"]), "factors": len(catalog["factors"])}
    payload = json.dumps({"bars": 80, "universe": ["BTCUSDT"], "scenario": "trend"})
    connection.request(
        "POST", "/api/run", body=payload, headers={"Content-Type": "application/json", "X-Quant-Local": "1"}
    )
    response = connection.getresponse()
    run = json.loads(response.read())
    assert response.status == 200 and len(run["run_id"]) == 64
    results["run_id"] = run["run_id"]
    connection.request("GET", "/report?id=" + run["run_id"])
    response = connection.getresponse()
    report = response.read().decode()
    assert response.status == 200 and "SYNTHETIC" in report
    results["report"] = response.status
    connection.request("POST", "/api/run", body=payload)
    response = connection.getresponse()
    response.read()
    assert response.status == 403
    results["unmarked_post_rejected"] = response.status
    connection.close()
finally:
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)
results.update(exposure="SYNTHETIC", server_stopped=True, external_requests=0)
(root / "artifacts/ui_smoke.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results))
