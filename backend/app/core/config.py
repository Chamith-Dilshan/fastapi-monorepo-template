import warnings
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BASE_DIR = Path(__file__).resolve().parent.parent.parent

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str
    DEBUG: bool = True

    # "local" enables human-readable console logs, permissive default secret
    # checks, and skips Sentry. Everything else is treated as a real
    # deployment target for logging/exception behavior.
    ENVIRONMENT: Environment = "local"

    API_V1_PREFIX: str

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    # Only needed to run the test suite — deliberately optional so a
    # production deployment doesn't have to invent a database name it never
    # uses. See `test_database_url` for the guard rails.
    TEST_DB: str | None = None

    SECRET_KEY: str
    ALGORITHM: str
    # Short on purpose for refresh tokens — a leaked access
    # token is only useful for this long.
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Optional bootstrap admin, created by `python -m app.initial_data`
    # (run from scripts/prestart.sh). Both must be set for it to do
    # anything; see app/initial_data.py.
    FIRST_ADMIN_EMAIL: str | None = None
    FIRST_ADMIN_PASSWORD: str | None = None

    # Comma-separated list of allowed origins, e.g.
    # "https://app.example.com,https://staging.example.com"
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- Observability -----------------------------------------------------
    SERVICE_NAME: str = "backend"
    LOG_LEVEL: str = "INFO"
    # JSON logs are the default everywhere except local dev, where a
    # human-readable console renderer is easier to read. Force either way
    # by setting this explicitly.
    LOG_JSON: bool | None = None

    SENTRY_DSN: AnyUrl | None = None

    OTEL_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    # --- Frontend / email --------------------------------------------------
    # Used for the Google OAuth redirect destination and (if ever needed)
    # links inside emails. No trailing slash.
    FRONTEND_URL: str = "http://localhost:3000"

    # "console" (default — logs the email, sends nothing), "resend", or
    # "smtp" (any SMTP server: a mail provider's relay, or Mailpit in dev).
    # Kept separate from ENVIRONMENT on purpose: a staging box might still
    # want console-only email, and local dev might occasionally want to
    # test real Resend delivery against a sandbox address.
    EMAIL_PROVIDER: Literal["console", "resend", "smtp"] = "console"
    EMAIL_FROM_ADDRESS: str = "onboarding@resend.dev"
    EMAIL_FROM_NAME: str = "App"
    RESEND_API_KEY: str | None = None

    # Only read when EMAIL_PROVIDER=smtp. SMTP_TLS = upgrade a plain
    # connection with STARTTLS (port 587); SMTP_SSL = TLS from the first byte
    # (port 465). Never both. Mailpit in dev needs neither.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    # --- OTP -----------------------------------------------------------
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    # Asking for another code while a fresh one is still outstanding does
    # nothing. Several endpoints send email to an address the caller only
    # *names* (verify, forgot-password), so without this anyone could use
    # them to flood somebody's inbox.
    OTP_RESEND_COOLDOWN_SECONDS: int = 60

    # --- Housekeeping (python -m app.cleanup) --------------------------------
    # Accounts that registered but never verified their email can't log in,
    # and they squat the address. After this long they're removed.
    UNVERIFIED_USER_TTL_DAYS: int = 7
    # Audit logs are kept forever unless you set this. Deleting audit history
    # is a policy decision (compliance, GDPR), so it is never the default.
    AUDIT_LOG_RETENTION_DAYS: int | None = None

    # --- OAuth: Google -------------------------------------------------
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    # Must exactly match a redirect URI registered in Google Cloud Console.
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Langfuse doubles as the OTel-native eval harness backend (see
    # PROJECT_BIBLE.md Section 10) — these are consumed once the
    # agents/extraction packages exist, wired through here from day one so
    # every service reads observability config from one place.
    LANGFUSE_HOST: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None

    model_config = SettingsConfigDict(
        # One shared `.env` at the repo root (the one docker compose reads),
        # with an optional `backend/.env` layered on top for running the
        # backend alone — later files win.
        env_file=(BASE_DIR.parent / ".env", BASE_DIR / ".env"),
        extra="ignore",
    )

    @field_validator("LOG_JSON", mode="before")
    @classmethod
    def _empty_string_is_unset(cls, value: object) -> object:
        # Lets LOG_JSON= (blank) in an env file mean "use the default",
        # instead of pydantic rejecting it as an invalid bool.
        if value == "":
            return None
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.BACKEND_CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def log_json(self) -> bool:
        if self.LOG_JSON is not None:
            return self.LOG_JSON
        return self.ENVIRONMENT != "local"

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT == "local"

    # --- Fail loudly on placeholder secrets outside local dev --------------
    # Adapted from the official fastapi/full-stack-fastapi-template pattern:
    # a default/placeholder secret is a warning in local dev (so the template
    # runs out of the box) and a hard error everywhere else, so a forgotten
    # `.env` value can't silently ship to staging/production.
    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        placeholders = {"changethis", "yoursecretkey", "postgres", ""}
        if value is not None and value.lower() in placeholders:
            message = (
                f'The value of {var_name} looks like a placeholder ("{value}"). '
                "Change it before deploying outside local development."
            )
            if self.is_local:
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret("FIRST_ADMIN_PASSWORD", self.FIRST_ADMIN_PASSWORD)
        return self

    @model_validator(mode="after")
    def _require_credentials_for_the_selected_email_provider(self) -> Self:
        # Catches "EMAIL_PROVIDER=resend but forgot RESEND_API_KEY" (or the
        # SMTP equivalent) at startup, not at the first password-reset
        # request in production.
        if self.EMAIL_PROVIDER == "resend" and not self.RESEND_API_KEY:
            raise ValueError("EMAIL_PROVIDER=resend requires RESEND_API_KEY to be set.")
        if self.EMAIL_PROVIDER == "smtp":
            if not self.SMTP_HOST:
                raise ValueError("EMAIL_PROVIDER=smtp requires SMTP_HOST to be set.")
            if self.SMTP_TLS and self.SMTP_SSL:
                raise ValueError(
                    "SMTP_TLS (STARTTLS) and SMTP_SSL (implicit TLS) are mutually exclusive."
                )
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,  # raw password
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @property
    def test_database_url(self) -> URL:
        # The test suite drops and recreates every table in this database
        # on each run (tests/conftest.py). Pointing it at the real
        # database by accident would wipe it, so refuse loudly instead.
        if not self.TEST_DB:
            raise RuntimeError("TEST_DB must be set to run the test suite.")
        if self.TEST_DB == self.POSTGRES_DB:
            raise RuntimeError(
                "TEST_DB must differ from POSTGRES_DB — tests drop all tables."
            )
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,  # raw password
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.TEST_DB,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
