"""One dormant manual production entry, without test or override switches."""

import json
import re
import sys

from quant_s2v2.protocol import Denied

from . import CLOSED
from .runtime import run_production


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["manual-once"]:
        print(CLOSED, file=sys.stderr)
        return 3
    try:
        result = run_production()
    except (Denied, OSError, ValueError, TypeError, KeyError) as exc:
        code = str(exc)
        print(code if re.fullmatch(r"[A-Z0-9_]+", code) else CLOSED, file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
