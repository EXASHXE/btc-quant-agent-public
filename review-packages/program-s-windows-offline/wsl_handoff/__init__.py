"""Isolated WSL-side read-only verifier and unmodified S1/C handoff consumer for Windows bundles."""

__all__ = [
    "BUNDLE_SCHEMA",
    "HANDOFF_SCHEMA",
    "HandoffError",
    "HandoffLedger",
    "compile_s1_from_verified",
    "evaluate_program_c_boundary",
    "probe_wsl_clock_readonly",
    "process_bundle_to_handoff",
    "verify_and_load_bundle",
]


def __getattr__(name: str):
    if name in __all__:
        from . import importer

        return getattr(importer, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
