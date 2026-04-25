"use client";

import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import { TotalAssetCard } from "./TotalAssetCard";
import { AssetDonutChart } from "./AssetDonutChart";
import { AssetTrendChart } from "./AssetTrendChart";
import { DataFreshnessIndicator } from "./DataFreshnessIndicator";
import { DisclaimerFooter } from "./DisclaimerFooter";
import { DashboardSkeleton } from "./DashboardSkeleton";

export function MinimalDashboard() {
  const { summary, loading, error } = useDashboardSummary();

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error || !summary) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-sm">{error ?? "대시보드 데이터를 불러올 수 없습니다."}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 갱신 시각 + 신뢰도 */}
      <DataFreshnessIndicator updatedAt={summary.updatedAt} />

      {/* 총 자산 */}
      <TotalAssetCard summary={summary} />

      {/* 차트 영역 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <AssetDonutChart summary={summary} />
        <AssetTrendChart />
      </div>

      {/* 면책 문구 */}
      <DisclaimerFooter />
    </div>
  );
}
