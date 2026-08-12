from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable

SESSION_COOKIE_NAME = "quantlab_session"
SESSION_HEADER_NAME = "X-QuantLab-Session"


class LANPairingSession:
    """In-memory LAN authorization; every token dies with the backend process."""

    def __init__(
        self,
        *,
        code_factory: Callable[[], str] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._code = (code_factory or self._generate_code)()
        if len(self._code) != 6 or not self._code.isdigit():
            raise ValueError("pairing code must contain exactly six digits")
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._tokens: set[str] = set()

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @property
    def pairing_code(self) -> str:
        return self._code

    def pair(self, code: str) -> str | None:
        if not hmac.compare_digest(str(code), self._code):
            return None
        token = self._token_factory()
        self._tokens.add(token)
        return token

    def accepts(self, token: str | None) -> bool:
        if not token:
            return False
        return any(hmac.compare_digest(token, candidate) for candidate in self._tokens)


def is_loopback_client(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}
