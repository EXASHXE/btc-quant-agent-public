"""Offline distribution's permanent genuine-source admission boundary."""

from typing import NoReturn

DISABLED = "LIVE_CAPABILITY_NOT_ACTIVATED"


class LiveDisabled(ValueError):
    """The installed distribution contains no physical genuine-source binding."""


def open_live(*, operating_scope: object = None, controller_activation: object = None) -> NoReturn:
    raise LiveDisabled(DISABLED)
