
import hashlib
import hmac
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.login_attempt import LoginAttempt


MAX_FAILED_ATTEMPTS = 5
WINDOW_MINUTES = 15
BLOCK_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _identifier_hash(email: str, client_ip: str) -> str:
    if settings.jwt_secret_key is None:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")

    secret = settings.jwt_secret_key.get_secret_value().encode("utf-8")

    # Derive a separate key for rate-limit identifiers.
    derived_key = hmac.new(
        secret,
        b"docuflow-login-rate-limit-v1",
        hashlib.sha256,
    ).digest()

    identifier = f"{email.strip().lower()}\0{client_ip}".encode("utf-8")

    return hmac.new(
        derived_key,
        identifier,
        hashlib.sha256,
    ).hexdigest()


def get_blocked_retry_seconds(
    db: Session,
    email: str,
    client_ip: str,
    now: datetime | None = None,
) -> int | None:
    now = now or _now()
    identifier = _identifier_hash(email, client_ip)

    blocked_until = db.scalar(
        select(LoginAttempt.blocked_until).where(
            LoginAttempt.identifier_hash == identifier,
            LoginAttempt.blocked_until > now,
        )
    )

    if blocked_until is None:
        return None

    if blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=timezone.utc)

    return max(1, math.ceil((blocked_until - now).total_seconds()))


def record_failed_login(
    db: Session,
    email: str,
    client_ip: str,
    now: datetime | None = None,
) -> int:
    now = now or _now()
    identifier = _identifier_hash(email, client_ip)

    window_start = now - timedelta(minutes=WINDOW_MINUTES)
    blocked_until = now + timedelta(minutes=BLOCK_MINUTES)

    dialect = db.bind.dialect.name

    if dialect == "postgresql":
        insert_statement = pg_insert(LoginAttempt)
    elif dialect == "sqlite":
        insert_statement = sqlite_insert(LoginAttempt)
    else:
        raise RuntimeError(f"Unsupported database dialect: {dialect}")

    statement = insert_statement.values(
        id=uuid.uuid4(),
        identifier_hash=identifier,
        failed_attempts=1,
        first_attempt_at=now,
        blocked_until=None,
        updated_at=now,
    )

    within_window = LoginAttempt.first_attempt_at > window_start
    next_count = case(
        (within_window, LoginAttempt.failed_attempts + 1),
        else_=1,
    )

    next_blocked_until = case(
        (
            within_window,
            case(
                (
                    LoginAttempt.failed_attempts + 1 >= MAX_FAILED_ATTEMPTS,
                    blocked_until,
                ),
                else_=LoginAttempt.blocked_until,
            ),
        ),
        else_=None,
    )

    statement = statement.on_conflict_do_update(
        index_elements=[LoginAttempt.identifier_hash],
        set_={
            "failed_attempts": next_count,
            "first_attempt_at": case(
                (within_window, LoginAttempt.first_attempt_at),
                else_=now,
            ),
            "blocked_until": next_blocked_until,
            "updated_at": now,
        },
    )

    db.execute(statement)
    db.commit()

    return db.scalar(
        select(LoginAttempt.failed_attempts).where(
            LoginAttempt.identifier_hash == identifier
        )
    )


def clear_login_failures(
    db: Session,
    email: str,
    client_ip: str,
) -> None:
    identifier = _identifier_hash(email, client_ip)

    db.query(LoginAttempt).filter(
        LoginAttempt.identifier_hash == identifier
    ).delete(synchronize_session=False)

    db.commit()


def cleanup_expired_login_attempts(
    db: Session,
    now: datetime | None = None,
) -> int:
    now = now or _now()
    retention_cutoff = now - timedelta(hours=24)

    deleted_count = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.updated_at < retention_cutoff)
        .delete(synchronize_session=False)
    )

    db.commit()
    return deleted_count