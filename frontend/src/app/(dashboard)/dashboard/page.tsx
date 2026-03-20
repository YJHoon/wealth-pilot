"use client";

import { useAppStore } from "@/stores/appStore";
import { TerminalDashboard } from "@/components/dashboard/TerminalDashboard";
import { MinimalDashboard } from "@/components/dashboard/MinimalDashboard";
import { useMediaQuery } from "@/hooks/useMediaQuery";

export default function DashboardPage() {
  const { viewMode } = useAppStore();
  const isMobile = useMediaQuery("(max-width: 1023px)");

  // 저장된 viewMode 선호값은 유지하되, 렌더링에만 모바일 보정 적용
  const effectiveViewMode = isMobile ? "minimal" : viewMode;

  if (effectiveViewMode === "terminal") {
    return <TerminalDashboard />;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">대시보드</h1>
      <MinimalDashboard />
    </div>
  );
}
