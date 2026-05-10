"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AnalysisRunSummary } from "@/types/advisory";
import { runStatusLabels } from "@/types/advisory";
import { tradingModeLabels } from "@/types/trading";
import { History, RefreshCw } from "lucide-react";

const STATUS_CLASS: Record<string, string> = {
  done: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  failed: "bg-red-500/20 text-red-300 border-red-500/30",
  ready: "bg-sky-500/20 text-sky-300 border-sky-500/30",
  executing: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  analyzing: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  pending: "bg-muted text-muted-foreground border-border",
};

function formatTime(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ko-KR");
}

export interface RunHistoryListProps {
  items: AnalysisRunSummary[] | null;
  loading: boolean;
  activeRunId: string | null;
  onSelect: (runId: string) => void;
  onRefresh: () => void;
}

export function RunHistoryList({
  items,
  loading,
  activeRunId,
  onSelect,
  onRefresh,
}: RunHistoryListProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="size-4 text-muted-foreground" />
          <span className="text-sm font-medium">분석 이력</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-[11px]"
          onClick={onRefresh}
          disabled={loading}
        >
          <RefreshCw className={`size-3 mr-1 ${loading ? "animate-spin" : ""}`} />
          {loading ? "불러오는 중..." : "새로고침"}
        </Button>
      </div>

      {!items || items.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-xs text-muted-foreground">
            아직 분석 이력이 없습니다.
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => {
            const isActive = activeRunId === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelect(item.id)}
                  className={`w-full text-left rounded-md border bg-card px-3 py-2 transition-colors hover:bg-accent/40 ${isActive ? "border-sky-500/60" : "border-border"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={STATUS_CLASS[item.status] ?? ""}
                      >
                        {runStatusLabels[item.status]}
                      </Badge>
                      <Badge variant="outline">
                        {tradingModeLabels[item.mode]}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {item.itemCount}개 종목
                      </span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {formatTime(item.startedAt)}
                    </span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
