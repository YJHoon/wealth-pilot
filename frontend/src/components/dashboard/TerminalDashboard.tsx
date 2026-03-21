"use client";

import { RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TerminalAssetTable } from "./TerminalAssetTable";
import { TerminalChart } from "./TerminalChart";
import { TerminalSummaryPanel } from "./TerminalSummaryPanel";
import { TerminalActivityLog } from "./TerminalActivityLog";
import { useDashboardData } from "@/hooks/useDashboardData";

const defaultBadge = { label: "알 수 없음", dot: "bg-muted-foreground" } as const;

const freshnessBadge: Record<string, { label: string; dot: string }> = {
  realtime: { label: "실시간", dot: "bg-emerald-400" },
  delayed: { label: "15분 지연", dot: "bg-yellow-400" },
  batch: { label: "1일 배치", dot: "bg-orange-400" },
  estimated: { label: "추정치", dot: "bg-red-400" },
};

export function TerminalDashboard() {
  const data = useDashboardData();

  if (data.isLoading) {
    return (
      <div className="flex h-full items-center justify-center" role="status" aria-label="대시보드 로딩 중">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="sr-only">로딩 중…</span>
      </div>
    );
  }
  const badge = freshnessBadge[data.freshness] ?? defaultBadge;
  const parsed = new Date(data.summary.updatedAt);
  const lastUpdated = Number.isFinite(parsed.getTime())
    ? parsed.toLocaleString("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "-";

  return (
    <div className="flex flex-col h-full gap-2">
      {/* 상단 바: 갱신 상태 */}
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
          onClick={() => void data.refresh()}
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

      {/* 메인 그리드: 3컬럼 */}
      <div className="grid grid-cols-[280px_1fr_240px] gap-2 flex-1 min-h-0">
        {/* 좌: 자산 테이블 */}
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <TerminalAssetTable assets={data.assets} />
        </div>

        {/* 중: 차트 */}
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <TerminalChart
            data={data.history}
            period={data.historyPeriod}
            onPeriodChange={data.setHistoryPeriod}
          />
        </div>

        {/* 우: 요약 */}
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <TerminalSummaryPanel summary={data.summary} />
        </div>
      </div>

      {/* 하단: 활동 로그 */}
      <div className="rounded-lg border border-border bg-card overflow-hidden h-[180px]">
        <TerminalActivityLog activity={data.activity} />
      </div>

      {/* 면책 문구 */}
      <div className="text-[10px] text-muted-foreground text-center pb-1">
        본 서비스는 투자 조언을 제공하지 않습니다. 표시된 시세는 지연될 수 있으며, 투자 판단의 책임은 사용자에게 있습니다.
      </div>
    </div>
  );
}
