import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

// 인증 없이 접근 가능한 경로
const PUBLIC_PATHS = ["/login", "/api/auth"];

// 2FA 관련 경로 (인증 후 접근 허용)
const TWO_FA_PATHS = ["/security/2fa"];

export default auth((req) => {
  const { pathname } = req.nextUrl;

  // 공개 경로는 인증 체크 안 함
  if (PUBLIC_PATHS.some((path) => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  // 정적 파일, _next 등은 스킵
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/manifest") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // 미인증 사용자 → 로그인 페이지
  if (!req.auth) {
    const loginUrl = new URL("/login", req.url);
    // Open Redirect 방지: 동일 도메인 경로만 허용
    if (pathname.startsWith("/") && !pathname.startsWith("//")) {
      loginUrl.searchParams.set("callbackUrl", pathname);
    }
    return NextResponse.redirect(loginUrl);
  }

  const isTwoFaPath = TWO_FA_PATHS.some((p) => pathname.startsWith(p));

  // 2FA 초기 설정 필요 → 설정 페이지로 강제 이동
  if (req.auth?.totpSetupRequired && !isTwoFaPath) {
    return NextResponse.redirect(new URL("/security/2fa/setup", req.url));
  }

  // 2FA 설정은 됐지만 이번 세션에서 OTP 검증 미완료 → 검증 페이지로 강제 이동
  if (req.auth?.totpRequired && !req.auth?.totpSetupRequired && !isTwoFaPath) {
    return NextResponse.redirect(new URL("/security/2fa/verify", req.url));
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|manifest.json|icons/).*)"],
};
