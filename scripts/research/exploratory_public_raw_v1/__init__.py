"""Offline, separately admitted public-native exploratory research; no trading interfaces."""


class GateError(ValueError):
    """A machine-readable, fail-closed decision."""


def require(ok, reason):
    if not ok:
        raise GateError(reason)
