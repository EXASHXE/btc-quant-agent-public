"""Independent host-clock admission before native I/O; no clock setters or probes."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..native.contract import Strict, require, verify_key


class HostBody(Strict):
    schema_version: Literal["F_HOST_CLOCK_ADMISSION_V1"] = "F_HOST_CLOCK_ADMISSION_V1"
    evidence_class: Literal["GENUINE_NATIVE", "SYNTHETIC_NETWORK_QA"]
    boot_id: str
    valid_start_ms: int
    valid_end_ms: int
    source_sha256: str
    config_sha256: str
    executable_sha256: str
    raw_diagnostics: dict
    native_clock_probes: list[dict]
    independent_reference: str


class HostEnvelope(Strict):
    grant: HostBody
    key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_base64: str


def verify_host(envelope, roots, grant, now_ms, *, qa=False, historical=False):
    verify_key(envelope, roots.get("auditor", {}))
    b = envelope.grant
    require(b.evidence_class == ("SYNTHETIC_NETWORK_QA" if qa else "GENUINE_NATIVE"), "HOST_PROVENANCE_CLASS")
    require(envelope.key_id == grant.auditor_key_id, "HOST_AUDITOR_ID")
    require(
        b.independent_reference
        and b.valid_start_ms <= now_ms < b.valid_end_ms
        and b.valid_end_ms - b.valid_start_ms <= 300000,
        "HOST_ADMISSION_STALE",
    )
    require(
        b.source_sha256 == grant.source_sha256
        and b.executable_sha256 == grant.executable_sha256
        and b.config_sha256 == grant.config_sha256,
        "HOST_BUILD_BINDING",
    )
    if not qa and not historical:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        require(b.boot_id == boot, "HOST_BOOT_EPOCH_CHANGED")
    samples = b.raw_diagnostics.get("samples", [])
    require(len(samples) >= 2, "HOST_DIAGNOSTICS_MISSING")
    anchor = samples[0]
    for s in samples:
        require(0 <= s["mono_after_ns"] - s["mono_before_ns"] <= 5000000, "HOST_SAMPLE_BRACKET_UNCERTAIN")
        lo = (s["wall_ns"] - s["mono_after_ns"]) - (anchor["wall_ns"] - anchor["mono_before_ns"])
        hi = (s["wall_ns"] - s["mono_before_ns"]) - (anchor["wall_ns"] - anchor["mono_after_ns"])
        require(lo >= -50000000 and hi <= 50000000, "HOST_CLOCK_UNQUALIFIED")
    probes = b.native_clock_probes
    require(len(probes) >= 2, "INDEPENDENT_NATIVE_CLOCK_PROBES_MISSING")
    lows = []
    highs = []
    previous = None
    for p in probes:
        require(
            p["source"] == "https://fapi.binance.com/fapi/v1/time"
            and p["original_target_tls_verified"] is True,
            "HOST_NATIVE_PROBE_PROVENANCE",
        )
        require(
            p["request_mono_ms"] <= p["receive_mono_ms"]
            and (
                previous is None
                or p["request_mono_ms"] > previous["receive_mono_ms"]
                and p["server_ms"] > previous["server_ms"]
            ),
            "HOST_NATIVE_PROBE_ORDER",
        )
        lows.append(p["server_ms"] - p["receive_mono_ms"] - 1)
        highs.append(p["server_ms"] - p["request_mono_ms"] + 1)
        require(
            0 <= now_ms - p["receive_wall_ms"] <= 300000
            and abs(p["receive_wall_ms"] - p["server_ms"]) <= 100,
            "HOST_NATIVE_PROBE_FRESHNESS_OR_UTC",
        )
        previous = p
    require((max(highs) - min(lows)) / 2 <= 100, "HOST_NATIVE_UNCERTAINTY")
    return {
        "status": "SYNTHETIC_ONLY" if qa else "INDEPENDENT_CLOCK_ADMISSION_VERIFIED",
        "uncertainty_ms": (max(highs) - min(lows)) / 2,
    }


def verify_review_epoch(envelope, sample, asof_ms):
    """A historical certificate cannot certify a new live decision clock."""
    body = envelope.grant
    require(abs(sample["wall_ms"] - asof_ms) <= 100, "LIVE_REVIEW_TIME_MISMATCH")
    anchor = body.raw_diagnostics["samples"][0]
    lo = (
        sample["wall_ms"] - sample["mono_after_ms"] - (anchor["wall_ns"] - anchor["mono_before_ns"]) / 1000000
    )
    hi = (
        sample["wall_ms"] - sample["mono_before_ms"] - (anchor["wall_ns"] - anchor["mono_after_ns"]) / 1000000
    )
    require(lo >= -50 and hi <= 50, "LIVE_REVIEW_CLOCK_EPOCH_CHANGED")
    require(
        0 <= sample["mono_after_ms"] - body.native_clock_probes[-1]["receive_mono_ms"] <= 300000,
        "LIVE_REVIEW_CLOCK_PROBES_STALE",
    )
