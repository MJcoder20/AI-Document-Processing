import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_security_headers():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert (
        response.headers["Referrer-Policy"]
        == "strict-origin-when-cross-origin"
    )
    assert (
        response.headers["Permissions-Policy"]
        == "camera=(), microphone=(), geolocation=()"
    )


def test_production_rejects_debug_mode():
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(
            app_env="production",
            debug=True,
            jwt_secret_key=SecretStr("a" * 64),
            cors_origins=["https://app.example.com"],
            allowed_hosts=["api.example.com"],
        )


def test_production_requires_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY is required"):
        Settings(
            app_env="production",
            debug=False,
            jwt_secret_key=None,
            cors_origins=["https://app.example.com"],
            allowed_hosts=["api.example.com"],
        )


def test_production_rejects_localhost_cors():
    with pytest.raises(ValidationError, match="CORS origins cannot contain localhost"):
        Settings(
            app_env="production",
            debug=False,
            jwt_secret_key=SecretStr("a" * 64),
            cors_origins=["http://localhost:5174"],
            allowed_hosts=["api.example.com"],
        )


def test_production_rejects_local_allowed_hosts():
    with pytest.raises(ValidationError, match="ALLOWED_HOSTS cannot contain local"):
        Settings(
            app_env="production",
            debug=False,
            jwt_secret_key=SecretStr("a" * 64),
            cors_origins=["https://app.example.com"],
            allowed_hosts=["localhost"],
        )

def test_health_endpoint_does_not_expose_environment():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert "environment" not in response.json()
    assert "application" not in response.json()

def test_production_rejects_unsupported_jwt_algorithm():
    with pytest.raises(
        ValidationError,
        match="Production JWT_ALGORITHM must be HS256",
    ):
        Settings(
            app_env="production",
            debug=False,
            jwt_secret_key=SecretStr("a" * 64),
            jwt_algorithm="HS512",
            cors_origins=["https://app.example.com"],
            allowed_hosts=["api.example.com"],
        )


def test_production_rejects_http_cors_origin():
    with pytest.raises(
        ValidationError,
        match="Production CORS origins must use HTTPS",
    ):
        Settings(
            app_env="production",
            debug=False,
            jwt_secret_key=SecretStr("a" * 64),
            jwt_algorithm="HS256",
            cors_origins=["http://app.example.com"],
            allowed_hosts=["api.example.com"],
        )