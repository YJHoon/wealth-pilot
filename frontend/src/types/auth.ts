import "next-auth";
import "@auth/core/jwt";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    refreshToken?: string;
    totpRequired?: boolean;
    totpSetupRequired?: boolean;
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    totpRequired?: boolean;
    totpSetupRequired?: boolean;
  }
}

// 백엔드 응답 타입
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  totp_required: boolean;
  totp_setup_required: boolean;
  user: BackendUser;
}

export interface BackendUser {
  id: string;
  email: string;
  name: string;
  totp_enabled: boolean;
  onboarding_completed: boolean;
  created_at: string;
}

export interface TotpSetupResponse {
  qr_code_base64: string;
  secret: string;
  otpauth_uri: string;
}

export interface TotpVerifyResponse {
  verified: boolean;
  message: string;
  access_token?: string;   // 성공 시 totp_verified=True 액세스 토큰
  refresh_token?: string;  // 성공 시 totp_verified=True 리프레시 토큰
}

export interface SessionItem {
  id: string;
  device_info: string;
  ip_address: string;
  last_active_at: string;
  created_at: string;
  is_current: boolean;
}
