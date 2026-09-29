"""Small, dependency-free security primitives for the HTTP API.

The module intentionally keeps authentication state server-side.  Browser
cookies contain only an opaque, high-entropy identifier; passwords and roles
are never encoded in client controlled tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class SecretProvider:
    """Read application secrets from an injected mapping or the environment."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment if environment is not None else os.environ

    def get(self, name: str, default: str | None = None) -> str | None:
        value = self._environment.get(name, default)
        return value if value not in (None, "") else default

    def require(self, name: str) -> str:
        value = self.get(name)
        if value is None:
            raise RuntimeError(f"Required secret {name!r} is not configured")
        return value


_SENSITIVE_NAME = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|authorization|cookie|webhook)", re.I)
_SENSITIVE_VALUE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie|webhook)\s*[:=]\s*[^\s,;]+")


def redact_secrets(value: Any) -> Any:
    """Return a logging-safe copy with values of sensitive fields removed."""
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub(r"\1=[REDACTED]", value)
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_NAME.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value


class SQLExecutionPolicy:
    """Conservative read-only SQL policy; reject uncertainty rather than write."""

    _forbidden = re.compile(
        r"\b(?:insert|update|delete|merge|alter|drop|create|truncate|grant|revoke|"
        r"commit|rollback|call|execute|exec|begin|declare|replace|vacuum|attach|detach|"
        r"pragma|copy|load|unload)\b",
        re.I,
    )

    @classmethod
    def validate_read_only(cls, sql: str) -> str:
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("SQL must be a non-empty string")
        statement = sql.strip()
        if "--" in statement or "/*" in statement or ";" in statement.rstrip(";"):
            raise ValueError("SQL comments and multiple statements are not permitted")
        statement = statement.rstrip(";").strip()
        if not re.match(r"^(?:select|with)\b", statement, re.I):
            raise ValueError("Only SELECT statements are permitted")
        if cls._forbidden.search(statement):
            raise ValueError("Statement contains a non-read-only operation")
        return statement

    @classmethod
    def is_read_only(cls, sql: str) -> bool:
        try:
            cls.validate_read_only(sql)
            return True
        except ValueError:
            return False


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    session_id: str | None = None


@dataclass
class SessionRecord:
    subject: str
    role: str
    expires_at: float
    csrf_token: str


class SessionStore:
    """Thread-safe opaque sessions with expiry, rotation and revocation."""

    def __init__(self, ttl_seconds: int = 3600, clock: Callable[[], float] = time.time) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    def create(self, subject: str, role: str = "USER", ttl_seconds: int | None = None) -> str:
        if not subject:
            raise ValueError("subject is required")
        lifetime = self._ttl if ttl_seconds is None else ttl_seconds
        if lifetime <= 0:
            raise ValueError("ttl_seconds must be positive")
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = SessionRecord(subject, role.upper(), self._clock() + lifetime, secrets.token_urlsafe(32))
        return token

    def get(self, token: str | None) -> SessionRecord | None:
        if not token:
            return None
        with self._lock:
            record = self._sessions.get(token)
            if record is not None and record.expires_at <= self._clock():
                self._sessions.pop(token, None)
                record = None
            return record

    def principal(self, token: str | None) -> Principal | None:
        record = self.get(token)
        return None if record is None else Principal(record.subject, record.role, token)

    def csrf_token(self, token: str) -> str | None:
        record = self.get(token)
        return None if record is None else record.csrf_token

    def validate_csrf(self, token: str | None, supplied: str | None) -> bool:
        expected = self.csrf_token(token) if token else None
        return bool(expected and supplied and hmac.compare_digest(expected, supplied))

    def rotate(self, token: str) -> str | None:
        """Replace a session id after login/privilege changes (fixation defence)."""
        with self._lock:
            record = self.get(token)
            if record is None:
                return None
            self._sessions.pop(token, None)
            replacement = secrets.token_urlsafe(32)
            self._sessions[replacement] = SessionRecord(
                record.subject, record.role, record.expires_at, secrets.token_urlsafe(32)
            )
            return replacement

    def revoke(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sessions.pop(token, None)


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def require_user(store: SessionStore, cookie_name: str = "session"):
    """FastAPI dependency accepting only a valid server-side USER session."""
    async def dependency(request: Request) -> Principal:
        principal = store.principal(request.cookies.get(cookie_name))
        if principal is None or principal.role != "USER":
            raise _unauthorized()
        return principal
    return dependency


def require_service(service_secret: str):
    """FastAPI dependency for machine-only endpoints using a configured secret."""
    bearer = HTTPBearer(auto_error=False)
    async def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
        if credentials is None or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(credentials.credentials, service_secret):
            raise _unauthorized("Service authentication required")
        return Principal("service", "SERVICE")
    return dependency


def require_csrf(store: SessionStore, cookie_name: str = "session", header_name: str = "x-csrf-token"):
    """FastAPI dependency for unsafe cookie-authenticated browser requests."""
    async def dependency(request: Request) -> None:
        token = request.cookies.get(cookie_name)
        if store.principal(token) is None:
            raise _unauthorized()
        if not store.validate_csrf(token, request.headers.get(header_name)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return dependency
