"""Keep the QA Python process from falling through to the host Hermes checkout."""

import sys
from pathlib import Path

host = Path("/usr/local/lib/hermes-agent")
finder_module = "__editable___hermes_agent_0_16_0_finder"
sys.meta_path[:] = [
    loader for loader in sys.meta_path if getattr(loader, "__module__", None) != finder_module
]
sys.path_hooks[:] = [
    loader for loader in sys.path_hooks if getattr(loader, "__module__", None) != finder_module
]
sys.path[:] = [
    entry
    for entry in sys.path
    if (
        not entry.startswith("__editable__.hermes_agent-0.16.0")
        and not (Path(entry).is_absolute() and Path(entry).resolve() == host)
    )
]
