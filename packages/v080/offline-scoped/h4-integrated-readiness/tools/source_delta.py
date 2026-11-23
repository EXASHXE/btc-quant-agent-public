"""Emit the B5 post2 to post3 patch and the added H4 installable source."""

import difflib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
original = root.parent / "lt-v080-sol62-a1-b5-local-derivative-offline-01"
for right in sorted(
    [
        root / "b5/pyproject.toml",
        *(root / "b5/src").rglob("*.py"),
        *(root / "b5/src").rglob("*.json"),
    ]
):
    name = right.relative_to(root / "b5").as_posix()
    left = original / name
    print(
        "".join(
            difflib.unified_diff(
                left.read_text().splitlines(keepends=True),
                right.read_text().splitlines(keepends=True),
                f"a/b5/{name}",
                f"b/b5/{name}",
            )
        ),
        end="",
    )
for path in sorted([root / "pyproject.toml", *(root / "src").rglob("*.py")]):
    name = path.relative_to(root).as_posix()
    print(
        "".join(
            difflib.unified_diff(
                [], path.read_text().splitlines(keepends=True), "/dev/null", f"b/{name}"
            )
        ),
        end="",
    )
