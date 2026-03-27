"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw } from "@/lib/format";
import { DataFreshnessBadge } from "./DataFreshnessBadge";
import type { TradingSignals, TradingSignalAction, RiskLevel } from "@/types";
import { TrendingUp, TrendingDown, Minus, ShieldAlert } from "lucide-react";

interface SignalCardProps {
  data: TradingSignals;
}

const MASK = "●●●●●●";

const actionConfig: Record<TradingSignalAction, { label: string; icon: typeof TrendingUp; className: string; bgClass: string }> = {
  buy: { label: "매수", icon: TrendingUp, className: "text-emerald-400", bgClass: "bg-emerald-500/10 border-emerald-500/30" },
  sell: { label: "매도", icon: TrendingDown, className: "text-red-400", bgClass: "bg-red-500/10 border-red-500/30" },
  hold: { label: "관망", icon: Minus, className: "text-amber-400", bgClass: "bg-amber-500/10 border-amber-500/30" },
};

const riskConfig: Record<RiskLevel, { className: string }> = {
  "상": { className: "bg-red-500/20 text-red-400 border-red-500/30" },
  "중": { className: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  "하": { className: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
};

export function SignalCard({ data }: SignalCardProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const config = actionConfig[data.action];
  const Icon = config.icon;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">매매 시그널</CardTitle>
          <DataFreshnessBadge dataSource={data.dataSource} updatedAt={data.updatedAt} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 시그널 메인 */}
        <div className={`flex items-center justify-between rounded-lg border p-4 ${config.bgClass}`}>
          <div className="flex items-center gap-3">
            <Icon className={`size-8 ${config.className}`} />
            <div>
              <p className={`text-2xl font-bold ${config.className}`}>{config.label}</p>
              {data.currentPrice != null && (
                <p className="text-sm text-muted-foreground">
                  현재가 {formatMaskedKrw(data.currentPrice, isMasked)}
                </p>
              )}
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">신뢰도</p>
            <p className="text-2xl font-bold">{Math.round(data.confidence * 100)}%</p>
          </div>
        </div>

        {/* 리스크 + 점수 */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-border p-3 text-center">
            <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground">
              <ShieldAlert className="size-3" />
              리스크
            </div>
            <Badge variant="outline" className={`mt-1.5 ${riskConfig[data.riskLevel].className}`}>
              {data.riskLevel}
            </Badge>
          </div>
          <div className="rounded-lg border border-border p-3 text-center">
            <p className="text-xs text-muted-foreground">기본적 점수</p>
            <p className="mt-1.5 text-lg font-semibold">
              {data.fundamentalScore != null ? `${Math.round(data.fundamentalScore * 100)}` : "-"}
            </p>
          </div>
          <div className="rounded-lg border border-border p-3 text-center">
            <p className="text-xs text-muted-foreground">기술적 점수</p>
            <p className="mt-1.5 text-lg font-semibold">
              {data.technicalScore != null ? `${Math.round(data.technicalScore * 100)}` : "-"}
            </p>
          </div>
        </div>

        {/* 근거 */}
        {data.reasons.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">판단 근거</p>
            <ul className="space-y-1">
              {data.reasons.map((reason, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground" />
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
