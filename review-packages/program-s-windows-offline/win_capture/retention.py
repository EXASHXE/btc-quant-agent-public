"""No daemon/deletion: boot-scoped cache admission and exact-path Owner purge receipt."""

from .access import need, safe
from .win_clock import check_windows_pair_coherence


def cache_status(capture_sample, current_sample):
    check_windows_pair_coherence(capture_sample, current_sample)
    age = current_sample["qpc_after_ms"] - capture_sample["qpc_before_ms"]
    need(0 <= age < 86400000, "CACHE_EXPIRED_OR_UNKNOWN_BOOT")
    return {"status": "WITHIN_MAX_24H", "age_ms": age, "strict_UTC": False, "automatic_deletion": False}


def purge_receipt(path, owner_reference, prior_manifest_sha256):
    p = safe(path)
    need(bool(owner_reference) and len(prior_manifest_sha256) == 64, "PURGE_OWNER_REFERENCE_REQUIRED")
    need(not p.exists(), "PURGE_NOT_COMPLETED")
    return {
        "schema": "S_OWNER_MANUAL_PURGE_RECEIPT_V1",
        "exact_path": str(p),
        "owner_reference": owner_reference,
        "prior_manifest_sha256": prior_manifest_sha256,
        "confirmed_absent": True,
        "worker_performed_deletion": False,
    }
