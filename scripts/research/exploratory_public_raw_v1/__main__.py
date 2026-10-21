"""No auto-discovery, downloads, account interface, or synthetic admission mode."""

import argparse

from . import GateError
from .runner import execute


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--accepted-registry-id', required=True)
    args = parser.parse_args(argv)
    try:
        result = execute(args.registration, args.manifest, args.accepted_registry_id)
    except (GateError, KeyError, TypeError, ValueError) as exc:
        print(f'SOURCE_OR_ADAPTER_BLOCKED: {exc}')
        return 2
    print(result['result_status'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
