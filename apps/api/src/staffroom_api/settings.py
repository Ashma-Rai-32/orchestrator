from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env, so commands work from any directory. Missing in Docker: ignored.
REPO_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    """Read from environment variables (same names as compose and .env)."""

    model_config = SettingsConfigDict(env_file=REPO_ENV_FILE, extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "staffroom"
    # Owner role: runs migrations only.
    postgres_user: str = "staffroom"
    postgres_password: SecretStr = SecretStr("staffroom")
    # App role: what the API connects as. Not the table owner, so RLS applies.
    app_db_user: str = "staffroom_app"
    app_db_password: SecretStr = SecretStr("staffroom_app")

    redis_host: str = "localhost"
    redis_port: int = 6379

    def _pg_url(self, user: str, password: SecretStr) -> str:
        return (
            f"postgresql+asyncpg://{user}:{password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url(self) -> str:
        return self._pg_url(self.app_db_user, self.app_db_password)

    @property
    def migration_database_url(self) -> str:
        return self._pg_url(self.postgres_user, self.postgres_password)

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"
