"""Real subprocess, synthetic SQLite/fake-sender evidence only. Network is denied."""

import json
import os
import socket
import sys
from pathlib import Path

from btc_quant_agent.platform.selection.store import Capital, SelectorStore
from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.selection.selector import advance_regime


def blocked(*args, **kwargs):
    raise RuntimeError("OFFLINE_NETWORK_BLOCKED")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.getaddrinfo = blocked
store = SelectorStore(sys.argv[1])
mode = sys.argv[2]
if mode == "regime":
    step = int(sys.argv[3])
    metrics = {
        "usable": True,
        "adx": 30,
        "T": 0.8,
        "slope": 0.1,
        "ER": 0.5,
        "range_intact": True,
        "z_return": 0.1,
        "oi_change": None,
        "rvol": 1,
        "high_volatility_proxy": False,
    }
    state = advance_regime(store.regime("BTCUSDT"), metrics, step)
    print(json.dumps(store.save_regime("BTCUSDT", state), sort_keys=True))
elif mode in {"episode_crash_after_prepare", "episode_resume"}:
    anchors = {"id": "episode-restart", "symbol": "BTCUSDT"}
    e = store.create_episode(anchors, 100)
    if not e["state"]["trigger_ids"]:
        store.transition(
            anchors["id"], e["revision"], {**e["state"], "status": "ARMED", "trigger_ids": ["t1", "t2"]}, 101
        )
    e = store.episode(anchors["id"])
    if mode == "episode_crash_after_prepare":
        origin = fingerprint([anchors["id"], "TRIGGER_NOTICE"])
        identity = store.commit_decision(e, 102, 102, origin=origin)
        store.prepare(identity, "BTCUSDT", 102)
        os._exit(24)

    def local_sender(wire):
        with Path(sys.argv[3]).open("a") as f:
            f.write(json.dumps(wire) + "\n")

    event = store.notify_episode(anchors["id"], 103, local_sender)
    print(json.dumps({"event": event, "status": store.get_notification(event)["status"]}))
elif mode == "reserve":
    proposal = {
        "episode_id": sys.argv[3],
        "symbol": "BTCUSDT",
        "side": 1,
        "beta": 1,
        "risk": 40,
        "notional": 1000,
        "margin": 1000,
        "cluster": "COMMON",
    }
    limits = {"total_risk": 0.005, "cluster_risk": 0.005, "gross": 2, "symbol": 0.5, "net_beta": 0.5}
    try:
        store.reserve(proposal, Capital(10000, 10000, 100), 100, limits)
    except ValueError as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}))
    else:
        print(json.dumps({"status": "RESERVED"}))
else:
    identity = store.commit_decision(
        {"source": "SYNTHETIC", "risk": "EXIT"}, 100, 101, origin="restart-fixture"
    )
    event = store.prepare(identity, "BTCUSDT", 101)

    def sender(wire):
        with Path(sys.argv[3]).open("a") as f:
            f.write(json.dumps(wire, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if mode == "crash_send":
            os._exit(23)

    result = store.dispatch(event, sender, 102)
    print(json.dumps({"status": result, "delivery": store.delivery(event)["delivery"]}, sort_keys=True))
