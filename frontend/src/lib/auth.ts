import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import type { Account, User } from "next-auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// NextAuth User에 백엔드 토큰 추가
interface ExtendedUser extends User {
  backendTokens?: {
    accessToken: string;
    refreshToken: string;
    totpRequired: boolean;
    totpSetupRequired: boolean;
    onboardingCompleted: boolean;
  };
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],

  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7일 (Refresh Token과 동일)
  },

  pages: {
    signIn: "/login",
  },

  callbacks: {
    async signIn({ user, account }: { user: User; account: Account | null }) {
      // Google 로그인 성공 시 백엔드에 사용자 등록/조회
      // account.id_token: Google이 발급한 ID Token (백엔드에서 검증)
      if (!account?.id_token) {
        return `/login?error=${encodeURIComponent("Google 인증 토큰을 가져올 수 없습니다.")}`;
      }

      try {
        const res = await fetch(`${API_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: user.email,
            name: user.name,
            google_id_token: account.id_token,  // 백엔드 서버 측 검증용
          }),
        });

        if (!res.ok) {
          const error = await res.json();
          return `/login?error=${encodeURIComponent(error.detail || "로그인에 실패했습니다.")}`;
        }

        const data = await res.json();
        // 백엔드 토큰을 user 객체에 임시 저장 → jwt callback에서 사용
        const extUser = user as ExtendedUser;
        extUser.backendTokens = {
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
          totpRequired: data.totp_required,
          totpSetupRequired: data.totp_setup_required,
          onboardingCompleted: data.user?.onboarding_completed ?? false,
        };

        return true;
      } catch {
        return `/login?error=${encodeURIComponent("서버에 연결할 수 없습니다.")}`;
      }
    },

    async jwt({ token, user, trigger, session }) {
      // 최초 로그인 시 백엔드 토큰 저장
      if (user) {
        const extUser = user as ExtendedUser;
        const backendTokens = extUser.backendTokens;
        if (backendTokens) {
          token.accessToken = backendTokens.accessToken;
          token.refreshToken = backendTokens.refreshToken;
          token.totpRequired = backendTokens.totpRequired;
          token.totpSetupRequired = backendTokens.totpSetupRequired;
          token.onboardingCompleted = backendTokens.onboardingCompleted;
        }
      }

      // 세션 업데이트 (2FA 완료, 온보딩 완료 후 새 토큰 반영)
      if (trigger === "update" && session) {
        if (session.accessToken !== undefined) token.accessToken = session.accessToken;
        if (session.totpRequired !== undefined) token.totpRequired = session.totpRequired;
        if (session.totpSetupRequired !== undefined) token.totpSetupRequired = session.totpSetupRequired;
        if (session.onboardingCompleted !== undefined) token.onboardingCompleted = session.onboardingCompleted;
      }

      return token;
    },

    async session({ session, token }) {
      // 클라이언트에 백엔드 토큰 전달
      session.accessToken = token.accessToken as string | undefined;
      session.refreshToken = token.refreshToken as string | undefined;
      session.totpRequired = token.totpRequired as boolean | undefined;
      session.totpSetupRequired = token.totpSetupRequired as boolean | undefined;
      session.onboardingCompleted = token.onboardingCompleted as boolean | undefined;

      return session;
    },
  },
});
