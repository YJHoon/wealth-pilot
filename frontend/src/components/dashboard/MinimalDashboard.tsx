"use client";

import { RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw, formatChangeKrw, formatPercent, pnlColorClass, assetTypeLabels } from "@/lib/format";
import type { DashboardData } from "@/hooks/useDashboardData";
import type { AssetType } from "@/types";

const FRESHNESS_BADGE: Record<string, { label: string; dot: string }> = {
  realtime: { label: "실시간", dot: "bg-emerald-400" },
  delayed: { label: "15분 지연", dot: "bg-yellow-400" },
  batch: { label: "1일 배치", dot: "bg-orange-400" },
  estimated: { label: "추정치", dot: "bg-red-400" },
};

interface Props {
  data: DashboardData;
}

export function MinimalDashboard({ data }: Props) {
  const { isMasked } = useAppStore();
  const { summary } = data;
  const badge = FRESHNESS_BADGE[data.freshness];
  const lastUpdated = new Date(summary.updatedAt).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="space-y-4">
      {/* 상단 바 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <div className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
            <span>{badge.label}</span>
          </div>
          <span>·</span>
          <span>마지막 갱신: {lastUpdated}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          onClick={data.refresh}
          disabled={data.isRefreshing}
        >
          {data.isRefreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          시세 갱신
        </Button>
      </div>

      {/* 총 자산 카드 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-muted-foreground font-normal">총 자산</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold font-[family-name:var(--font-geist-mono)]">
            {formatMaskedKrw(summary.totalValueKrw, isMasked)}
          </div>
          <div className={`text-sm mt-1 ${pnlColorClass(summary.previousDayChange.amount)}`}>
            전일 대비 {formatChangeKrw(summary.previousDayChange.amount, isMasked)}{" "}
            ({formatPercent(summary.previousDayChange.ratio)})
          </div>
        </CardContent>
      </Card>

      {/* 수익률 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label: "합산 손익", value: summary.pnl.total },
          { label: "실현 손익", value: summary.pnl.realized },
          { label: "미실현 손익", value: summary.pnl.unrealized },
        ].map((item) => (
          <Card key={item.label} size="sm">
            <CardHeader>
              <CardTitle className="text-xs text-muted-foreground font-normal">
                {item.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className={`text-lg font-bold font-[family-name:var(--font-geist-mono)] ${pnlColorClass(item.value)}`}>
                {formatChangeKrw(item.value, isMasked)}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 유형별 비중 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">자산 유형별 비중</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {(Object.entries(summary.byType) as [AssetType, { valueKrw: number; ratio: number }][]).map(
              ([type, v]) => (
                <div key={type} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{assetTypeLabels[type]}</span>
                  <div className="flex items-center gap-3">
                    <span className="font-[family-name:var(--font-geist-mono)]">
                      {formatMaskedKrw(v.valueKrw, isMasked)}
                    </span>
                    <span className="text-xs text-muted-foreground w-12 text-right">
                      {v.ratio.toFixed(1)}%
                    </span>
                  </div>
                </div>
              ),
            )}
          </div>
        </CardContent>
      </Card>

      {/* 그룹별 요약 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {Object.values(summary.byGroup).map((group) => (
          <Card key={group.name} size="sm">
            <CardHeader>
              <CardTitle className="text-sm">{group.name}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-lg font-bold font-[family-name:var(--font-geist-mono)]">
                {formatMaskedKrw(group.valueKrw, isMasked)}
              </div>
              <div className="text-xs text-muted-foreground">{group.ratio.toFixed(1)}%</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 면책 문구 */}
      <p className="text-[10px] text-muted-foreground text-center">
        본 서비스는 투자 조언을 제공하지 않습니다. 표시된 시세는 지연될 수 있으며, 투자 판단의 책임은 사용자에게 있습니다.
      </p>
    </div>
  );
}
