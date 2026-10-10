"""R3 test-only Linux syscall tracer for one freshly forked synthetic child.

The trace interval is delimited by child SIGSTOPs. Fixture creation and the
auditor's post-trace FD inspection are outside it. No process enumeration,
/proc inspection, or market path is involved.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import signal
import struct
from collections.abc import Callable
from typing import Any

_LIBC = ctypes.CDLL(None, use_errno=True)
_LIBC.ptrace.restype = ctypes.c_long
_NAMES = {
    0: "read", 2: "open", 3: "close", 5: "fstat", 6: "lstat",
    17: "pread", 21: "access", 78: "getdents", 82: "rename",
    87: "unlink", 89: "readlink", 217: "getdents64", 257: "open",
    262: "newfstatat", 263: "unlinkat", 264: "renameat",
    267: "readlinkat", 332: "statx",
}
_CORE = frozenset({"open", "fstat", "pread", "close"})


def _ptrace(request: int, pid: int, addr: int = 0, data: int = 0) -> int:
    ctypes.set_errno(0)
    value = _LIBC.ptrace(
        ctypes.c_uint(request), ctypes.c_int(pid),
        ctypes.c_void_p(addr), ctypes.c_void_p(data),
    )
    error = ctypes.get_errno()
    if value == -1 and error:
        raise OSError(error, os.strerror(error))
    return int(value)


def _child_path(pid: int, pointer: int) -> str | None:
    if pointer == 0:
        return None
    raw = bytearray()
    for offset in range(0, 4096, 8):
        try:
            value = _ptrace(2, pid, pointer + offset)
        except OSError:
            return "<unreadable-child-path>"
        chunk = (value & ((1 << 64) - 1)).to_bytes(8, "little")
        if b"\0" in chunk:
            raw.extend(chunk[:chunk.index(0)])
            return raw.decode(errors="replace")
        raw.extend(chunk)
    return "<path-over-4096>"


def trace_own_child(
    operation: Callable[[], Any],
    postprocess: Callable[[Any], dict[str, Any]],
    *,
    prepare: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Trace actual kernel entries while *operation* runs in our own forked child."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("R3 native evidence requires Linux x86_64")
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_fd)
        try:
            if prepare is not None:
                prepare()
            _ptrace(0, 0)  # PTRACE_TRACEME on this new child only.
            os.kill(os.getpid(), signal.SIGSTOP)
            observed = operation()
            os.kill(os.getpid(), signal.SIGSTOP)
            payload = {"observation": postprocess(observed)}
        except BaseException as exc:  # noqa: BLE001 - child error sent to parent.
            payload = {"child_error": f"{type(exc).__name__}: {exc}"}
        data = json.dumps(payload, sort_keys=True).encode()
        if len(data) > 2_000_000:
            data = b'{"child_error":"bounded child payload exceeded"}'
        for offset in range(0, len(data), 4096):
            os.write(write_fd, data[offset:offset + 4096])
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    events: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    steps = 0
    reaped = False
    try:
        _, status = os.waitpid(child, 0)
        if not os.WIFSTOPPED(status):
            reaped = True
            raise RuntimeError("child failed before initial trace marker")
        _ptrace(0x4200, child, 0, 1)  # PTRACE_SETOPTIONS, TRACESYSGOOD.
        while True:
            _ptrace(24, child)  # PTRACE_SYSCALL.
            _, status = os.waitpid(child, 0)
            steps += 1
            if steps > 20_000:
                raise RuntimeError("native trace step ceiling exceeded")
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                reaped = True
                raise RuntimeError("child exited during native trace")
            stop = os.WSTOPSIG(status)
            if stop == signal.SIGSTOP:
                _ptrace(17, child)  # detach before auditor postprocessing.
                os.kill(child, signal.SIGCONT)
                break
            if stop != (signal.SIGTRAP | 0x80):
                raise RuntimeError(f"unexpected trace signal {stop}")
            buf = ctypes.create_string_buffer(128)
            _ptrace(0x420E, child, 128, ctypes.addressof(buf))
            kind = buf.raw[0]
            if kind == 1:
                nr = struct.unpack_from("<Q", buf.raw, 24)[0]
                args = struct.unpack_from("<6Q", buf.raw, 32)
                pending = None
                if nr in _NAMES:
                    path = None
                    if nr in (2, 6, 21, 82, 87, 89):
                        path = _child_path(child, args[0])
                    elif nr in (257, 262, 263, 264, 267, 332):
                        path = _child_path(child, args[1])
                    name = _NAMES[nr]
                    family = name
                    if name == "newfstatat":
                        family = "fstat" if path == "" else "stat"
                    pending = {
                        "nr": nr, "family": family, "path": path,
                        "arg0": args[0], "arg1": args[1], "arg2": args[2],
                        "arg3": args[3],
                    }
            elif kind == 2 and pending is not None:
                returned = struct.unpack_from("<q", buf.raw, 24)[0]
                pending["returned"] = returned
                pending["errno"] = -returned if -4095 <= returned < 0 else 0
                events.append(pending)
                pending = None
        data = bytearray()
        while True:
            chunk = os.read(read_fd, 65536)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 2_000_000:
                raise RuntimeError("child observation exceeded bound")
        _, status = os.waitpid(child, 0)
        reaped = True
        payload = json.loads(data)
        if payload.get("child_error"):
            raise RuntimeError(payload["child_error"])
        core = [event for event in events if event["family"] in _CORE]
        counts = {family: sum(e["family"] == family for e in core)
                  for family in sorted(_CORE)}
        return {
            "observation": payload["observation"],
            "native_core_events": core,
            "native_core_counts": counts,
            "native_core_total": len(core),
            "native_noncore_fs_events": [e for e in events if e["family"] not in _CORE],
            "native_trace_steps": steps,
            "child_exit_code": os.waitstatus_to_exitcode(status),
        }
    finally:
        os.close(read_fd)
        if not reaped:
            try:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
            except ProcessLookupError:
                pass
