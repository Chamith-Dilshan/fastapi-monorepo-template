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

    TEST_DB: str

    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

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
    # Langfuse doubles as the OTel-native eval harness backend (see
    # PROJECT_BIBLE.md Section 10) — these are consumed once the
    # agents/extraction packages exist, wired through here from day one so
    # every service reads observability config from one place.
    LANGFUSE_HOST: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
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
