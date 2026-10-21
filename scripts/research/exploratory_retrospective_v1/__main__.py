"""Explicit synthetic structural check only; all other invocation fails closed."""

import argparse
import json

from .synthetic import self_check


def main() -> None:
    parser = argparse.ArgumentParser(description="Disabled research mode; artificial self-check only")
    parser.add_argument("--synthetic-self-check", action="store_true")
    args = parser.parse_args()
    if not args.synthetic_self_check:
        parser.error("MODE_DISABLED_BY_DEFAULT: real execution is unavailable")
    print(json.dumps(self_check(), sort_keys=True))


if __name__ == "__main__":
    main()
