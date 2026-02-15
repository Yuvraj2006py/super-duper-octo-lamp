import base64
import hashlib
import hmac
import time
from typing import Optional

from fastapi import HTTPException, status

from app.core.config import get_settings


def _sign(message: str) -> str:
    settings = get_settings()
    digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def create_session_token(user_id: str) -> str:
    settings = get_settings()
    issued_at = int(time.time())
    expiry = issued_at + settings.token_ttl_seconds
    payload = f"{user_id}:{expiry}"
    signature = _sign(payload)
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode("utf-8")).decode("utf-8")
    return token


def verify_session_token(token: str) -> Optional[str]:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id, expiry_raw, signature = decoded.split(":", 2)
    except Exception:
        return None

    payload = f"{user_id}:{expiry_raw}"
    expected = _sign(payload)
    if not hmac.compare_digest(signature, expected):
        return None

    if int(expiry_raw) < int(time.time()):
        return None

    return user_id


def validate_login_api_key(api_key: str) -> None:
    settings = get_settings()
    if not hmac.compare_digest(api_key, settings.local_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
