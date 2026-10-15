import warnings

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "APP_NAME": "t",
    "APP_VERSION": "0",
    "API_V1_PREFIX": "/api/v1",
    "POSTGRES_HOST": "h",
    "POSTGRES_PORT": 5432,
    "POSTGRES_DB": "app",
    "POSTGRES_USER": "u",
    "POSTGRES_PASSWORD": "a-real-password",
    "SECRET_KEY": "a-real-secret-key",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
}


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch):
    """Settings reads the real process environment (CI sets TEST_DB, a dev
    shell may set anything). Every test here states exactly what it needs,
    so nothing from outside may leak in and change the outcome."""
    for field in Settings.model_fields:
        monkeypatch.delenv(field, raising=False)


def make(**overrides) -> Settings:
    # Values come from a loosely-typed dict on purpose (tests pass bad ones);
    # pydantic validates them at runtime, which is what is under test.
    return Settings(_env_file=None, **{**BASE, **overrides})  # pyrefly: ignore


def test_placeholder_secret_only_warns_in_local():
    with pytest.warns(UserWarning, match="SECRET_KEY"):
        make(ENVIRONMENT="local", SECRET_KEY="changethis")


@pytest.mark.parametrize("env", ["test", "staging", "production"])
def test_placeholder_secret_refuses_to_boot_elsewhere(env):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(ENVIRONMENT=env, SECRET_KEY="changethis")


def test_placeholder_database_and_admin_passwords_are_caught_too():
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        make(ENVIRONMENT="production", POSTGRES_PASSWORD="postgres")
    with pytest.raises(ValidationError, match="FIRST_ADMIN_PASSWORD"):
        make(ENVIRONMENT="production", FIRST_ADMIN_PASSWORD="changethis")


def test_resend_provider_requires_a_key():
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        make(EMAIL_PROVIDER="resend")
    assert (
        make(EMAIL_PROVIDER="resend", RESEND_API_KEY="re_x").EMAIL_PROVIDER == "resend"
    )


def test_cors_origins_are_split_and_trimmed():
    s = make(BACKEND_CORS_ORIGINS="https://a.com, https://b.com ,")
    assert s.cors_origins == ["https://a.com", "https://b.com"]


def test_log_json_defaults_by_environment_and_can_be_forced():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert make(ENVIRONMENT="local").log_json is False
    assert make(ENVIRONMENT="staging").log_json is True
    assert make(ENVIRONMENT="staging", LOG_JSON=False).log_json is False
    assert make(ENVIRONMENT="staging", LOG_JSON="").log_json is True  # blank = unset


def test_test_database_url_requires_a_separate_database():
    with pytest.raises(RuntimeError, match="TEST_DB must be set"):
        _ = make().test_database_url
    with pytest.raises(RuntimeError, match="must differ"):
        _ = make(TEST_DB="app").test_database_url
    assert make(TEST_DB="app_test").test_database_url.database == "app_test"


def test_database_urls_use_the_asyncpg_driver():
    assert make().database_url.drivername == "postgresql+asyncpg"


def test_smtp_provider_requires_a_host():
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        make(EMAIL_PROVIDER="smtp")
    assert make(EMAIL_PROVIDER="smtp", SMTP_HOST="mail.example.com").SMTP_PORT == 587


def test_smtp_starttls_and_implicit_tls_are_mutually_exclusive():
    with pytest.raises(ValidationError, match="mutually exclusive"):
        make(EMAIL_PROVIDER="smtp", SMTP_HOST="h", SMTP_TLS=True, SMTP_SSL=True)
    # Either one alone, or neither (Mailpit), is fine.
    make(EMAIL_PROVIDER="smtp", SMTP_HOST="h", SMTP_TLS=False, SMTP_SSL=True)
    make(EMAIL_PROVIDER="smtp", SMTP_HOST="h", SMTP_TLS=False, SMTP_SSL=False)
