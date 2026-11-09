"""Isolated Windows-native stdlib market capture adapter for Quant v0.7.0 (POC)."""

from .bundle import BundleLedger, write_atomic_bytes
from .capture import WindowsCollector, capture_session, metadata, parse_klines, reference, verify_observation
from .transport import CaptureError, WindowsHttpsTransport, strict_json
from .win_clock import DualWindowsClockMonitor, WindowsClockError, sample_windows_clocks

__all__ = [
    "BundleLedger",
    "CaptureError",
    "DualWindowsClockMonitor",
    "WindowsClockError",
    "WindowsCollector",
    "WindowsHttpsTransport",
    "capture_session",
    "metadata",
    "parse_klines",
    "reference",
    "sample_windows_clocks",
    "strict_json",
    "verify_observation",
    "write_atomic_bytes",
]
