"""In-memory mock only. This module has no socket/HTTP client or webhook URL."""

from dataclasses import dataclass
import hmac

from .card import signature


class NotDelivered(Exception):
    """Trusted mock proves no bytes were submitted; a bounded retry is safe."""


class AmbiguousDelivery(Exception):
    """Submission may have happened. Never automatically replay."""


@dataclass(frozen=True)
class Response:
    status: int
    body: object
    proven_not_delivered: bool = False


class MockFeishuTransport:
    """Scripted provider observations. Codes/proofs are synthetic fixtures only."""

    def __init__(self, outcomes=(), expected_secret=None):
        self._outcomes = iter(outcomes)
        self._expected_secret = expected_secret
        self.cards = []

    def __repr__(self):
        return "<MockFeishuTransport offline>"

    def send(self, card):
        self.cards.append(card)
        if self._expected_secret is not None:
            expected = signature(card.get("timestamp", ""), self._expected_secret.read())
            if not hmac.compare_digest(card.get("sign", ""), expected):
                return Response(200, {"code": 19021, "msg": "signature rejected"}, True)
        outcome = next(self._outcomes, Response(200, {"code": 0, "msg": "ok"}))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
