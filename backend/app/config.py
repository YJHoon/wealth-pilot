from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 데이터베이스
    database_url: str

    # 암호화
    encryption_key: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # NextAuth
    nextauth_secret: str = ""

    # CORS (쉼표 구분 문자열)
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # 텔레그램
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Sentry
    sentry_dsn: str = ""

    # 개발용: 인증 비활성화 (True면 모든 API에서 인증 스킵)
    auth_disabled: bool = False

    # 환경
    env: str = "development"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


settings = Settings()
