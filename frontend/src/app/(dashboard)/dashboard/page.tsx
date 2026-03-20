"use client";

import { Loader2 } from "lucide-react";
import { useAppStore } from "@/stores/appStore";
import { useDashboardData } from "@/hooks/useDashboardData";
import { TerminalDashboard } from "@/components/dashboard/TerminalDashboard";
import { MinimalDashboard } from "@/components/dashboard/MinimalDashboard";
import { useMediaQuery } from "@/hooks/useMediaQuery";

export default function DashboardPage() {
  const { viewMode } = useAppStore();
  const data = useDashboardData();
  const isMobile = useMediaQuery("(max-width: 1023px)");

  // 저장된 viewMode 선호값은 유지하되, 렌더링에만 모바일 보정 적용
  const effectiveViewMode = isMobile ? "minimal" : viewMode;

  if (data.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (effectiveViewMode === "terminal") {
    return <TerminalDashboard data={data} />;
  }

  return <MinimalDashboard data={data} />;
}
