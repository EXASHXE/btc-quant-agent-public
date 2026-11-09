"""Dual independent Windows hardware/interrupt elapsed clocks + unqualified wall snapshot."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
from typing import Any, Callable
import uuid


class WindowsClockError(ValueError):
    """Fail-closed clock domain error."""

    def __init__(self, message: str, status: str = "WIN_CLOCK_DEGRADED_BLOCKED"):
        super().__init__(message)
        self.status = status


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


if os.name == "nt":
    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KB = ctypes.WinDLL("kernelbase", use_last_error=True)
    _NTDLL = ctypes.WinDLL("ntdll", use_last_error=True)
    _GTC64 = _K32.GetTickCount64
    _GTC64.restype = ctypes.c_ulonglong
else:  # pragma: no cover - Windows-only module
    _K32 = None
    _KB = None
    _NTDLL = None
    _GTC64 = None


def _windows_boot_identifier(qpc_freq: int) -> str:
    """Return Windows kernel per-boot BootIdentifier GUID via ntdll!NtQuerySystemInformation(90)."""
    if _NTDLL is not None:
        buf = (ctypes.c_ubyte * 32)()
        ret = ctypes.c_ulong()
        status = _NTDLL.NtQuerySystemInformation(90, buf, len(buf), ctypes.byref(ret))
        if status == 0 and ret.value >= 16 and any(buf[:16]):
            # Bind GUID to the kernel's current boot epoch; neither QPC frequency
            # nor a potentially persistent boot-entry GUID alone is sufficient.
            boot = (ctypes.c_ubyte * 48)()
            boot_ret = ctypes.c_ulong()
            boot_status = _NTDLL.NtQuerySystemInformation(3, boot, len(boot), ctypes.byref(boot_ret))
            epoch = int.from_bytes(bytes(boot[:8]), "little", signed=True)
            if boot_status == 0 and boot_ret.value >= 8 and epoch > 0:
                return str(uuid.UUID(bytes_le=bytes(buf[:16]))) + ":" + str(epoch)
            raise WindowsClockError("WIN_KERNEL_BOOT_EPOCH_UNAVAILABLE")
    raise WindowsClockError("WIN_REAL_BOOT_IDENTIFIER_UNAVAILABLE")


def _filetime_to_unix_ns(raw_100ns: int) -> int:
    return (raw_100ns - 116444736000000000) * 100


def query_w32tm_readonly() -> dict[str, Any]:
    """Read-only W32Time provenance snapshot; never mutates service/registry state."""
    if os.name != "nt":
        return {"supported": False, "strict_utc_qualified": False}
    info: dict[str, Any] = {"supported": True, "strict_utc_qualified": False, "query_exit": None}
    try:
        proc = subprocess.run(
            ["w32tm", "/query", "/status"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        info["query_exit"] = proc.returncode
        info["service_stopped_or_unavail"] = proc.returncode != 0
        info["status_text_unqualified"] = proc.stdout
        info["status_error"] = proc.stderr
        info["synchronization_status_interpretation"] = "RAW_STATUS_ONLY_NOT_STRICT_UTC"
    except (OSError, subprocess.TimeoutExpired) as exc:
        info["query_error"] = type(exc).__name__
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\W32Time\Parameters"
        ) as key:
            ntype, _ = winreg.QueryValueEx(key, "Type")
            ntp_srv, _ = winreg.QueryValueEx(key, "NtpServer")
            info["registry_type"] = ntype
            info["registry_ntp_server"] = ntp_srv
    except OSError as exc:
        info["registry_error"] = type(exc).__name__
    return info


def sample_windows_clocks(*, boot_session_id: str | None = None) -> dict[str, Any]:
    """Read bracketed Windows QPC + UnbiasedInterruptTimePrecise + GTC64 + FILETIME."""
    if os.name != "nt" or _K32 is None or _KB is None or _GTC64 is None:
        raise WindowsClockError("WINDOWS_NATIVE_PLATFORM_REQUIRED")

    freq = wt.LARGE_INTEGER()
    if not _K32.QueryPerformanceFrequency(ctypes.byref(freq)) or freq.value <= 0:
        raise WindowsClockError("WIN_QPC_FREQUENCY_UNAVAILABLE")

    qpc0 = wt.LARGE_INTEGER()
    qpc1 = wt.LARGE_INTEGER()
    unb0 = ctypes.c_ulonglong()
    unb1 = ctypes.c_ulonglong()
    ft = _FILETIME()

    if not _K32.QueryPerformanceCounter(ctypes.byref(qpc0)):
        raise WindowsClockError("WIN_QPC_READ_FAILED")
    _KB.QueryUnbiasedInterruptTimePrecise(ctypes.byref(unb0))
    _KB.GetSystemTimePreciseAsFileTime(ctypes.byref(ft))
    tick64_ms = int(_GTC64())
    _KB.QueryUnbiasedInterruptTimePrecise(ctypes.byref(unb1))
    if not _K32.QueryPerformanceCounter(ctypes.byref(qpc1)):
        raise WindowsClockError("WIN_QPC_READ_FAILED")

    qpc_before_ns = (int(qpc0.value) * 1_000_000_000) // int(freq.value)
    qpc_after_ns = (int(qpc1.value) * 1_000_000_000) // int(freq.value)
    unbiased_before_ns = int(unb0.value) * 100
    unbiased_after_ns = int(unb1.value) * 100
    ft_raw = (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)
    win_utc_ns = _filetime_to_unix_ns(ft_raw)

    session_tag = _windows_boot_identifier(int(freq.value))
    if boot_session_id is not None and boot_session_id != session_tag:
        raise WindowsClockError("WIN_CALLER_BOOT_OVERRIDE_FORBIDDEN")

    return {
        "boot_session_id": session_tag,
        "qpc_freq": int(freq.value),
        "qpc_before_ns": qpc_before_ns,
        "qpc_after_ns": qpc_after_ns,
        "qpc_before_ms": qpc_before_ns // 1_000_000,
        "qpc_after_ms": qpc_after_ns // 1_000_000,
        "unbiased_before_ns": unbiased_before_ns,
        "unbiased_after_ns": unbiased_after_ns,
        "unbiased_before_ms": unbiased_before_ns // 1_000_000,
        "unbiased_after_ms": unbiased_after_ns // 1_000_000,
        "tick64_ms": tick64_ms,
        "win_utc_ns": win_utc_ns,
        "win_utc_ms": win_utc_ns // 1_000_000,
        "strict_utc_qualified": False,
    }


def check_windows_pair_coherence(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    max_span_ms: int = 5,
    max_divergence_ms: int = 50,
    max_wall_step_ms: int = 50,
) -> dict[str, Any]:
    """Verify QPC vs UnbiasedInterruptTimePrecise coherence; separately monitor wall jumps."""
    if first["boot_session_id"] != second["boot_session_id"]:
        raise WindowsClockError("WIN_BOOT_SESSION_CHANGED")
    if first["qpc_freq"] != second["qpc_freq"]:
        raise WindowsClockError("WIN_QPC_FREQUENCY_CHANGED")
    span_a_ns = first["qpc_after_ns"] - first["qpc_before_ns"]
    span_b_ns = second["qpc_after_ns"] - second["qpc_before_ns"]
    unb_span_a_ns = first["unbiased_after_ns"] - first["unbiased_before_ns"]
    unb_span_b_ns = second["unbiased_after_ns"] - second["unbiased_before_ns"]
    if not (0 <= span_a_ns <= max_span_ms * 1_000_000 and 0 <= span_b_ns <= max_span_ms * 1_000_000):
        raise WindowsClockError("WIN_QPC_BRACKET_SPAN_UNCERTAIN")
    if not (0 <= unb_span_a_ns <= max_span_ms * 1_000_000 and 0 <= unb_span_b_ns <= max_span_ms * 1_000_000):
        raise WindowsClockError("WIN_UNBIASED_BRACKET_SPAN_UNCERTAIN")
    if (
        second["qpc_before_ns"] < first["qpc_before_ns"]
        or second["unbiased_before_ns"] < first["unbiased_before_ns"]
    ):
        raise WindowsClockError("WIN_ELAPSED_CLOCK_ROLLBACK")
    if second["tick64_ms"] < first["tick64_ms"]:
        raise WindowsClockError("WIN_TICK64_ROLLBACK")

    # Interval uncertainty between QPC midpoint and Unbiased midpoint
    qpc_a = (first["qpc_before_ns"] + first["qpc_after_ns"]) / 2.0
    qpc_b = (second["qpc_before_ns"] + second["qpc_after_ns"]) / 2.0
    unb_a = (first["unbiased_before_ns"] + first["unbiased_after_ns"]) / 2.0
    unb_b = (second["unbiased_before_ns"] + second["unbiased_after_ns"]) / 2.0
    delta_qpc_ms = (qpc_b - qpc_a) / 1_000_000.0
    delta_unb_ms = (unb_b - unb_a) / 1_000_000.0
    qpc_vs_unb_ms = abs(delta_unb_ms - delta_qpc_ms)
    allowed_ms = max_divergence_ms + (span_a_ns + span_b_ns + unb_span_a_ns + unb_span_b_ns) / 2_000_000.0
    if qpc_vs_unb_ms > allowed_ms:
        raise WindowsClockError(f"WIN_QPC_VS_UNBIASED_DIVERGENCE:{qpc_vs_unb_ms:.3f}ms>{allowed_ms:.3f}ms")

    if (
        abs((second["tick64_ms"] - first["tick64_ms"]) - delta_qpc_ms)
        > 50 + 32 + (span_a_ns + span_b_ns) / 2_000_000
    ):
        raise WindowsClockError("WIN_QPC_VS_TICK64_DIVERGENCE")

    # Separately monitor Windows host FILETIME wall jumps relative to QPC
    delta_wall_ms = (second["win_utc_ns"] - first["win_utc_ns"]) / 1_000_000.0
    wall_vs_qpc_ms = abs(delta_wall_ms - delta_qpc_ms)
    wall_jumped = wall_vs_qpc_ms > max_wall_step_ms + (span_a_ns + span_b_ns) / 2_000_000.0
    return {
        "delta_qpc_ms": delta_qpc_ms,
        "delta_unbiased_ms": delta_unb_ms,
        "qpc_vs_unbiased_diff_ms": qpc_vs_unb_ms,
        "wall_vs_qpc_diff_ms": wall_vs_qpc_ms,
        "wall_jumped": wall_jumped,
    }


class DualWindowsClockMonitor:
    """Enforces cumulative + adjacent QPC vs Unbiased coherence across a capture session."""

    def __init__(
        self,
        sampler: Callable[[], dict[str, Any]] | None = None,
        *,
        max_span_ms: int = 5,
        max_divergence_ms: int = 50,
    ):
        self._sampler = sampler or sample_windows_clocks
        self.max_span_ms = max_span_ms
        self.max_divergence_ms = max_divergence_ms
        self.samples: list[dict[str, Any]] = []
        self.wall_jumps_observed: list[dict[str, Any]] = []
        self.w32tm_snapshot = query_w32tm_readonly()
        self.anchor = self.sample()

    def sample(self) -> dict[str, Any]:
        cur = self._sampler()
        if self.samples:
            cum = check_windows_pair_coherence(
                self.samples[0],
                cur,
                max_span_ms=self.max_span_ms,
                max_divergence_ms=self.max_divergence_ms,
            )
            adj = check_windows_pair_coherence(
                self.samples[-1],
                cur,
                max_span_ms=self.max_span_ms,
                max_divergence_ms=self.max_divergence_ms,
            )
            if cum["wall_jumped"] or adj["wall_jumped"]:
                self.wall_jumps_observed.append(
                    {
                        "sample_index": len(self.samples),
                        "adj_wall_vs_qpc_ms": adj["wall_vs_qpc_diff_ms"],
                        "cum_wall_vs_qpc_ms": cum["wall_vs_qpc_diff_ms"],
                    }
                )
        else:
            # Validate initial sample bracket alone
            check_windows_pair_coherence(
                cur, cur, max_span_ms=self.max_span_ms, max_divergence_ms=self.max_divergence_ms
            )
        self.samples.append(cur)
        return cur
