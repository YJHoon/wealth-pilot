"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/stores/appStore";
import { formatAmount, formatPnl } from "@/lib/format";
import type { DashboardSummary } from "@/types";
import { PNL_TABS } from "./constants";

interface TotalAssetCardProps {
  summary: DashboardSummary;
}

export function TotalAssetCard({ summary }: TotalAssetCardProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const [pnlTab, setPnlTab] = useState<"total" | "realized" | "unrealized">("total");

  const { previousDayChange, pnl } = summary;
  const changePositive = previousDayChange.amount >= 0;

  const pnlValue = pnl[pnlTab];
  const pnlPositive = pnlValue >= 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          총 자산
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 총자산 금액 */}
        <p className="text-3xl font-bold tracking-tight" data-testid="total-value">
          {formatAmount(summary.totalValueKrw, "KRW", isMasked)}
        </p>

        {/* 전일대비 */}
        <div className="flex items-center gap-3">
          <Badge
            variant={changePositive ? "default" : "destructive"}
            data-testid="daily-change"
          >
            {isMasked
              ? "●●●●"
              : `${changePositive ? "+" : ""}${previousDayChange.ratio.toFixed(2)}%`}
          </Badge>
          <span
            className={`text-sm font-medium ${changePositive ? "text-emerald-500" : "text-red-500"}`}
          >
            {formatPnl(previousDayChange.amount, "KRW", isMasked)}
          </span>
          <span className="text-xs text-muted-foreground">전일대비</span>
        </div>

        {/* PnL 탭 */}
        <div className="flex items-center gap-4 border-t pt-3">
          <div className="flex gap-1">
            {PNL_TABS.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setPnlTab(tab.value)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  pnlTab === tab.value
                    ? "bg-secondary text-secondary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <span
            className={`text-sm font-semibold ${pnlPositive ? "text-emerald-500" : "text-red-500"}`}
            data-testid="pnl-value"
          >
            {formatPnl(pnlValue, "KRW", isMasked)}
          </span>
          {!isMasked && pnl.totalRatio !== 0 && pnlTab === "total" && (
            <span
              className={`text-xs ${pnlPositive ? "text-emerald-500" : "text-red-500"}`}
            >
              ({pnlPositive ? "+" : ""}{pnl.totalRatio.toFixed(2)}%)
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
