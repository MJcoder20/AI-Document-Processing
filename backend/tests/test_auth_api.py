import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException
from app.core.config import settings
from app.core.dependencies import require_admin
from app.core.security import create_access_token, decode_access_token
from app.models.user import User
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app import models


@pytest.fixture
def auth_client(monkeypatch):
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

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        SecretStr("test-secret-key-for-authentication"),
    )

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_register_user(auth_client):
    response = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "SecurePassword123",
            "role": "admin",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
    assert response.json()["role"] == "user"
    assert "hashed_password" not in response.json()


def test_register_duplicate_email(auth_client):
    payload = {
        "email": "test@example.com",
        "password": "SecurePassword123",
    }

    auth_client.post("/api/v1/auth/register", json=payload)
    response = auth_client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 409


def test_login_and_get_current_user(auth_client):
    auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "SecurePassword123",
        },
    )

    login_response = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "SecurePassword123",
        },
    )

    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    me_response = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "test@example.com"


def test_login_rejects_wrong_password(auth_client):
    auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "SecurePassword123",
        },
    )

    response = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPassword123",
        },
    )

    assert response.status_code == 401


def test_me_rejects_missing_token(auth_client):
    response = auth_client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_rejects_invalid_token(auth_client):
    response = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_me_rejects_expired_token(auth_client):
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "exp": expired_at,
            "iat": expired_at - timedelta(minutes=30),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    response = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_require_admin_rejects_regular_user():
    user = User(
        id=uuid4(),
        email="user@example.com",
        hashed_password="hashed-password",
        role="user",
        is_active=True,
    )

    with pytest.raises(HTTPException) as exc:
        require_admin(current_user=user)

    assert exc.value.status_code == 403


def test_require_admin_accepts_admin():
    admin = User(
        id=uuid4(),
        email="admin@example.com",
        hashed_password="hashed-password",
        role="admin",
        is_active=True,
    )

    assert require_admin(current_user=admin) is admin


def test_access_token_contains_required_claims(auth_client):
    user_id = uuid4()
    token = create_access_token(user_id)

    payload = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        issuer="docuflow-ai",
        audience="docuflow-api",
    )

    assert payload["sub"] == str(user_id)
    assert payload["iss"] == "docuflow-ai"
    assert payload["aud"] == "docuflow-api"
    assert payload["type"] == "access"


def test_decode_rejects_wrong_token_type(auth_client):
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": str(user_id),
            "exp": now + timedelta(minutes=30),
            "iat": now,
            "iss": "docuflow-ai",
            "aud": "docuflow-api",
            "type": "refresh",
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


@pytest.mark.parametrize(
    ("issuer", "audience"),
    [
        ("another-service", "docuflow-api"),
        ("docuflow-ai", "another-api"),
    ],
)
def test_decode_rejects_wrong_issuer_or_audience(
    auth_client,
    issuer,
    audience,
):
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "exp": now + timedelta(minutes=30),
            "iat": now,
            "iss": issuer,
            "aud": audience,
            "type": "access",
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_login_rate_limit_returns_429_and_retry_after(auth_client):
    payload = {
        "email": "ratelimit@example.com",
        "password": "WrongPassword123",
    }

    # The first five failed attempts are rejected normally.
    for _ in range(5):
        response = auth_client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401

    # The next attempt is blocked.
    response = auth_client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


def test_successful_login_resets_rate_limit(auth_client):
    payload = {
        "email": "reset@example.com",
        "password": "SecurePassword123",
    }

    registration = auth_client.post(
        "/api/v1/auth/register",
        json=payload,
    )
    assert registration.status_code == 201

    wrong_payload = {
        "email": payload["email"],
        "password": "WrongPassword123",
    }

    # Four failed attempts must not block the account.
    for _ in range(4):
        response = auth_client.post(
            "/api/v1/auth/login",
            json=wrong_payload,
        )
        assert response.status_code == 401

    # Successful login clears the failed-attempt counter.
    response = auth_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200

    # A new failure starts from one attempt, not five.
    response = auth_client.post(
        "/api/v1/auth/login",
        json=wrong_payload,
    )
    assert response.status_code == 401