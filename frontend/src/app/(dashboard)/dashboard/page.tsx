"use client";

import { useEffect } from "react";
import { Loader2 } from "lucide-react";
import { useAppStore } from "@/stores/appStore";
import { useDashboardData } from "@/hooks/useDashboardData";
import { TerminalDashboard } from "@/components/dashboard/TerminalDashboard";
import { MinimalDashboard } from "@/components/dashboard/MinimalDashboard";
import { useMediaQuery } from "@/hooks/useMediaQuery";

export default function DashboardPage() {
  const { viewMode, setViewMode } = useAppStore();
  const data = useDashboardData();
  const isMobile = useMediaQuery("(max-width: 1023px)");

  // 모바일에서는 자동으로 미니멀 모드 전환
  useEffect(() => {
    if (isMobile && viewMode === "terminal") {
      setViewMode("minimal");
    }
  }, [isMobile, viewMode, setViewMode]);

  if (data.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (viewMode === "terminal" && !isMobile) {
    return <TerminalDashboard data={data} />;
  }

  return <MinimalDashboard data={data} />;
}
