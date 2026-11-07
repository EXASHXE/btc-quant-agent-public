"""Synthetic contract/store microbenchmark; not a native source release test."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path


def blocked(*args, **kwargs):
    raise AssertionError('LT_A_NATIVE_NETWORK_FORBIDDEN')


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.getaddrinfo = blocked


def main():
    from btc_quant_agent.domain import Candle
    from btc_quant_agent.platform.swing import INTERVALS, ClosedBar, State, decide
    from btc_quant_agent.platform.swing_store import DecisionStore

    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--store', required=True)
    args = parser.parse_args()
    output, path = Path(args.output), Path(args.store)
    project = Path(__file__).resolve().parent.parent
    for destination, boundary in ((output, project.parent), (path, project)):
        if (not destination.resolve().is_relative_to(boundary)
                or any(p.is_symlink() for p in (destination, *destination.parents))):
            raise ValueError('BENCHMARK_OUTPUT_OUTSIDE_ISOLATED_WORKSPACE')
    if output.exists() or path.exists():
        raise ValueError('BENCHMARK_OUTPUT_EXISTS')
    store = DecisionStore(path)
    start = int(datetime(2026, 11, 6, tzinfo=UTC).timestamp() * 1000)
    elapsed = []
    started = time.perf_counter_ns()
    for cycle in range(48):
        trigger = start + cycle * INTERVALS['4H']
        for symbol in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT'):
            bars = []
            for timeframe in ('4H', '1D'):
                size = INTERVALS[timeframe]
                latest = trigger // size * size
                for end in range(latest - 59 * size, latest + size, size):
                    c = Candle(symbol, timeframe, end-size, end-1, 100, 101, 99, 100, 10,
                               available_at_ms=end+10)
                    bars.append(ClosedBar(candle=c, source_id='fabricated', source_event_ms=end,
                                          received_ms=end+5, available_ms=end+10, durable_ms=end+20))
            before = time.perf_counter_ns()
            snapshot = decide(symbol=symbol, decision_ms=trigger+30_000,
                              trigger_close_ms=trigger, bars=bars)
            assert snapshot.state is State.NO_SETUP
            store.append(snapshot)
            elapsed.append((time.perf_counter_ns()-before)/1_000_000)
    total_s = (time.perf_counter_ns()-started)/1_000_000_000
    ordered = sorted(elapsed)
    report = {
        'schema': 'LT_A_SYNTHETIC_CONTRACT_MICROBENCHMARK_V1',
        'workload': '48 completed 4H triggers x 3 symbols; 60 4H + 60 1D bars per prefix',
        'calls': len(elapsed), 'native_market_requests': 0, 'source_qualified': False,
        'shadow_qualified': False, 'no_setup_decisions': len(elapsed),
        'code_sha256': {name: hashlib.sha256((project/name).read_bytes()).hexdigest()
                        for name in ['src/btc_quant_agent/platform/swing.py',
                                     'src/btc_quant_agent/platform/swing_store.py',
                                     'tools/swing_benchmark.py']},
        'measured_scope': 'offline validation, prefix hashing, SQLite synchronous FULL append only',
        'not_measured': ['native source availability', 'native latency', 'transport recovery',
                         'venue correctness', 'M1B sustained150/s', 'LT-B release qualification'],
        'total_seconds_including_fixture_generation': total_s,
        'validation_and_persist_ms': {'p50': statistics.median(elapsed),
                                      'p95': ordered[int(0.95*(len(ordered)-1))],
                                      'p99': ordered[int(0.99*(len(ordered)-1))], 'max': max(elapsed)},
    }
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
