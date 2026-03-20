"use client";

import type { DataFreshness } from "@/types";

const freshnessConfig: Record<DataFreshness, { icon: string; label: string; color: string }> = {
  realtime: { icon: "\uD83D\uDFE2", label: "실시간", color: "text-emerald-500" },
  delayed: { icon: "\uD83D\uDFE1", label: "15분 지연", color: "text-yellow-500" },
  batch: { icon: "\uD83D\uDFE0", label: "1일 배치", color: "text-orange-500" },
  estimated: { icon: "\uD83D\uDD34", label: "추정치", color: "text-red-500" },
};

interface DataFreshnessIndicatorProps {
  updatedAt: string;
  freshness?: DataFreshness;
}

export function DataFreshnessIndicator({ updatedAt, freshness }: DataFreshnessIndicatorProps) {
  const now = new Date();
  const updated = new Date(updatedAt);
  const diffMs = now.getTime() - updated.getTime();
  const diffMin = Math.floor(diffMs / 60_000);

  // 자동 신뢰도 판단: freshness가 없으면 시간 기반으로 추정
  const level: DataFreshness = freshness ?? (
    diffMin < 5 ? "realtime"
    : diffMin < 30 ? "delayed"
    : diffMin < 1440 ? "batch"
    : "estimated"
  );

  const config = freshnessConfig[level];
  const formattedTime = updated.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="freshness">
      <span>{config.icon}</span>
      <span className={config.color}>{config.label}</span>
      <span>· 마지막 갱신: {formattedTime}</span>
    </div>
  );
}
