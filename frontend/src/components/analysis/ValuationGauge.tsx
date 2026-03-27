"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw } from "@/lib/format";
import type { FundamentalAnalysis } from "@/types";

interface ValuationGaugeProps {
  data: FundamentalAnalysis;
}

export function ValuationGauge({ data }: ValuationGaugeProps) {
  const isMasked = useAppStore((s) => s.isMasked);

  const currentPrice = data.currentPrice;
  const fairValue = data.perBasedFairValue;

  if (currentPrice == null || fairValue == null || fairValue === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">적정가 대비 현재가</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">적정가 데이터가 부족합니다</p>
        </CardContent>
      </Card>
    );
  }

  // 비율: 1.0 = 적정가, >1 고평가, <1 저평가
  const ratio = currentPrice / fairValue;
  // 게이지 위치: 0~200% 범위를 0~100%로 매핑
  const gaugePercent = Math.min(Math.max((ratio / 2) * 100, 0), 100);
  const gapPct = data.priceGapPct;

  // 색상 결정
  const getColor = () => {
    if (ratio < 0.85) return "text-emerald-400";
    if (ratio > 1.15) return "text-red-400";
    return "text-blue-400";
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">적정가 대비 현재가</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 게이지 바 */}
        <div className="space-y-2">
          <div className="relative h-4 rounded-full bg-gradient-to-r from-emerald-500/30 via-blue-500/30 to-red-500/30">
            {/* 적정가 마커 (50%) */}
            <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-muted-foreground/50" />
            {/* 현재가 마커 */}
            <div
              className="absolute top-1/2 size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground shadow-lg"
              style={{ left: `${gaugePercent}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>저평가</span>
            <span>적정</span>
            <span>고평가</span>
          </div>
        </div>

        {/* 가격 비교 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border border-border p-3 text-center">
            <p className="text-xs text-muted-foreground">현재가</p>
            <p className="mt-1 text-lg font-semibold">
              {formatMaskedKrw(currentPrice, isMasked)}
            </p>
          </div>
          <div className="rounded-lg border border-border p-3 text-center">
            <p className="text-xs text-muted-foreground">PER 기반 적정가</p>
            <p className="mt-1 text-lg font-semibold">
              {formatMaskedKrw(fairValue, isMasked)}
            </p>
          </div>
        </div>

        {/* 괴리율 */}
        {gapPct != null && (
          <div className="text-center">
            <span className={`text-2xl font-bold ${getColor()}`}>
              {gapPct >= 0 ? "+" : ""}
              {gapPct.toFixed(1)}%
            </span>
            <p className="mt-0.5 text-xs text-muted-foreground">괴리율</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
