"""Consumer policy: frozen historical audit only. No WSL clock can make it current."""

from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import tempfile
from win_capture.transport import CaptureError


def frozen_copy(source, parent):
    """Read through pinned directory descriptors; never follow a replaced symlink."""
    if os.name != "posix":
        raise CaptureError("WSL_PINNED_DIRECTORY_FD_REQUIRED")
    source = Path(source)
    if ".." in source.parts:
        raise CaptureError("AUDIT_PATH_TRAVERSAL")
    absolute = source.absolute()
    for part in absolute.parts:
        if (
            "holdout" in part.lower()
            or part.startswith("l4-")
            or (part.startswith("lt-program-") and part != "lt-program-s-windows-handoff-hardening-01")
        ):
            raise CaptureError("PROTECTED_ORIGINAL_SOURCE_PATH")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = nxt
    except BaseException:
        os.close(directory)
        raise
    target = Path(tempfile.mkdtemp(prefix="S_frozen_QA_audit_", dir=parent))

    def read(relative):
        parts = relative.split("/")
        if not parts or any(x in ("", "..", ".") for x in parts):
            raise CaptureError("AUDIT_RELATIVE_PATH")
        fd = os.dup(directory)
        try:
            for part in parts[:-1]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            f = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(f, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise CaptureError("AUDIT_REGULAR_FILE_REQUIRED")
                return stream.read(32 * 1024 * 1024 + 1)
        finally:
            os.close(fd)

    try:
        raw = read("bundle_manifest.json")
        m = json.loads(raw)
        if m.get("evidence_class") != "WIN_CAPTURE_LOOPBACK_QA_V1":
            raise CaptureError(
                "SOURCE_BLOCKED_PUBLIC_CACHE_REQUIRES_INDEPENDENT_CURRENT_WINDOWS_RETENTION_ANCHOR"
            )
        files = ["bundle_manifest.json", "ledger.sqlite"] + [r["raw_path"] for r in m["responses"]]
        for name in files:
            b = read(name)
            if len(b) > 32 * 1024 * 1024:
                raise CaptureError("AUDIT_FILE_SIZE")
            p = target / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        if read("bundle_manifest.json") != raw:
            raise CaptureError("BUNDLE_REPLACED_DURING_CHECK")
        return target, m["bundle_sha256"]
    finally:
        os.close(directory)
