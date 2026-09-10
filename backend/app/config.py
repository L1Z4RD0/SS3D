from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:5173"
    seed_admin_username: str = "Lizard"
    seed_admin_password: str | None = None
    # False in local dev (http, same-site different port -> SameSite=Lax works fine).
    # Must be True in production whenever the frontend and backend live on different
    # domains (e.g. Vercel + Render): cross-site cookies require SameSite=None, which
    # browsers only honor when Secure is also set.
    cookie_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def refresh_cookie_samesite(self) -> str:
        return "none" if self.cookie_secure else "lax"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
