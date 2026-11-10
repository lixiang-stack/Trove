from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from trove.config import Config
from trove.errors import RateLimitedError

SESSION_COOKIE = "trove_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 5 * 60
SESSION_SALT = "trove.session"


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_failures: int = MAX_FAILURES,
        window_seconds: int = FAILURE_WINDOW_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client: str) -> None:
        with self._lock:
            failures = self._prune(client)
            if len(failures) >= self.max_failures:
                retry_after = max(1, int(self.window_seconds - (self.clock() - failures[0])))
                raise RateLimitedError(
                    "Too many failed sign-in attempts; try again later", retry_after=retry_after
                )

    def record_failure(self, client: str) -> None:
        with self._lock:
            failures = self._prune(client)
            failures.append(self.clock())

    def reset(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)

    def _prune(self, client: str) -> deque[float]:
        failures = self._failures[client]
        cutoff = self.clock() - self.window_seconds
        while failures and failures[0] < cutoff:
            failures.popleft()
        return failures


class AuthService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.serializer = URLSafeTimedSerializer(config.session_secret, salt=SESSION_SALT)
        self.rate_limiter = LoginRateLimiter()

    def login(self, password: str, client: str) -> str | None:
        self.rate_limiter.check(client)
        if not self.config.password_configured() or not self.config.verify_password(password):
            self.rate_limiter.record_failure(client)
            self.rate_limiter.check(client)
            return None
        self.rate_limiter.reset(client)
        return self.issue_token()

    def issue_token(self) -> str:
        return self.serializer.dumps({"role": "owner", "epoch": self.config.session_epoch})

    def verify_token(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            payload = self.serializer.loads(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        return (
            isinstance(payload, dict)
            and payload.get("role") == "owner"
            and payload.get("epoch") == self.config.session_epoch
        )

    def logout(self) -> None:
        self.config.invalidate_sessions()


def is_secure_request(scheme: str, forwarded_proto: str | None, config: Config) -> bool:
    if config.force_secure_cookies:
        return True
    return scheme == "https" or (forwarded_proto or "").lower() == "https"
