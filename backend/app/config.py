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

    # 싱글유저 모드: 허용된 이메일만 로그인 가능 (빈 문자열이면 제한 없음)
    allowed_email: str = ""

    # KIS API — 모의투자
    kis_paper_app_key: str = ""
    kis_paper_app_secret: str = ""
    kis_paper_account_number: str = ""
    kis_paper_account_product_code: str = "01"
    kis_paper_base_url: str = "https://openapivts.koreainvestment.com:29443"

    # KIS API — 실전
    kis_live_app_key: str = ""
    kis_live_app_secret: str = ""
    kis_live_account_number: str = ""
    kis_live_account_product_code: str = "01"
    kis_live_base_url: str = "https://openapi.koreainvestment.com:9443"

    trading_enabled: bool = False  # 자동매매 글로벌 킬 스위치

    def kis_credentials(self, mode: str) -> dict:
        """모드별 KIS 인증정보 반환. 잘못된 모드는 ValueError."""
        if mode == "paper":
            return {
                "app_key": self.kis_paper_app_key,
                "app_secret": self.kis_paper_app_secret,
                "account_number": self.kis_paper_account_number,
                "account_product_code": self.kis_paper_account_product_code,
            }
        if mode == "live":
            return {
                "app_key": self.kis_live_app_key,
                "app_secret": self.kis_live_app_secret,
                "account_number": self.kis_live_account_number,
                "account_product_code": self.kis_live_account_product_code,
            }
        raise ValueError(f"Invalid KIS trading mode: {mode!r}. Expected 'paper' or 'live'.")

    # 환경
    env: str = "development"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


settings = Settings()
