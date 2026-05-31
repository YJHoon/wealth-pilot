from decimal import Decimal

from pydantic import field_validator
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

    # ── Stage 3: LLM 어드바이저 ──
    # 프로바이더 선택: "gemini"(무료 티어 가능) | "anthropic"
    llm_provider: str = "gemini"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    # 모델명은 선택된 프로바이더의 모델명을 그대로 사용한다.
    # gemini: "gemini-2.0-flash"(비-thinking, free tier 한도 ↑) /
    #         "gemini-2.5-flash"(thinking, 한도 ↓) /
    # anthropic: "claude-sonnet-4-5" 등
    llm_advisor_model: str = "gemini-2.0-flash"
    llm_advisor_min_confidence: int = 70  # 이 값 미만이면 발주 차단
    llm_advisor_timeout_seconds: float = 20.0
    llm_advisor_max_tokens: int = 1024
    # advisory 배치 호출(1 run = 1 LLM call) 출력 토큰 한도.
    # 후보 종목당 ~200 토큰 JSON 가정, 20종목까지 안전.
    advisory_batch_max_tokens: int = 4096
    # 배치 호출은 종목 수에 비례해 느릴 수 있어 별도 타임아웃.
    advisory_batch_timeout_seconds: float = 60.0

    # ── Stage 3 Step 6: RAG 유사 케이스 회상 (모듈 D) ──
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    embedding_model_cache_dir: str = ""  # 빈 문자열이면 sentence-transformers 기본 경로
    rag_top_k: int = 5  # 유사 케이스 검색 최대 개수
    rag_min_similarity: float = 0.5  # 최소 코사인 유사도 임계값

    # ── Stage 3 Step 4: 주간 메타 분석 (모듈 C) ──
    # 모델명은 llm_provider 설정에 맞춰야 한다.
    meta_analysis_model: str = "gemini-2.0-flash"
    meta_analysis_max_rules: int = 5  # 한 번에 생성할 최대 규칙 수
    adaptive_rule_ttl_days: int = 14  # 규칙 기본 유효기간 (일)

    # ── 원클릭 분석·매매 (Advisory) 안전 한도 ──
    # 1회 run 당 사용자가 할당할 수 있는 예산의 절대 상한 (사고 반경 제한).
    advisory_max_run_budget_krw: Decimal = Decimal("1000000000")
    # 1회 run 후보 종목 수 상한 (LLM 호출 비용 가드).
    advisory_max_candidates: int = 20
    # 1종목당 평가자산 대비 매수 금액 비중 상한.
    advisory_max_position_pct: Decimal = Decimal("0.20")
    # 결과 TTL (분) — 경과 시 /execute 거절, 재분석 강제.
    advisory_ttl_minutes: int = 5

    @field_validator("llm_provider")
    @classmethod
    def _validate_llm_provider(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in ("anthropic", "gemini"):
            raise ValueError("llm_provider must be 'anthropic' or 'gemini'")
        return normalized

    @field_validator("rag_top_k")
    @classmethod
    def _validate_rag_top_k(cls, v: int) -> int:
        if v < 1:
            raise ValueError("rag_top_k must be >= 1")
        return v

    @field_validator("rag_min_similarity")
    @classmethod
    def _validate_rag_min_similarity(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("rag_min_similarity must be between 0.0 and 1.0")
        return v

    @field_validator("meta_analysis_max_rules")
    @classmethod
    def _validate_max_rules(cls, v: int) -> int:
        if v < 1:
            raise ValueError("meta_analysis_max_rules must be >= 1")
        return v

    @field_validator("adaptive_rule_ttl_days")
    @classmethod
    def _validate_ttl_days(cls, v: int) -> int:
        if v < 1:
            raise ValueError("adaptive_rule_ttl_days must be >= 1")
        return v

    @field_validator("advisory_max_run_budget_krw")
    @classmethod
    def _validate_advisory_budget(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("advisory_max_run_budget_krw must be > 0")
        return v

    @field_validator("advisory_max_candidates")
    @classmethod
    def _validate_advisory_candidates(cls, v: int) -> int:
        if v < 1:
            raise ValueError("advisory_max_candidates must be >= 1")
        return v

    @field_validator("advisory_max_position_pct")
    @classmethod
    def _validate_advisory_position_pct(cls, v: Decimal) -> Decimal:
        if not (Decimal("0") < v <= Decimal("1")):
            raise ValueError("advisory_max_position_pct must be in (0, 1]")
        return v

    @field_validator("advisory_ttl_minutes")
    @classmethod
    def _validate_advisory_ttl(cls, v: int) -> int:
        if v < 1:
            raise ValueError("advisory_ttl_minutes must be >= 1")
        return v

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
