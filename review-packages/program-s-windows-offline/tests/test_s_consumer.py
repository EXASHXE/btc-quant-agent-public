from tests.test_wsl_handoff_e2e import (
    make_qa_bundle as make_qa_bundle,
    _loopback_only_socket_guard as _loopback_only_socket_guard,
)
import json
import os
import pytest
from wsl_handoff.importer import process_bundle_to_handoff, HandoffError
from wsl_handoff.safe_audit import frozen_copy


def test_stale_or_replayed_bundle_never_current_even_without_WSL_time(tmp_path):
    for _ in range(2):
        with pytest.raises(HandoffError, match="CURRENT_REVIEW_ANCHOR_UNAVAILABLE") as e:
            process_bundle_to_handoff(tmp_path / "not_read", tmp_path / "out", mode="CURRENT_MANUAL_REVIEW")
        assert e.value.status == "SOURCE_BLOCKED"
    assert not (tmp_path / "out").exists()


def test_history_replay_is_non_actionable_and_repeat_same_output_rejected(make_qa_bundle, tmp_path):
    src, m = make_qa_bundle()
    out = tmp_path / "audit_output"
    x = process_bundle_to_handoff(src, out)
    assert x["mode"] == "HISTORY_AUDIT" and x["current_actionability"] == "SOURCE_BLOCKED"
    assert all(d["historical_only"] for d in x["decisions"].values())
    assert (out / "operator.html").exists()
    with pytest.raises(HandoffError, match="REPEATED_IMPORT"):
        process_bundle_to_handoff(src, out)


def test_TOCTOU_raw_symlink_swap_fails_closed(make_qa_bundle, tmp_path, monkeypatch):
    src, m = make_qa_bundle()
    raw = src / m["responses"][0]["raw_path"]
    other = tmp_path / "outside"
    other.write_text("OUTSIDE_QA_SENTINEL")
    old = os.open
    swapped = False

    def opening(path, *a, **kw):
        nonlocal swapped
        if path == raw.name and not swapped:
            swapped = True
            raw.unlink()
            raw.symlink_to(other)
        return old(path, *a, **kw)

    monkeypatch.setattr(os, "open", opening)
    with pytest.raises(OSError):
        frozen_copy(src, tmp_path)
    assert swapped


def test_public_bundle_not_relabelled_or_copied_for_retention(tmp_path):
    src = tmp_path / "public"
    src.mkdir()
    (src / "bundle_manifest.json").write_text(
        json.dumps({"evidence_class": "WIN_CAPTURE_PUBLIC_OPERATIONAL_V1"})
    )
    with pytest.raises(ValueError, match="PUBLIC_CACHE_REQUIRES"):
        frozen_copy(src, tmp_path)
