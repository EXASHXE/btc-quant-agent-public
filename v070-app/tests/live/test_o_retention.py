from datetime import timedelta
import pytest
from o_retention import DEADLINE, state


def test_before_deadline_no_payload_use_no_deletion():
    s = state(DEADLINE - timedelta(seconds=1))
    assert s["status"] == "RETENTION_WINDOW_OPEN_NO_RAW_USE_BY_O" and not s["raw_use_by_O_allowed"]
    assert not s["deletion_performed"] and not s["automatic_job_created"]


def test_at_and_after_deadline_fail_closed_without_deletion():
    for now in [DEADLINE, DEADLINE + timedelta(seconds=1)]:
        s = state(now)
        assert s["status"].startswith("EXPIRED") and not s["raw_use_by_O_allowed"]
        assert s["exact_capture_path"] == "/tmp/quant-n-public-d4d2b36b0036/work/public"
        assert not s["deletion_performed"]
    with pytest.raises(ValueError):
        state(DEADLINE.replace(tzinfo=None))
