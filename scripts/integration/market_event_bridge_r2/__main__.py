"""Main execution entry point for market_event_bridge_r2 module."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
