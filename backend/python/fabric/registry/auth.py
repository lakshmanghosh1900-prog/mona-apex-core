from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

ROLE_LEVELS: dict[str, int] = {"User": 1, "Operator": 2, "Admin": 3, "Owner": 4}
DEFAULT_TTL_SECONDS = 3600


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class AuthContext:
    subject: str
    role: str
    issued_at: int
    expires_at: int

    @property
    def level(self) -> int:
        return ROLE_LEVELS.get(self.role, 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "role": self.role,
            "level": self.level,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


class AuthService:
    """HMAC-SHA256 signed tokens. Stdlib only, no paid auth provider.

    The signing secret comes from AUTH_SECRET; if unset an ephemeral random
    secret is generated (tokens then die on restart — safe dev default).
    """

    def __init__(self, secret: str | None = None, default_ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._secret = (secret if secret is not None else os.getenv("AUTH_SECRET", "")).encode("utf-8") or secrets.token_bytes(32)
        self.default_ttl = default_ttl
        self.ephemeral = not bool(os.getenv("AUTH_SECRET", ""))

    def _sign(self, payload: bytes) -> str:
        return _b64e(hmac.new(self._secret, payload, hashlib.sha256).digest())

    def issue_token(self, subject: str, role: str, ttl_seconds: int | None = None) -> dict[str, Any]:
        if role not in ROLE_LEVELS:
            raise AuthError(f"unknown role: {role}")
        if not subject.strip():
            raise AuthError("subject must be non-empty")
        ttl = self.default_ttl if ttl_seconds is None else int(ttl_seconds)
        if ttl < 1 or ttl > 86400:
            raise AuthError("ttl_seconds must be 1..86400")
        now = int(time.time())
        payload = {"sub": subject, "role": role, "iat": now, "exp": now + ttl, "nonce": secrets.token_hex(8)}
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        token = f"{_b64e(raw)}.{self._sign(raw)}"
        return {
            "token": token,
            "subject": subject,
            "role": role,
            "issued_at": now,
            "expires_at": payload["exp"],
            "ttl_seconds": ttl,
            "token_type": "Bearer",
        }

    def verify_token(self, token: str) -> AuthContext:
        if not token or "." not in token:
            raise AuthError("malformed token")
        try:
            encoded, signature = token.rsplit(".", 1)
            raw = _b64d(encoded)
        except Exception as exc:  # noqa: BLE001
            raise AuthError("malformed token") from exc
        expected = self._sign(raw)
        if not hmac.compare_digest(signature, expected):
            raise AuthError("signature mismatch (tampered or forged token)")
        try:
            payload = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise AuthError("unreadable payload") from exc
        if payload.get("role") not in ROLE_LEVELS:
            raise AuthError("unknown role in token")
        now = int(time.time())
        if now > int(payload.get("exp", 0)):
            raise AuthError("token expired")
        return AuthContext(
            subject=str(payload.get("sub", "")),
            role=str(payload["role"]),
            issued_at=int(payload.get("iat", now)),
            expires_at=int(payload["exp"]),
        )

    @staticmethod
    def parse_bearer(header: str | None) -> str:
        if not header:
            raise AuthError("missing Authorization header")
        parts = header.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthError("expected 'Authorization: Bearer <token>'")
        return parts[1].strip()

    def authenticate(self, authorization_header: str | None) -> AuthContext:
        return self.verify_token(self.parse_bearer(authorization_header))

    @staticmethod
    def can_escalate(requested_role: str, current_role: str) -> bool:
        return ROLE_LEVELS.get(requested_role, 0) <= ROLE_LEVELS.get(current_role, 0)


_auth: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth
    if _auth is None:
        _auth = AuthService()
    return _auth


def reset_auth_service(secret: str | None = None) -> AuthService:
    global _auth
    _auth = AuthService(secret=secret) if secret is not None else AuthService()
    return _auth
