"""Copy available Hermes files verified individually against the pinned Git tree."""

import hashlib
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

root = Path("/usr/local/lib/hermes-agent")
destination = Path(sys.argv[1])
commit = "c2fa302e933aafc5f995696709a4179f54206c26"


def git(*args, stderr=None):
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-C", str(root), "-c", "gc.auto=0", *args],
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        stderr=stderr,
    )


@lru_cache(maxsize=None)
def tree(oid):
    rows = {}
    for row in filter(None, git("ls-tree", "-z", oid).split(b"\0")):
        meta, name = row.split(b"\t", 1)
        rows[os.fsdecode(name)] = meta.split()
    return rows


def lookup(parts):
    oid = commit
    for part in parts[:-1]:
        _, type_, oid = tree(oid)[part]
        if type_ != b"tree":
            raise SystemExit(f"UNEXPECTED_HERMES_TREE {part}")
    return tree(oid)[parts[-1]]


runtime_dirs = {
    "agent",
    "cron",
    "gateway",
    "hermes",
    "hermes_cli",
    "providers",
    "plugins",
    "tools",
}
present = recovered = omitted = 0
for row in filter(None, git("ls-files", "-z").split(b"\0")):
    relative = Path(os.fsdecode(row))
    if relative.suffix != ".py" and relative.parts[:3] != ("plugins", "platforms", "feishu"):
        continue
    if not (
        relative.parts[0] in runtime_dirs
        or relative.parts[:3] == ("plugins", "platforms", "feishu")
    ) and not (len(relative.parts) == 1 and relative.suffix == ".py"):
        continue
    path = root / relative
    in_worktree = path.is_file() or path.is_symlink()
    try:
        mode, type_, oid = lookup(relative.parts)
    except subprocess.CalledProcessError:
        if in_worktree:
            raise
        omitted += 1
        continue
    if type_ != b"blob" or mode not in (b"100644", b"100755") or path.is_symlink():
        raise SystemExit(f"UNEXPECTED_HERMES_INPUT {path}")
    try:
        raw = git("cat-file", "blob", oid, stderr=subprocess.DEVNULL)
        recovered += 1
    except subprocess.CalledProcessError:
        if not in_worktree:
            omitted += 1
            continue
        raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode("ascii")
    if hashlib.sha1(header + raw, usedforsecurity=False).hexdigest().encode() != oid:
        raise SystemExit(f"HERMES_SOURCE_HASH_MISMATCH {path}")
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    target.chmod(0o700 if mode == b"100755" else 0o600)
    present += 1
if not (destination / "run_agent.py").is_file():
    raise SystemExit("HERMES_AGENT_SOURCE_UNAVAILABLE")
print(
    f"PASS Hermes Git-verified source commit={commit} copied={present} recovered={recovered} absent={omitted}"
)
