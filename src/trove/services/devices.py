from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.config import Config
from trove.db.models import DeviceToken
from trove.errors import ValidationError
from trove.services.auth import LoginRateLimiter

LAST_USED_THROTTLE_MS = 5 * 60 * 1000


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    device_id: str
    name: str
    created_at: int
    last_used_at: int
    revoked_at: int | None


@dataclass(slots=True)
class IssuedDeviceToken:
    device_id: str
    name: str
    token: str
    created_at: int


class DeviceService:
    def __init__(
        self,
        config: Config,
        sessions: sessionmaker[Session],
        rate_limiter: LoginRateLimiter,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.rate_limiter = rate_limiter

    def issue(self, *, password: str, name: str, client: str) -> IssuedDeviceToken | None:
        name = name.strip()
        if not name:
            raise ValidationError(
                "Device name cannot be empty", details={"code": "device.name_required"}
            )
        self.rate_limiter.check(client)
        if not self.config.password_configured() or not self.config.verify_password(password):
            self.rate_limiter.record_failure(client)
            self.rate_limiter.check(client)
            return None
        self.rate_limiter.reset(client)
        token = secrets.token_urlsafe(32)
        now = utc_ms()
        device_id = str(uuid.uuid4())
        with self.sessions() as session:
            session.add(
                DeviceToken(
                    device_id=device_id,
                    name=name,
                    token_hash=hash_token(token),
                    created_at=now,
                    last_used_at=now,
                    session_epoch=self.config.session_epoch,
                )
            )
            session.commit()
        return IssuedDeviceToken(
            device_id=device_id, name=name, token=token, created_at=now
        )

    def verify(self, token: str) -> tuple[str | None, str | None]:
        """Return (device_id, error_code); error_code is None when valid."""
        with self.sessions() as session:
            row = session.execute(
                select(DeviceToken).where(DeviceToken.token_hash == hash_token(token))
            ).scalars().first()
            if row is None:
                return None, "auth.device_token_invalid"
            if row.revoked_at is not None or row.session_epoch != self.config.session_epoch:
                return row.device_id, "auth.device_revoked"
            now = utc_ms()
            if now - row.last_used_at >= LAST_USED_THROTTLE_MS:
                row.last_used_at = now
                session.commit()
            return row.device_id, None

    def list(self) -> list[DeviceRecord]:
        with self.sessions() as session:
            rows = session.execute(
                select(DeviceToken).order_by(DeviceToken.created_at, DeviceToken.device_id)
            ).scalars()
            return [_record(row) for row in rows]

    def revoke(self, device_id: str) -> DeviceRecord | None:
        with self.sessions() as session:
            row = session.get(DeviceToken, device_id)
            if row is None:
                return None
            if row.revoked_at is None:
                row.revoked_at = utc_ms()
                session.commit()
            return _record(row)


def _record(row: DeviceToken) -> DeviceRecord:
    return DeviceRecord(
        device_id=row.device_id,
        name=row.name,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )
