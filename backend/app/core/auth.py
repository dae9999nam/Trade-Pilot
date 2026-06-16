import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User, UserSession
from app.schemas import LoginResponse, UserProfile

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
PASSWORD_ALGORITHM = "pbkdf2_sha256"


def normalize_login(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        settings.password_hash_iterations,
    )
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(settings.password_hash_iterations),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", maxsplit=3)
        iterations = int(iterations_raw)
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
    except (ValueError, TypeError):
        return False

    if algorithm != PASSWORD_ALGORITHM:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def authenticate(db: Session, username: str, password: str) -> User:
    login = normalize_login(username)
    user = db.scalar(select(User).where(User.email == login))
    if user is None:
        user = _bootstrap_admin_if_configured(db, login, password)

    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return user


def register_user(db: Session, email: str, password: str, role: str = "user") -> User:
    login = normalize_login(email)
    if db.scalar(select(User.id).where(User.email == login)) is not None:
        raise HTTPException(status_code=409, detail="User already exists.")

    user = User(email=login, password_hash=hash_password(password), role=role, is_active=True)
    db.add(user)
    db.flush()
    return user


def create_authenticated_session(
    db: Session,
    user: User,
    response: Response,
    request: Request,
) -> LoginResponse:
    now = datetime.now(UTC)
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(minutes=settings.session_ttl_minutes)

    db.add(
        UserSession(
            user_id=user.id,
            session_token_hash=_token_hash(session_token),
            csrf_token_hash=_token_hash(csrf_token),
            expires_at=expires_at,
            last_seen_at=now,
        )
    )
    user.last_login_at = now
    db.commit()

    max_age = settings.session_ttl_minutes * 60
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=max_age,
        expires=max_age,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        expires=max_age,
        path="/",
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )
    return LoginResponse(csrf_token=csrf_token, user=_profile(user))


def logout_current_session(
    db: Session,
    request: Request,
    response: Response,
) -> dict[str, bool]:
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        session = db.scalar(
            select(UserSession).where(UserSession.session_token_hash == _token_hash(session_token))
        )
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)
            db.commit()
    clear_auth_cookies(response)
    return {"ok": True}


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def require_auth(
    request: Request,
    db: Session = Depends(get_db),
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> UserProfile:
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise HTTPException(status_code=401, detail="Missing session.")

    now = datetime.now(UTC)
    session = db.scalar(
        select(UserSession)
        .join(User)
        .where(
            UserSession.session_token_hash == _token_hash(session_token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    if request.method.upper() not in SAFE_METHODS:
        _require_csrf(request, session, x_csrf_token)

    session.last_seen_at = now
    db.commit()
    return _profile(session.user)


def require_admin(user: UserProfile = Depends(require_auth)) -> UserProfile:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return user


def _require_csrf(
    request: Request,
    session: UserSession,
    x_csrf_token: str | None,
) -> None:
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    if not csrf_cookie or not x_csrf_token:
        raise HTTPException(status_code=403, detail="Missing CSRF token.")
    if not hmac.compare_digest(csrf_cookie, x_csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")
    if not hmac.compare_digest(session.csrf_token_hash, _token_hash(x_csrf_token)):
        raise HTTPException(status_code=403, detail="Invalid CSRF session.")


def _bootstrap_admin_if_configured(db: Session, login: str, password: str) -> User | None:
    if login != normalize_login(settings.admin_username):
        return None
    if not hmac.compare_digest(password, settings.admin_password):
        return None
    if settings.admin_password == "change-me-now" and settings.app_env == "production":
        raise HTTPException(status_code=500, detail="Default admin password is not allowed.")
    return register_user(db, login, password, role="admin")


def _profile(user: User) -> UserProfile:
    return UserProfile(id=user.id, username=user.email, email=user.email, role=user.role)  # type: ignore[arg-type]


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64decode(payload: str) -> bytes:
    padded = payload + "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))
