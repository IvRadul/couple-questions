from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    jwt_secret_key: str = "dev_secret_change_me"
    jwt_algorithm: str = "HS256"
    # Токен фактически бессрочный (365 дней) — логина/пароля нет,
    # поэтому мы не хотим разлогинивать анонимного пользователя.
    jwt_expire_minutes: int = 60 * 24 * 365
    database_url: str = "sqlite:///./couple_questions.db"
    cors_origins: str = "http://localhost:3000"
    # Секретная фраза для получения прав администратора через POST /admin/claim.
    # ОБЯЗАТЕЛЬНО смените в .env перед выкладкой на сервер.
    admin_secret_key: str = "change_me_admin_secret"

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
