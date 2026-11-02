"""Fabricated subprocess worker for genuine SQLite/atomic-file crash tests. No transport."""

import json
import os
from pathlib import Path
import socket
import sys


def blocked(*args, **kwargs):
    raise AssertionError("OFFLINE_CHILD_NETWORK_DISABLED")


def main():
    socket.socket.connect = blocked
    socket.getaddrinfo = blocked
    from btc_quant_agent.platform.canary.control import BudgetGuard, CanaryStore, CircuitOpen
    from btc_quant_agent.platform.canary.policy import ROOT, StoragePolicy, load_catalog, load_policy
    from btc_quant_agent.platform.canary.storage import ReceiptStorage

    mode, folder = sys.argv[1], Path(sys.argv[2])
    folder.mkdir(parents=True, exist_ok=True)
    store = CanaryStore(folder / "canary.sqlite")
    if mode == "budget":
        p = load_policy(ROOT / "configs/canary/offline.yaml").model_copy(
            update={"ip_weight_per_minute": 3, "retry_weight_reserve_per_minute": 1}
        )
        try:
            BudgetGuard(store, p).request(
                load_catalog(ROOT / "configs/canary/endpoints.json")["binance_usdm_oi"], {}, 1000
            )
            print("ACCEPT")
        except CircuitOpen:
            print("BLOCK")
    elif mode == "chunk-crash":

        def crash(point):
            os._exit(67)

        s = ReceiptStorage(folder, store, StoragePolicy(), crash_hook=crash)
        s.write("RAW", "BTCUSDT", ({"exposure": "SYNTHETIC", "value": 1},), 1000, 2000)
    elif mode == "recover":
        s = ReceiptStorage(folder, store, StoragePolicy())
        s.recover_orphans()
        print(json.dumps(s.audit()))
    elif mode == "source":
        state, reason = store.accept(
            "binance_usdm_bbo_ws",
            "BTCUSDT",
            epoch=0,
            sequence=1,
            native_ms=1000,
            payload_hash="immutable",
            receive_ms=1100,
            instrument_hash="fabricated",
        )
        print(json.dumps({"state": state, "reason": reason}))
    else:
        raise ValueError("UNKNOWN_OFFLINE_WORKER")


if __name__ == "__main__":
    main()
