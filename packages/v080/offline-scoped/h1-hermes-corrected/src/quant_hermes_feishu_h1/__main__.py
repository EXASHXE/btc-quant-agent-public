"""Module entrypoint for ``python -m quant_hermes_feishu_h1``."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
