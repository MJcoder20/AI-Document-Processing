
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.core.config import settings
from app.db.base import Base
from app.models.login_attempt import LoginAttempt
from app.services.login_rate_limiter import (
    MAX_FAILED_ATTEMPTS,
    clear_login_failures,
    get_blocked_retry_seconds,
    record_failed_login,
    cleanup_expired_login_attempts,
)


@pytest.fixture
def db_session(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        SecretStr("test-secret-key-for-rate-limiter"),
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_failed_attempts_are_counted(db_session):
    now = datetime.now(timezone.utc)

    for expected_count in range(1, MAX_FAILED_ATTEMPTS):
        count = record_failed_login(
            db_session,
            "user@example.com",
            "192.0.2.10",
            now,
        )
        assert count == expected_count

        assert get_blocked_retry_seconds(
            db_session,
            "user@example.com",
            "192.0.2.10",
            now,
        ) is None


def test_fifth_failed_attempt_blocks_login(db_session):
    now = datetime.now(timezone.utc)

    for _ in range(MAX_FAILED_ATTEMPTS):
        record_failed_login(
            db_session,
            "user@example.com",
            "192.0.2.10",
            now,
        )

    retry_seconds = get_blocked_retry_seconds(
        db_session,
        "user@example.com",
        "192.0.2.10",
        now,
    )

    assert retry_seconds is not None
    assert 1 <= retry_seconds <= 15 * 60


def test_block_expires_after_block_period(db_session):
    now = datetime.now(timezone.utc)

    for _ in range(MAX_FAILED_ATTEMPTS):
        record_failed_login(
            db_session,
            "user@example.com",
            "192.0.2.10",
            now,
        )

    later = now + timedelta(minutes=16)

    assert get_blocked_retry_seconds(
        db_session,
        "user@example.com",
        "192.0.2.10",
        later,
    ) is None

    count = record_failed_login(
        db_session,
        "user@example.com",
        "192.0.2.10",
        later,
    )

    assert count == 1


def test_attempts_outside_window_start_new_count(db_session):
    now = datetime.now(timezone.utc)

    for _ in range(4):
        record_failed_login(
            db_session,
            "user@example.com",
            "192.0.2.10",
            now,
        )

    later = now + timedelta(minutes=16)

    count = record_failed_login(
        db_session,
        "user@example.com",
        "192.0.2.10",
        later,
    )

    assert count == 1


def test_successful_login_clears_failures(db_session):
    now = datetime.now(timezone.utc)

    for _ in range(4):
        record_failed_login(
            db_session,
            "user@example.com",
            "192.0.2.10",
            now,
        )

    clear_login_failures(
        db_session,
        "user@example.com",
        "192.0.2.10",
    )

    identifier_count = db_session.scalar(
        select(LoginAttempt).where(
            LoginAttempt.identifier_hash.is_not(None)
        )
    )

    assert identifier_count is None

    count = record_failed_login(
        db_session,
        "user@example.com",
        "192.0.2.10",
        now,
    )

    assert count == 1


def test_different_ips_have_separate_limits(db_session):
    now = datetime.now(timezone.utc)

    for _ in range(MAX_FAILED_ATTEMPTS):
        record_failed_login(
            db_session,
            "user@example.com",
            "192.0.2.10",
            now,
        )

    assert get_blocked_retry_seconds(
        db_session,
        "user@example.com",
        "192.0.2.10",
        now,
    ) is not None

    assert get_blocked_retry_seconds(
        db_session,
        "user@example.com",
        "192.0.2.11",
        now,
    ) is None


def test_different_emails_have_separate_limits(db_session):
    now = datetime.now(timezone.utc)

    for _ in range(MAX_FAILED_ATTEMPTS):
        record_failed_login(
            db_session,
            "first@example.com",
            "192.0.2.10",
            now,
        )

    assert get_blocked_retry_seconds(
        db_session,
        "second@example.com",
        "192.0.2.10",
        now,
    ) is None


def test_cleanup_removes_records_older_than_24_hours(db_session):
    now = datetime.now(timezone.utc)

    record_failed_login(
        db_session,
        "old@example.com",
        "192.0.2.10",
        now - timedelta(hours=25),
    )

    record_failed_login(
        db_session,
        "recent@example.com",
        "192.0.2.11",
        now,
    )

    deleted_count = cleanup_expired_login_attempts(
        db_session,
        now,
    )

    assert deleted_count == 1

    remaining = db_session.query(LoginAttempt).all()
    assert len(remaining) == 1
    assert remaining[0].failed_attempts == 1