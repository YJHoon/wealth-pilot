"use client";

import { useCallback, useEffect, useRef } from "react";
import { signOut } from "next-auth/react";

const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // 30분
const ACTIVITY_EVENTS = ["mousedown", "keydown", "touchstart", "scroll"] as const;
// 탭 간 활동 시각 공유 키 (localStorage)
const LAST_ACTIVITY_KEY = "idle-timeout:last-activity";

/**
 * 30분 미사용 시 자동 로그아웃
 * - 마우스, 키보드, 터치, 스크롤 이벤트로 활동 감지
 * - localStorage로 탭 간 활동 시각 공유 (한 탭 활동 중이면 다른 탭도 유지)
 */
export function useIdleTimeout() {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleLogout = useCallback(async () => {
    // 로그아웃 시 서비스 워커 캐시 삭제 (인증된 페이지가 브라우저에 남지 않도록)
    if ("caches" in window) {
      await Promise.allSettled([caches.delete("pages"), caches.delete("start-url")]);
    }
    // 에러 코드를 사용하여 라우팅 규약과 UI 문구 분리
    signOut({ callbackUrl: "/login?error=idle_timeout" });
  }, []);

  const resetTimer = useCallback(() => {
    // 마지막 활동 시각을 기록하여 다른 탭도 갱신할 수 있게 함
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(handleLogout, IDLE_TIMEOUT_MS);
  }, [handleLogout]);

  useEffect(() => {
    // 다른 탭의 활동을 감지하여 타이머 리셋
    const handleStorage = (event: StorageEvent) => {
      if (event.key === LAST_ACTIVITY_KEY) {
        if (timerRef.current) {
          clearTimeout(timerRef.current);
        }
        timerRef.current = setTimeout(handleLogout, IDLE_TIMEOUT_MS);
      }
    };

    // 초기 타이머 설정
    resetTimer();
    window.addEventListener("storage", handleStorage);

    // 활동 이벤트 리스너
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, resetTimer, { passive: true });
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
      window.removeEventListener("storage", handleStorage);
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, resetTimer);
      }
    };
  }, [resetTimer, handleLogout]);
}
