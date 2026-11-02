"""Finite fabricated-process tests only; never a public-network entry point."""

import json
import os
from pathlib import Path
import socket
import sys


def main():
    def blocked(*a, **kw):
        raise AssertionError("PUBLIC_WORKER_OFFLINE_ONLY")

    socket.socket.connect = blocked
    socket.getaddrinfo = blocked
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from canary_public.fixtures import Clock, Backend, meta_payload, record, wire
    from btc_quant_agent.platform.canary.public_policy import START, load_scope
    from btc_quant_agent.platform.canary.public_data import normalize
    from btc_quant_agent.platform.canary.control import CanaryStore
    from btc_quant_agent.platform.canary.public_journal import PublicJournal
    from btc_quant_agent.platform.canary.public_runtime import run_public

    mode, path = sys.argv[1], Path(sys.argv[2])
    path.mkdir(parents=True, exist_ok=True)
    clock = Clock()
    scope = load_scope()
    if mode == "run-until-stop":

        class ReadyBackend(Backend):
            def connect(self, url, timeout, on_control):
                result = super().connect(url, timeout, on_control)
                if "/market/" in url:
                    (path / "worker_ready").write_text("SYNTHETIC_ONLY")
                return result

        result = run_public(scope, enabled=True, clock=clock, backend=ReadyBackend(scope, clock), output=path)
        print(
            json.dumps(
                {
                    "stop_reason": result["stop_reason"],
                    "sockets_closed": result["sockets_closed"],
                    "threads_stopped": result["receiver_threads_stopped"],
                    "native_market_requests": result["native_market_requests"],
                }
            )
        )
        return
    store = CanaryStore(path / "state.sqlite", clock_ms=clock.wall)

    def crash(point):
        os._exit(67)

    journal = PublicJournal(
        path,
        store,
        clock,
        exposure="SYNTHETIC",
        reserve=0,
        crash_hook=crash if mode == "crash-rename" else None,
    )
    if mode == "crash-rename":
        journal.write("raw", [record(scope, wire("binance_usdm_exchange_info", meta_payload(), START + 100))])
    elif mode == "recover":
        print(json.dumps(journal.audit_replay(normalize)))
    elif mode == "complete":
        raw = journal.rows()[0]
        records = journal.read(raw)["records"]
        journal.write("normalized", [normalize(x) for x in records], raw_sha=raw[1])
        print(json.dumps(journal.audit_replay(normalize)))
    else:
        raise ValueError("UNKNOWN_OFFLINE_WORKER")


if __name__ == "__main__":
    main()
