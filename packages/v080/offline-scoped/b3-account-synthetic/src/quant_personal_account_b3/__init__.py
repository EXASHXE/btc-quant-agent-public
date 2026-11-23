"""QUANT v0.8.0 B3 offline account-aware decision support package.

Strictly offline, GET-only synthetic private-account fixture boundary.
No live HTTP transport, no real credentials, no real account connection,
and no Layer 3 TRADE_EXECUTION capability exist in this package.
"""

from __future__ import annotations

from .models import (
    ACCOUNT_REALITY_BANNER,
    CONNECTION_MODE_FIXTURE,
    EVIDENCE_CLASS_SYNTHETIC,
    LAYER3_STATUS,
    PRIVATE_CONNECTION_NOT_ACTIVATED,
    SYNTHETIC_BANNER_TEXT,
    AccountB3Error,
)

__version__ = "0.8.0b3"

__all__ = [
    "ACCOUNT_REALITY_BANNER",
    "AccountB3Error",
    "CONNECTION_MODE_FIXTURE",
    "EVIDENCE_CLASS_SYNTHETIC",
    "LAYER3_STATUS",
    "PRIVATE_CONNECTION_NOT_ACTIVATED",
    "SYNTHETIC_BANNER_TEXT",
    "__version__",
]
