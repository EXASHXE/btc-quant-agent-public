"""The future genuine-public composition is pinned dormant in the B1 offline build."""

from typing import NoReturn

from .policy import SourceBlocked


def open_live(*, operating_scope: object, controller_activation: object) -> NoReturn:
    """A later reviewed build must bind trusted Owner scope and Controller activation before any DNS/I/O."""
    # No trusted activation or network peer constructor is shipped for genuine public traffic.
    raise SourceBlocked("LIVE_CAPABILITY_DORMANT")
