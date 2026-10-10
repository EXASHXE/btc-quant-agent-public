"""Linux x86-64 ptrace of this audit's own child, between two SIGSTOP markers.

No process enumeration, /proc reads, external trace tools or real data paths.
The child imports/creates its synthetic fixture before tracing begins. JSON and
auditor leak verification/cleanup run after detachment and are excluded.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import signal
import struct

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.ptrace.restype = ctypes.c_long
SYSCALL_NAMES = {
    0: "read", 2: "open", 3: "close", 5: "fstat", 6: "lstat", 17: "pread64",
    21: "access", 78: "getdents", 82: "rename", 83: "mkdir", 87: "unlink",
    89: "readlink", 217: "getdents64", 257: "openat", 262: "newfstatat",
    263: "unlinkat", 264: "renameat", 267: "readlinkat", 332: "statx",
}


def ptrace(request: int, pid: int, address: int = 0, data: int = 0) -> int:
    ctypes.set_errno(0)
    answer = LIBC.ptrace(ctypes.c_uint(request), ctypes.c_int(pid),
                         ctypes.c_void_p(address), ctypes.c_void_p(data))
    err = ctypes.get_errno()
    if answer == -1 and err:
        raise OSError(err, os.strerror(err))
    return answer


def peek_string(pid: int, pointer: int) -> str | None:
    if not pointer:
        return None
    value = bytearray()
    for offset in range(0, 4096, ctypes.sizeof(ctypes.c_long)):
        try:
            word = ptrace(2, pid, pointer+offset)
        except OSError:
            return "<unreadable-child-path>"
        chunk = (word & ((1 << 64)-1)).to_bytes(8, "little")
        if 0 in chunk:
            value.extend(chunk[:chunk.index(0)])
            return value.decode("utf-8", errors="replace")
        value.extend(chunk)
    return "<path-exceeds4096>"


def native_trace(prepare, postprocess) -> dict:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Native audit requires Linux x86-64; do not fake a kernel trace")
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            operation = prepare()
            ptrace(0, 0)  # TRACEME: this new child only.
            os.kill(os.getpid(), signal.SIGSTOP)
            observed = operation()
            os.kill(os.getpid(), signal.SIGSTOP)  # End reader/attestation native scope.
            payload = {"observation": postprocess(observed)}
        except BaseException as exc:  # noqa: BLE001 -- child IPC reports failure; parent raises it.
            payload = {"child_error": {"type": type(exc).__name__, "message": str(exc)}}
        data = json.dumps(payload, sort_keys=True).encode()
        for offset in range(0, len(data), 4096):
            os.write(write_fd, data[offset:offset+4096])
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    events = []
    steps = 0
    pending = None
    reaped = False
    try:
        _, status = os.waitpid(pid, 0)
        if not os.WIFSTOPPED(status):
            reaped = True
            raise RuntimeError("Child failed before native trace start (ptrace or fixture setup)")
        ptrace(0x4200, pid, 0, 1)  # SETOPTIONS TRACESYSGOOD
        while True:
            ptrace(24, pid)  # SYSCALL
            _, status = os.waitpid(pid, 0)
            steps += 1
            if steps > 20000:
                raise RuntimeError("Bounded native trace step ceiling exceeded")
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                reaped = True
                raise RuntimeError("Child terminated inside reader trace without end marker")
            stop = os.WSTOPSIG(status)
            if stop == signal.SIGSTOP:
                ptrace(17, pid)  # DETACH; excluded postprocessing starts afterwards.
                os.kill(pid, signal.SIGCONT)
                break
            if stop != (signal.SIGTRAP | 0x80):
                raise RuntimeError(f"Unexpected native trace signal {stop}")
            buffer = ctypes.create_string_buffer(128)
            ptrace(0x420E, pid, 128, ctypes.addressof(buffer))  # GET_SYSCALL_INFO
            operation = buffer.raw[0]
            if operation == 1:  # actual kernel entry; no guessed entry/exit toggle.
                nr = struct.unpack_from("<Q", buffer.raw, 24)[0]
                args = struct.unpack_from("<6Q", buffer.raw, 32)
                pending = None
                if nr in SYSCALL_NAMES:
                    path = None
                    if nr in (2, 6, 21, 82, 83, 87, 89):
                        path = peek_string(pid, args[0])
                    elif nr in (257, 262, 263, 264, 267, 332):
                        path = peek_string(pid, args[1])
                    name = SYSCALL_NAMES[nr]
                    family = name
                    if name in ("open", "openat"):
                        family = "open"
                    elif name == "pread64":
                        family = "pread"
                    elif name == "newfstatat":
                        family = "fstat" if path == "" else "stat"
                    pending = {"index": len(events)+1, "nr": nr, "syscall": name,
                               "family": family, "args": list(args), "path": path}
            elif operation == 2 and pending is not None:
                returned = struct.unpack_from("<q", buffer.raw, 24)[0]
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
            if len(data) > 2*1024*1024:
                raise RuntimeError("Bounded child observation ceiling exceeded")
        _, status = os.waitpid(pid, 0)
        reaped = True
        payload = json.loads(data)
        if "child_error" in payload:
            raise RuntimeError(payload["child_error"])
        return {"native_events": events, "native_trace_steps": steps,
                "child_exit": os.waitstatus_to_exitcode(status), **payload}
    finally:
        os.close(read_fd)
        if not reaped:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except ProcessLookupError:
                pass
