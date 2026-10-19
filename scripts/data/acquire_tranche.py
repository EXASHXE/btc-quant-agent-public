#!/usr/bin/env python3
"""Convenience script entrypoint for V065-DATA-R2 Data Acquisition."""
import sys
from pathlib import Path

# Ensure quant-0.6.5 root is in sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
src_root = repo_root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

from tools.data.pipeline import main

if __name__ == "__main__":
    sys.exit(main())
