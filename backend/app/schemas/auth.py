"""인증 관련 Pydantic v2 스키마"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- 토큰 ---

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str  # user_id (UUID 문자열)
    exp: datetime
    type: str  # "access" | "refresh"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# --- Google OAuth 콜백 ---

class GoogleLoginRequest(BaseModel):
    """NextAuth에서 Google 로그인 후 백엔드에 전달하는 정보"""
    email: EmailStr = Field(..., description="Google 이메일")
    name: str = Field(..., description="Google 이름")
    google_id_token: str = Field(..., description="Google ID Token (서버 측 검증용)")
    device_info: str = Field(default="Unknown", description="기기 정보 (User-Agent)")
    # ip_address는 서버 측에서 결정 (클라이언트 스푸핑 방지)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    totp_required: bool = Field(..., description="2FA 검증 필요 여부")
    totp_setup_required: bool = Field(..., description="2FA 초기 설정 필요 여부")
    user: "UserResponse"


# --- 2FA ---

class TotpSetupResponse(BaseModel):
    """2FA 설정 시 QR 코드와 시크릿 반환"""
    qr_code_base64: str = Field(..., description="QR 코드 이미지 (Base64)")
    secret: str = Field(..., description="수동 입력용 TOTP 시크릿")
    otpauth_uri: str = Field(..., description="OTP Auth URI")


class TotpVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="6자리 OTP 코드")


class TotpVerifyResponse(BaseModel):
    verified: bool
    message: str
    access_token: str | None = None   # 성공 시 totp_verified=True 액세스 토큰
    refresh_token: str | None = None  # 성공 시 totp_verified=True 리프레시 토큰 (2FA 우회 방지)


# --- 세션 ---

class SessionResponse(BaseModel):
    id: uuid.UUID
    device_info: str
    ip_address: str
    last_active_at: datetime
    created_at: datetime
    is_current: bool = Field(default=False, description="현재 사용 중인 세션인지")

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int


# --- 사용자 ---

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    totp_enabled: bool
    onboarding_completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}
