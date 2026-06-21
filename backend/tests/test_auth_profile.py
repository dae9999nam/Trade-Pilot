from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.api.routes import _revoke_other_sessions
from app.core.auth import _token_hash
from app.core.config import settings
from app.db.base import Base
from app.models import User, UserSession
from app.schemas import UserProfileUpdate


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _request_with_session(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/auth/me",
            "headers": [(b"cookie", f"{settings.session_cookie_name}={token}".encode("ascii"))],
        }
    )


def test_user_profile_update_normalizes_email() -> None:
    payload = UserProfileUpdate(
        current_password="current-password",
        email=" New.User@Example.COM ",
        new_password="long-enough-password",
    )

    assert payload.email == "new.user@example.com"


def test_revoke_other_sessions_keeps_current_session() -> None:
    db = _session()
    now = datetime.now(UTC)
    user = User(email="demo@example.com", password_hash="hash", role="user", is_active=True)
    other_user = User(email="other@example.com", password_hash="hash", role="user", is_active=True)
    db.add_all([user, other_user])
    db.flush()

    current_token = "current-session-token"
    current_session = UserSession(
        user_id=user.id,
        session_token_hash=_token_hash(current_token),
        csrf_token_hash="current-csrf",
        expires_at=now + timedelta(hours=1),
    )
    other_session = UserSession(
        user_id=user.id,
        session_token_hash=_token_hash("other-session-token"),
        csrf_token_hash="other-csrf",
        expires_at=now + timedelta(hours=1),
    )
    unrelated_session = UserSession(
        user_id=other_user.id,
        session_token_hash=_token_hash("unrelated-session-token"),
        csrf_token_hash="unrelated-csrf",
        expires_at=now + timedelta(hours=1),
    )
    db.add_all([current_session, other_session, unrelated_session])
    db.flush()

    _revoke_other_sessions(db, _request_with_session(current_token), user.id)

    assert current_session.revoked_at is None
    assert other_session.revoked_at is not None
    assert unrelated_session.revoked_at is None
