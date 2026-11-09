"""Hash-only N retention guard. Never opens or deletes market payloads."""

from datetime import datetime, timezone
from pathlib import Path

CAPTURE = Path("/tmp/quant-n-public-d4d2b36b0036/work/public")
DEADLINE = datetime(2026, 11, 9, 16, 20, tzinfo=timezone.utc)


def state(now):
    if now.tzinfo is None:
        raise ValueError("UTC_AWARE_AUDIT_TIME_REQUIRED")
    expired = now >= DEADLINE
    return {
        "deadline_UTC": DEADLINE.isoformat(),
        "exact_capture_path": str(CAPTURE),
        "status": "EXPIRED_DO_NOT_USE_OWNER_PURGE_APPROVAL_REQUIRED"
        if expired
        else "RETENTION_WINDOW_OPEN_NO_RAW_USE_BY_O",
        "raw_use_by_O_allowed": False,
        "deletion_performed": False,
        "automatic_job_created": False,
        "path_is_symlink": CAPTURE.is_symlink(),
        "directory_exists": CAPTURE.is_dir(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(state(datetime.now(timezone.utc)), sort_keys=True))
