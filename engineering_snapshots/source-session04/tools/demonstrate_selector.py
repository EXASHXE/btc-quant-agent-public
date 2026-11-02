"""Offline user-report and risk-notification fixture after an episode evaluation."""

import argparse
import json
import socket
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.platform.core import InstrumentSpec, UserReportedFill, dec, primitive
from btc_quant_agent.platform.position_management import supervise
from btc_quant_agent.platform.selection.fixtures import bar, market_event, monitor
from btc_quant_agent.platform.selection.lifecycle import record_user_fill
from btc_quant_agent.platform.selection.management import ExitPolicy
from btc_quant_agent.platform.selection.sources import MINUTE
from btc_quant_agent.platform.selection.store import SelectorStore


def blocked(*args, **kwargs):
    raise RuntimeError("OFFLINE_NETWORK_BLOCKED")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.getaddrinfo = blocked
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--evaluation", default="artifacts/final/evaluation")
parser.add_argument("--output", default="artifacts/final/user-position")
args = parser.parse_args()
report = json.loads((Path(args.evaluation) / "episodes.json").read_text())
anchors = next(
    c["anchors"] for c in report["scan"]["candidates"] if c["anchors"]["strategy"] == "trend_pullback"
)
output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)
store = SelectorStore(output / "user.sqlite")
store.create_episode(anchors, anchors["setup_ts"] + 1000)
spec = InstrumentSpec(**anchors["contract"])
fill = UserReportedFill(
    "fabricated-owner-input",
    "user-position-fixture",
    anchors["symbol"],
    "LONG",
    dec(anchors["anchor"]),
    dec(1),
    anchors["setup_ts"] + MINUTE,
    anchors["setup_ts"] + MINUTE + 1000,
)
(output / "fill.json").write_text(json.dumps(primitive(fill), indent=2) + "\n")
position, binding = record_user_fill(store, anchors["id"], fill, spec)
normal = monitor(anchors, 2)
hold = supervise(position, market_event(normal), episode_policy=ExitPolicy(atr=anchors["atr"]))
price = float(position.entry) + 3 * anchors["atr"]
favorable = monitor(anchors, 3, price=price)
favorable = replace(
    favorable,
    bar=bar(spec, favorable.bar.start, price - 0.1, price + 0.1, price - 0.2, price, interval=MINUTE),
)
tighten = supervise(position, market_event(favorable), episode_policy=ExitPolicy(atr=anchors["atr"]))
partial = supervise(
    position, market_event(favorable), episode_policy=ExitPolicy(atr=anchors["atr"], partial_at_r=1.5)
)
gap = monitor(anchors, 4, mode="gap", quote=False)
exit_action = supervise(position, market_event(gap), episode_policy=ExitPolicy(atr=anchors["atr"]))
identity = store.commit_decision(exit_action, gap.now, gap.now, origin="synthetic-risk-notice")
event = store.prepare(identity, anchors["symbol"], gap.now)
wire = []
store.dispatch(event, lambda payload: wire.append(payload), gap.now + 1)
store.dispatch(event, lambda payload: wire.append(payload), gap.now + 2)
receipt = {
    "source_context": "OFFLINE_SYNTHETIC_USER_REPORT_INPUT; no human fill or account proof",
    "episode": anchors["id"],
    "binding": binding,
    "actions": [primitive(x) for x in (hold, tighten, partial, exit_action)],
    "actual_ledger_position": primitive(store.position(position.id)),
    "fake_sender_calls": len(wire),
    "sender_status": store.get_notification(event)["status"],
    "delivery": store.delivery(event),
    "orders": 0,
}
assert receipt["actual_ledger_position"]["status"] == "OPEN"
assert [x["action"] for x in receipt["actions"]] == ["HOLD", "TIGHTEN_STOP", "PARTIAL_EXIT", "EXIT"]
(output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(
    json.dumps(
        {"receipt": str(output / "receipt.json"), "fake_sender_calls": len(wire), "position_status": "OPEN"}
    )
)
