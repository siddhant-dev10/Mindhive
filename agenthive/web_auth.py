"""Short-lived, signed dashboard sessions with CSRF protection.

The login credential is supplied only to the session endpoint. It is never
stored in browser storage or embedded in static JavaScript. The browser holds
an HttpOnly signed cookie and keeps the matching CSRF nonce in memory.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple


SESSION_TTL_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class DashboardSession:
    subject: str
    expires_at: int
    csrf_token: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signing_key(api_token: str) -> bytes:
    return hashlib.sha256(b"AgentHive dashboard session v1\0" + api_token.encode("utf-8")).digest()


def issue_dashboard_session(
    subject: str,
    api_token: str,
    now: Optional[int] = None,
    ttl: int = SESSION_TTL_SECONDS,
) -> Tuple[DashboardSession, str]:
    if not subject or len(api_token) < 32:
        raise ValueError("A configured owner and a strong dashboard credential are required")
    issued_at = int(time.time() if now is None else now)
    session = DashboardSession(
        subject=subject,
        expires_at=issued_at + ttl,
        csrf_token=secrets.token_urlsafe(32),
    )
    payload = json.dumps(
        {"sub": session.subject, "exp": session.expires_at, "iat": issued_at, "csrf": session.csrf_token},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = _b64encode(payload)
    signature = hmac.new(_signing_key(api_token), encoded.encode("ascii"), hashlib.sha256).digest()
    return session, encoded + "." + _b64encode(signature)


def verify_dashboard_session(cookie: Optional[str], api_token: Optional[str], now: Optional[int] = None) -> Optional[DashboardSession]:
    if not cookie or not api_token or len(api_token) < 32:
        return None
    try:
        encoded, supplied_signature = cookie.split(".", 1)
        expected_signature = _b64encode(
            hmac.new(_signing_key(api_token), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
        current_time = int(time.time() if now is None else now)
        if not isinstance(payload.get("exp"), int) or payload["exp"] <= current_time:
            return None
        if not isinstance(payload.get("iat"), int) or payload["iat"] > current_time + 30:
            return None
        if payload["exp"] - payload["iat"] > SESSION_TTL_SECONDS:
            return None
        if not all(isinstance(payload.get(key), str) and payload[key] for key in ("sub", "csrf")):
            return None
        return DashboardSession(payload["sub"], payload["exp"], payload["csrf"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def verify_csrf(session: Optional[DashboardSession], supplied_token: Optional[str]) -> bool:
    return bool(
        session
        and supplied_token
        and hmac.compare_digest(session.csrf_token, supplied_token)
    )
