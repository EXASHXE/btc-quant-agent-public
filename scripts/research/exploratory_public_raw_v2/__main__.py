"""Explicit offline execution. No trust installation or synthetic mode."""

import argparse

from ..exploratory_public_raw_v1 import GateError
from .runner import execute


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--accepted-registry-id', required=True)
    args = parser.parse_args(argv)
    try:
        receipt = execute(args.registration, args.manifest, args.accepted_registry_id)
    except (GateError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f'SOURCE_REPAIR_BLOCKED_EXACT: {exc}')
        return 2
    print(receipt['terminal'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
