"""Run: python3 -m q0b --output artifacts (zero external requests)."""
import argparse
import json
from pathlib import Path

from .examples import artifacts


def main():
    parser = argparse.ArgumentParser(description="Synthetic-only S1_INTRADAY_MTF_V2 example cards")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    values = artifacts()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        for name, value in values.items():
            (args.output / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"schema": "S1_INTRADAY_MTF_V2", "synthetic_only": True,
                      "network_calls": 0, "outputs": list(values),
                      "acceptance": "PENDING_CONTROLLER_0_C"}, sort_keys=True))


if __name__ == "__main__":
    main()
