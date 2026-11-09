"""Finite local compatibility/durability/clock evidence. No socket or time setter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys

from btc_quant_agent.platform.native.clock import Clock
from btc_quant_agent.platform.native.contract import require, strict, source_hash, Grant
from btc_quant_agent.platform.qualification.admission import HostEnvelope, verify_host, verify_review_epoch
from btc_quant_agent.platform.qualification.clock_diagnostics import run

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((Path(__file__).parent / "platform_contract.json").read_text())


def compatibility(observed=None):
    info = observed or {
        "system": platform.system(),
        "machine": platform.machine(),
        "implementation": platform.python_implementation(),
        "python": platform.python_version(),
        "libc": platform.libc_ver()[0],
        "libc_version": platform.libc_ver()[1],
    }
    require(
        info["system"] == CONTRACT["system"]
        and info["machine"] == CONTRACT["machine"]
        and info["implementation"] == CONTRACT["python_implementation"]
        and info["python"] == CONTRACT["python_version"]
        and info["libc"] == CONTRACT["libc"]
        and tuple(int(x) for x in info["libc_version"].split("."))
        >= tuple(int(x) for x in CONTRACT["minimum_glibc"].split(".")),
        "UNSUPPORTED_HOST_PROFILE",
    )
    return {"status": "COMPATIBLE_NOT_QUALIFIED", **info}


def stability(profile):
    """Replay real retained pairs through the unchanged accepted sticky policy."""

    class RetainedClock(Clock):
        record: dict = {}

        def pair(self):
            return self.record

    clock = RetainedClock()
    for i, sample in enumerate(profile["samples"]):
        # Truncate each ns clock exactly as the accepted Clock.pair does.
        pair = {
            "wall_ms": sample["wall_ns"] // 1000000,
            "mono_before_ms": sample["mono_before_ns"] // 1000000,
            "mono_after_ms": sample["mono_after_ns"] // 1000000,
        }
        clock.record = pair
        try:
            clock.sample()
        except ValueError as exc:
            return {
                "status": "HOST_CLOCK_UNQUALIFIED",
                "first_stop_index": i,
                "reason": str(exc),
                "failure_evidence": clock.failure_evidence,
                "epoch_resets": 0,
            }
    require(
        len(profile["samples"]) >= 2 and profile["elapsed_seconds"] >= CONTRACT["clock_observation_seconds"],
        "BOUNDED_CLOCK_COVERAGE_INCOMPLETE",
    )
    require(profile["cross_process_mono_order_valid"], "CROSS_PROCESS_CLOCK_DOMAIN_UNCERTAIN")
    return {
        "status": "BOUNDED_STABILITY_ONLY",
        "qualified": False,
        "reason": "INDEPENDENT_UTC_REQUIRED",
        "epoch_resets": 0,
    }


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_json(path, value):
    with Path(path).open("xb") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    fsync_dir(Path(path).parent)


def filesystem(directory, fault=lambda phase: None):
    import fcntl

    directory = Path(directory)
    require(
        not any(p.is_symlink() for p in (directory, *directory.absolute().parents)), "UNTRUSTED_HOST_OUTPUT"
    )
    directory.mkdir(exist_ok=False)
    fsync_dir(directory.parent)
    stats = os.statvfs(directory)
    require(
        stats.f_bavail * stats.f_frsize >= CONTRACT["filesystem_free_bytes_minimum"],
        "HOST_STORAGE_ADMISSION_FAILED",
    )
    raw = b"QUANT_G_OFFLINE_DURABILITY_PROBE_V1\n"
    stage = directory / "staged"
    fault("before_write")
    with stage.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        fault("before_fsync")
        os.fsync(stream.fileno())
    fault("before_replace")
    os.replace(stage, directory / "committed")
    fsync_dir(directory)
    require((directory / "committed").read_bytes() == raw, "ATOMIC_FILE_MISMATCH")
    database = directory / "crash.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("CREATE TABLE committed(value INTEGER)")
        db.execute("INSERT INTO committed VALUES(1)")
    script = "import os,sqlite3,sys;d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA synchronous=FULL');d.execute('BEGIN IMMEDIATE');d.execute('INSERT INTO committed VALUES(2)');os._exit(73)"
    child = subprocess.run([sys.executable, "-I", "-c", script, str(database)], timeout=5)
    require(child.returncode == 73, "CRASH_INJECTION_DID_NOT_EXIT")
    with sqlite3.connect(database) as db:
        require(
            db.execute("PRAGMA integrity_check").fetchone() == ("ok",), "SQLITE_RECOVERY_INTEGRITY_FAILED"
        )
        require(
            db.execute("SELECT value FROM committed").fetchall() == [(1,)], "UNCOMMITTED_CRASH_DATA_VISIBLE"
        )
    with (directory / "exclusive.lock").open("xb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        script = "import fcntl,sys;f=open(sys.argv[1],'rb');\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError: sys.exit(0)\nsys.exit(9)"
        child = subprocess.run(
            [sys.executable, "-I", "-c", script, str(directory / "exclusive.lock")], timeout=5
        )
        require(child.returncode == 0, "EXCLUSIVE_LOCK_NOT_ENFORCED")
    fsync_dir(directory)
    return {
        "status": "PASS_LOCAL_FSYNC_CRASH_ROLLBACK_AND_LOCK",
        "free_bytes": stats.f_bavail * stats.f_frsize,
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "power_loss_hardware_qualification": "NOT_ESTABLISHED",
        "crash_child_exit": 73,
    }


def signed_host(envelope, grant, wheel, current):
    # No root injection flag; exactly the authentic installed F trust path.
    from btc_quant_agent.platform import native

    roots = strict((Path(native.__file__).parent / "authority_roots.json").read_bytes())
    require(grant.source_sha256 == source_hash(), "FINAL_SOURCE_BINDING")
    require(
        grant.executable_sha256 == hashlib.sha256(Path(wheel).read_bytes()).hexdigest(), "FINAL_WHEEL_BINDING"
    )
    result = verify_host(envelope, roots, grant, current["wall_ms"])
    verify_review_epoch(envelope, current, current["wall_ms"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-certificate", type=Path)
    parser.add_argument("--grant", type=Path)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args(argv)
    result: dict = {
        "schema": "G_HOST_READINESS_V1",
        "status": "HOST_NOT_YET_QUALIFIED",
        "native_requests": 0,
        "host_changed": False,
        "independent_UTC": "ABSENT",
    }
    try:
        require(
            not any(p.is_symlink() for p in (args.output, *args.output.absolute().parents)),
            "UNTRUSTED_HOST_OUTPUT",
        )
        args.output.mkdir(exist_ok=False)
        result["environment"] = compatibility()
        result["filesystem"] = filesystem(args.output / "filesystem")
        profile = run(CONTRACT["clock_observation_seconds"])
        durable_json(args.output / "clock_raw.json", profile)
        result["clock"] = stability(profile)
        require(result["clock"]["status"] == "BOUNDED_STABILITY_ONLY", "HOST_CLOCK_UNQUALIFIED")
        require(
            args.host_certificate and args.grant and args.wheel, "INDEPENDENT_AUTHENTIC_UTC_EVIDENCE_REQUIRED"
        )
        result["independent_UTC"] = signed_host(
            HostEnvelope.model_validate(strict(args.host_certificate.read_bytes())),
            Grant.model_validate(strict(args.grant.read_bytes())),
            args.wheel,
            Clock().sample(),
        )
        result["status"] = "HOST_CLOCK_QUALIFIED_FOR_SIGNED_CURRENT_EPOCH_ONLY"
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        result["reason"] = str(exc)
    try:
        durable_json(args.output / "result.json", result)
    except (ValueError, OSError) as exc:
        result.update(status="FAILED_DURABLE_HOST_REPORT", report_error=str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"].startswith("HOST_CLOCK_QUALIFIED_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
