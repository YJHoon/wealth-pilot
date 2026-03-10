"use client";

import { useSession } from "next-auth/react";
import { useIdleTimeout } from "@/hooks/useIdleTimeout";

/**
 * 로그인 상태에서만 idle timeout 활성화
 */
export function IdleTimeoutProvider({ children }: { children: React.ReactNode }) {
  const { status } = useSession();

  // 인증된 상태에서만 idle 감지
  if (status === "authenticated") {
    return <IdleTimeoutActive>{children}</IdleTimeoutActive>;
  }

  return <>{children}</>;
}

function IdleTimeoutActive({ children }: { children: React.ReactNode }) {
  useIdleTimeout();
  return <>{children}</>;
}
