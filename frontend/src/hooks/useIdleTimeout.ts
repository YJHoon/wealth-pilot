"use client";

import { useCallback, useEffect, useRef } from "react";
import { signOut } from "next-auth/react";

const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // 30분
const ACTIVITY_EVENTS = ["mousedown", "keydown", "touchstart", "scroll"] as const;

/**
 * 30분 미사용 시 자동 로그아웃
 * - 마우스, 키보드, 터치, 스크롤 이벤트로 활동 감지
 * - 타이머 리셋
 */
export function useIdleTimeout() {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleLogout = useCallback(async () => {
    // 로그아웃 시 서비스 워커 캐시 삭제 (인증된 페이지가 브라우저에 남지 않도록)
    if ("caches" in window) {
      await Promise.allSettled([caches.delete("pages"), caches.delete("start-url")]);
    }
    signOut({ callbackUrl: "/login?error=30분 동안 활동이 없어 자동 로그아웃되었습니다." });
  }, []);

  const resetTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(handleLogout, IDLE_TIMEOUT_MS);
  }, [handleLogout]);

  useEffect(() => {
    // 초기 타이머 설정
    resetTimer();

    // 활동 이벤트 리스너
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, resetTimer, { passive: true });
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, resetTimer);
      }
    };
  }, [resetTimer]);
}
