"""Independent temporary-file attacks and OS-boundary observations of frozen R2.

The implementation is never edited. Native ptrace and a separately delegated
Python OS-boundary observer must agree for open/fstat/pread/close. Faults alter
only synthetic runtime conditions; all owned leaked FDs are audited/closed later.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from native import native_trace

from scripts.strategy_research.p2_s3_footer_reader import constants, reader, types

COMMON = {"open", "fstat", "pread", "close"}
TERMINAL = "S3A_CODEX_INDEPENDENT_AUDIT_FAIL_HARD_SYSCALL_ACCOUNTING_OR_ROOT_ISOLATION"


def guard_literal(path):
    if isinstance(path, (str, bytes, os.PathLike)):
        text = os.fsdecode(path).replace("\\", "/").lower()
        if "quant-agent/data" in text or "quant-agent-sanitized" in text:
            raise RuntimeError("AUDIT_GUARD: real owner literal must never reach an OS function")


class Boundary:
    def __init__(self, fault: str = ""):
        self.saved = {name: getattr(os, name) for name in
                      ("open", "fstat", "pread", "close", "stat", "scandir")}
        self.events = []
        self.active = {}
        self.fault = fault
        self.fault_used = False
        self.support = os.supports_dir_fd

    def __enter__(self):
        for name in self.saved:
            setattr(os, name, self._proxy(name))
        os.supports_dir_fd = set(self.support) | {os.open}
        return self

    def __exit__(self, *unused):
        for name, original in self.saved.items():
            setattr(os, name, original)
        os.supports_dir_fd = self.support

    def _proxy(self, name):
        def traced(*args, **kwargs):
            if name in ("open", "stat", "scandir"):
                guard_literal(args[0])
            caller = sys._getframe(1)
            event = {"index": len(self.events)+1, "api": name,
                     "caller": caller.f_code.co_filename, "line": caller.f_lineno,
                     "function": caller.f_code.co_name, "errno": 0,
                     "delegated_native": True}
            if name == "open":
                event.update(path=os.fsdecode(args[0]), flags=args[1], dir_fd=kwargs.get("dir_fd"))
            elif name in ("fstat", "close", "pread"):
                event["fd"] = args[0]
                event["fd_label"] = self.active.get(args[0], "unknown")
            else:
                event["path"] = os.fsdecode(args[0])
            if name == "pread":
                event.update(requested=args[1], offset=args[2])
            self.events.append(event)
            delegated = args
            # Real failing native syscall, not an exception fabricated before entry.
            if name == "close" and not self.fault_used and (
                (self.fault == "close_root_fault" and caller.f_code.co_name == "open_anchored_root_dir")
                or (self.fault == "close_leaf_fault" and caller.f_code.co_name == "close_fd"
                    and self.active.get(args[0]) == "data.parquet")
            ):
                self.fault_used = True
                delegated = (-1,)
                event["injected_native_argument"] = -1
            try:
                answer = self.saved[name](*delegated, **kwargs)
            except OSError as exc:
                event["errno"] = exc.errno
                raise
            if name == "open":
                event["returned_fd"] = answer
                self.active[answer] = event["path"]
            elif name == "close":
                self.active.pop(args[0], None)
            elif name == "pread":
                event["returned_bytes"] = len(answer)
            return answer
        return traced


def rechecksum(grant, **updates):
    changed = replace(grant, **updates, signature_hex="")
    return replace(changed, signature_hex=changed.compute_expected_checksum())


def prepare_case(spec: dict, fixtures: dict):
    base = Path(tempfile.mkdtemp(prefix="s3a-ind-audit-"))
    mode = spec["mode"]
    root = base / "root"
    if mode == "deep_cap100":
        root = base.joinpath(*(f"d{i:02}" for i in range(fixtures["deep_directory_count"])), "root")
    elif mode in ("missing_ancestor", "ancestor_symlink", "ancestor_nondirectory", "permission_eacces"):
        root = base / "gate" / "root"
    root.mkdir(parents=True)
    leaf = root / constants.S3_SINGLE_PILOT_REL_PATH
    leaf.parent.mkdir(parents=True)
    payload = bytes.fromhex(fixtures["parquet_hex"])
    if mode == "footer_oversize":
        payload = b"PAR1" + b"Q"*65537 + struct.pack("<I", 65537) + b"PAR1"
    elif mode == "footer_corrupt":
        payload = b"PAR1" + b"Q"*1024 + bytes(40) + struct.pack("<I", 40) + b"PAR1"
    leaf.write_bytes(payload)
    types._FORBIDDEN_SURROGATE_TREES.clear()
    types._TRUSTED_CUSTODY_REGISTRY.clear()
    setup = Boundary()
    with setup:
        grant = types.create_valid_synthetic_grant(str(root), max_attempted_fs_calls=spec["cap"])
    root_relative = str(root.relative_to(base))
    changes = []
    kwargs = {}
    if mode == "missing_ancestor":
        (base / "gate").rename(base / "moved_gate")
    elif mode == "ancestor_nondirectory":
        (base / "gate").rename(base / "moved_gate")
        (base / "gate").write_bytes(b"invented_not_directory")
    elif mode in ("ancestor_symlink", "multihop_symlink"):
        if mode == "ancestor_symlink":
            (base / "gate").rename(base / "moved_gate")
            (base / "gate").symlink_to(base / "moved_gate", target_is_directory=True)
        else:
            root.rename(base / "moved_root")
            (base / "hop").symlink_to(base / "moved_root", target_is_directory=True)
            root.symlink_to(base / "hop", target_is_directory=True)
    elif mode == "permission_eacces":
        base.chmod(0o755)
        (base / "gate").chmod(0)
        changes.append(str(base / "gate"))
    elif mode == "root_replaced":
        root.rename(base / "old_root")
        root.mkdir()
    elif mode == "forbidden_surrogate":
        # Same-device fake owner under this fresh base; never the real owner root.
        types.register_forbidden_owner_surrogate_tree(root)
    elif mode == "leaf_hardlink":
        os.link(leaf, base / "invented_hardlink")
    elif mode == "leaf_replaced_after_trailer":
        replacement = base / "replacement.parquet"
        replacement.write_bytes(payload)
        kwargs["post_trailer_pread_hook"] = lambda: os.replace(replacement, leaf)
    elif mode == "self_minted_no_custody":
        grant = rechecksum(grant, trusted_custody_id="not_registered")
    elif mode == "self_minted_factory":
        # Anyone in-process can use this public fixture issuer. It is test-only.
        grant = types.create_valid_synthetic_grant(str(root))
    elif mode == "production_mode":
        kwargs["production_mode"] = True
    elif mode == "simulated_crossdevice":
        kwargs["simulated_dev_overrides"] = {"research": 999999}
    elif mode == "borrowed_custody":
        other = base / "other"
        other.mkdir()
        other_grant = types.create_valid_synthetic_grant(str(other))
        grant = rechecksum(grant, trusted_custody_id=other_grant.trusted_custody_id)
    elif mode == "temp_path_escape":
        requested = str(root / ".." / "root")
        grant = rechecksum(grant, synthetic_fixture_root=requested)
        root = Path(requested)  # literal construction only; target must reject '..'.
    observation = Boundary(mode)
    captured = []
    original_wrapper = reader.MeteredPosixSyscallWrapper

    def capture_wrapper(*args, **kw):
        obj = original_wrapper(*args, **kw)
        captured.append(obj)
        return obj

    def operation():
        if mode == "permission_eacces" and os.geteuid() == 0:
            # Attach the own-child tracer first, then drop child privileges.
            os.setgroups([])
            os.setgid(65534)
            os.setuid(65534)
        if mode == "attestation_only":
            with observation:
                value = types.create_valid_synthetic_grant(str(root))
            answer = {"decision_code": "ATTESTATION_SETUP_ONLY", "custody_created": bool(value.trusted_custody_id)}
            snap = None
        else:
            reader.MeteredPosixSyscallWrapper = capture_wrapper
            try:
                with observation:
                    try:
                        value = reader.SingleFileParquetFooterReader(
                            synthetic_fixture_root=str(root), grant=grant, **kwargs).evaluate_to_receipt()
                        answer = value.to_dict()
                    except (OSError, AssertionError) as exc:
                        answer = {"unstructured_exception": type(exc).__name__, "message": str(exc)}
            finally:
                reader.MeteredPosixSyscallWrapper = original_wrapper
            snap = captured[0].snapshot().to_dict() if captured else None
        return {"target_receipt": answer, "snapshot_after_operation": snap,
                "boundary_events": observation.events, "outstanding_owned_fds": observation.active,
                "grant_setup_boundary_events": setup.events, "setup_native_scope": False,
                "scope": "GRANT_ATTESTATION_SETUP" if mode == "attestation_only" else "READER_OPERATION",
                "base_cleanup_path": str(base), "restore_permissions": changes,
                "fixture_root_relative": root_relative, "effective_uid": os.geteuid(),
                "payload_sha256": hashlib.sha256(payload).hexdigest()}
    return operation


def postprocess(observed):
    held = []
    cleanup = []
    # Outside both target and native trace; touch only this child's recorded opens.
    for fd_string, label in observed["outstanding_owned_fds"].items():
        fd = int(fd_string)
        try:
            os.fstat(fd)
        except OSError as exc:
            cleanup.append({"fd": fd, "verify_errno": exc.errno})
        else:
            held.append({"fd": fd, "label": label, "verified_by_native_fstat": True})
            os.close(fd)
            cleanup.append({"fd": fd, "audit_closed": True})
    observed["actual_held_descriptors_after_target"] = held
    observed["excluded_auditor_cleanup"] = cleanup
    return observed


def run_case(spec: dict, fixtures: dict) -> dict:
    data = native_trace(lambda: prepare_case(spec, fixtures), postprocess)
    obs = data["observation"]
    base = Path(obs["base_cleanup_path"])
    assert str(base).startswith("/tmp/s3a-ind-audit-")
    for path in obs["restore_permissions"]:
        os.chmod(path, 0o755)
    shutil.rmtree(base)
    counts = Counter(e["family"] for e in data["native_events"])
    boundary = Counter(e["api"] for e in obs["boundary_events"])
    # Independent actual kernel entries and delegated Python boundary must agree.
    for family in COMMON:
        assert counts[family] == boundary[family], (spec["id"], family, counts, boundary)
    reported = (obs["snapshot_after_operation"] or {}).get("attempted_fs_calls_total", 0)
    common_native = sum(counts[f] for f in COMMON)
    return {"case": spec, **data, "native_family_counts": dict(counts),
            "boundary_api_counts": dict(boundary), "native_common_attempts": common_native,
            "target_reported_attempts": reported, "native_common_minus_reported": common_native-reported,
            "native_all_recorded_FS_attempts": len(data["native_events"]),
            "actual_common_cap_exceeded": common_native > spec["cap"],
            "assertion": "KERNEL_AND_INDEPENDENT_BOUNDARY_COUNTS_MATCH",
            "count_scope": "Setup/attestation excluded unless case explicitly ATTESTATION_SETUP; attack rename separately labeled syscall"}


def main():
    fixture_path = Path(__file__).with_name("fixtures.json")
    payload = fixture_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    assert digest == fixture_path.with_suffix(".sha256").read_text().strip()
    fixtures = json.loads(payload)
    cases = []
    for spec in fixtures["scenarios"]:
        case = run_case(spec, fixtures)
        cases.append(case)
        print(json.dumps({"case": spec["id"], "kernel": case["native_common_attempts"],
                          "reported": case["target_reported_attempts"],
                          "delta": case["native_common_minus_reported"]}), flush=True)
    normal = next(c for c in cases if c["case"]["id"] == "normal_cap_100")
    deep = next(c for c in cases if c["case"]["id"] == "deep_cap100")
    assert normal["native_common_minus_reported"] > 0
    assert deep["actual_common_cap_exceeded"] and deep["observation"]["target_receipt"]["allowed"]
    result = {"schema": "S3A_CODEX_NATIVE_AUDIT_V1", "frozen_target_sha": fixtures["frozen_target_sha"],
              "input_sha256": digest, "cases": cases, "executed_cases": len(cases),
              "terminal": TERMINAL,
              "trace_method": "Linux ptrace TRACEME + GET_SYSCALL_INFO of newly forked own child; independent Python OS observer corroboration",
              "scope": "Synthetic tmp files only; no owner data probes, fixes or production grant"}
    output = ROOT / "evidence/v0.6/b_line/p2_s3a_codex_independent_audit_r1/S3A_R2_NATIVE_OS_SYSCALL_TRACE_COMPARISON.json"
    output.write_text(json.dumps(result, sort_keys=True, indent=2)+"\n")


if __name__ == "__main__":
    main()
