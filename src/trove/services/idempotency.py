"""Request idempotency for creating operations.

Only successful responses are stored. A key that is still being processed is
reported as a conflict instead of running the operation twice. In-progress
keys expire quickly so a crashed request does not block the key for a full day.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.db.models import IdempotencyKey
from trove.errors import (
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
    ValidationError,
)

IN_PROGRESS_TTL_MS = 5 * 60 * 1000
COMPLETED_TTL_MS = 24 * 60 * 60 * 1000
MAX_KEY_LENGTH = 255


class BeginState(StrEnum):
    STARTED = "started"
    REPLAY = "replay"


@dataclass(slots=True)
class BeginResult:
    state: BeginState
    token: int | None = None
    status_code: int | None = None
    payload: dict[str, Any] | None = None


def normalize_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip()
    if not key:
        return None
    if len(key) > MAX_KEY_LENGTH:
        raise ValidationError(
            "Idempotency-Key is too long",
            details={"code": "idempotency.key_invalid"},
        )
    return key


def request_fingerprint(method: str, path: str, payload: Any) -> str:
    canonical = json.dumps(
        {"method": method.upper(), "path": path, "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def begin(
        self,
        key: str,
        *,
        method: str,
        path: str,
        request_hash: str,
    ) -> BeginResult:
        now = utc_ms()
        with self.sessions() as session:
            session.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at <= now))
            row = session.get(IdempotencyKey, key)
            if row is not None:
                return self._existing(row, method, path, request_hash)
            session.add(
                IdempotencyKey(
                    key=key,
                    method=method.upper(),
                    path=path,
                    request_hash=request_hash,
                    state="in_progress",
                    created_at=now,
                    expires_at=now + IN_PROGRESS_TTL_MS,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                row = session.get(IdempotencyKey, key)
                if row is None:
                    raise IdempotencyInProgressError(
                        "A request with this Idempotency-Key is still in progress"
                    ) from None
                return self._existing(row, method, path, request_hash)
        return BeginResult(state=BeginState.STARTED, token=now)

    def complete(
        self,
        key: str,
        *,
        token: int,
        status_code: int,
        payload: dict[str, Any],
    ) -> None:
        now = utc_ms()
        with self.sessions() as session:
            row = session.get(IdempotencyKey, key)
            if row is None or row.state != "in_progress" or row.created_at != token:
                return
            row.state = "completed"
            row.status_code = status_code
            row.response_json = json.dumps(payload, ensure_ascii=False)
            row.expires_at = now + COMPLETED_TTL_MS
            session.commit()

    def abort(self, key: str, *, token: int) -> None:
        with self.sessions() as session:
            row = session.get(IdempotencyKey, key)
            if (
                row is not None
                and row.state == "in_progress"
                and row.created_at == token
            ):
                session.delete(row)
                session.commit()

    @staticmethod
    def _existing(
        row: IdempotencyKey,
        method: str,
        path: str,
        request_hash: str,
    ) -> BeginResult:
        if (
            row.method != method.upper()
            or row.path != path
            or row.request_hash != request_hash
        ):
            raise IdempotencyKeyReusedError(
                "Idempotency-Key was already used for a different request"
            )
        if row.state == "completed":
            return BeginResult(
                state=BeginState.REPLAY,
                status_code=row.status_code or 200,
                payload=json.loads(row.response_json or "{}"),
            )
        raise IdempotencyInProgressError(
            "A request with this Idempotency-Key is still in progress"
        )
