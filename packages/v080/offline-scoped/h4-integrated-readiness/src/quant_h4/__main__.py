"""The delivered command reports capability status and local prospective scope only."""

import argparse
import json


def main():
    parser = argparse.ArgumentParser(prog="python -m quant_h4")
    parser.add_argument("command", choices=("status", "market-plan"))
    args = parser.parse_args()
    if args.command == "status":
        print("BLOCKED_LIVE_GATE")
        return 3

    from .market import packet

    print(json.dumps(packet(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
