import base64
import hashlib
import hmac
import json
import time
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.schemas import UserProfile

bearer = HTTPBearer(auto_error=False)


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64decode(payload: str) -> bytes:
    padded = payload + "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def create_access_token(username: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + settings.access_token_ttl_minutes * 60,
    }
    payload_segment = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.admin_token_secret.encode("utf-8"),
        payload_segment.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_segment}.{_b64encode(signature)}"


def verify_access_token(token: str) -> UserProfile:
    try:
        payload_segment, signature_segment = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token.") from exc

    expected_signature = hmac.new(
        settings.admin_token_secret.encode("utf-8"),
        payload_segment.encode("ascii"),
        hashlib.sha256,
    ).digest()
    actual_signature = _b64decode(signature_segment)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise HTTPException(status_code=401, detail="Invalid token.")

    payload = json.loads(_b64decode(payload_segment))
    if int(payload["exp"]) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired.")
    if payload["sub"] != settings.admin_username:
        raise HTTPException(status_code=401, detail="Unknown user.")

    return UserProfile(username=payload["sub"], role="admin")


def authenticate(username: str, password: str) -> UserProfile:
    username_ok = hmac.compare_digest(username, settings.admin_username)
    password_ok = hmac.compare_digest(password, settings.admin_password)
    if not username_ok or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return UserProfile(username=username, role="admin")


def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UserProfile:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return verify_access_token(credentials.credentials)
