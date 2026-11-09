# ruff: noqa: E402
# Source/bootstrap path is established before optional installed Quant imports.
"""Actual Windows QPC/NTFS + fabricated loopback CONNECT/TLS; no real market data."""

from pathlib import Path
import hashlib
import json
import socket
import sys
import tempfile
import ipaddress
import platform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.fixtures import LoopbackMockVenue
from win_capture.capture import capture_session
from win_capture.bundle import verify_ntfs
from win_capture.win_clock import sample_windows_clocks, check_windows_pair_coherence, query_w32tm_readonly

original = socket.socket.connect


def local(sock, address):
    if not ipaddress.ip_address(address[0]).is_loopback:
        raise RuntimeError("OFFLINE_EXTERNAL_NETWORK_FORBIDDEN")
    return original(sock, address)


socket.socket.connect = local
root = Path(tempfile.mkdtemp(prefix="Quant_S_NTFS_SYNTHETIC_"))
volume = verify_ntfs(root)
print(json.dumps({"created_QA_root": str(root), "real_market_data": False}), flush=True)
v = LoopbackMockVenue(root / "tls")
v.connect_tunnel = True
try:
    first = sample_windows_clocks()
    m = capture_session(root / "bundle", qa=v.qa)
    last = sample_windows_clocks()
    coherence = check_windows_pair_coherence(first, last)
    receipt = {
        "class": "SYNTHETIC_LOOPBACK_QA_NOT_MARKET",
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "bundle_path": str(root / "bundle"),
        "NTFS": volume,
        "Windows_first": first,
        "Windows_last": last,
        "coherence": coherence,
        "W32Time": query_w32tm_readonly(),
        "bundle_sha256": m["bundle_sha256"],
        "requests": m["requests"],
        "weight": m["request_weight"],
        "CONNECT_calls": v.connect_calls,
        "exchange_requests": 0,
        "strict_UTC": False,
        "source_files": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "win_capture").glob("*.py")
        },
    }
    print(json.dumps(receipt, sort_keys=True))
    (ROOT / "audit/S_NATIVE_NTFS_RECEIPT.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
finally:
    v.close()
