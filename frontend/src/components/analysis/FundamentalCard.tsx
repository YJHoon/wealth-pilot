"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw } from "@/lib/format";
import { DataFreshnessBadge } from "./DataFreshnessBadge";
import type { FundamentalAnalysis, ValuationSignal } from "@/types";

interface FundamentalCardProps {
  data: FundamentalAnalysis;
}

const MASK = "●●●●●●";

const signalConfig: Record<ValuationSignal, { label: string; className: string }> = {
  undervalued: { label: "저평가", className: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  fair: { label: "적정", className: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  overvalued: { label: "고평가", className: "bg-red-500/20 text-red-400 border-red-500/30" },
};

function MetricRow({ label, value, compare }: { label: string; value: string | null; compare?: string | null }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{value ?? "-"}</span>
        {compare && (
          <span className="text-xs text-muted-foreground">
            (섹터 {compare})
          </span>
        )}
      </div>
    </div>
  );
}

export function FundamentalCard({ data }: FundamentalCardProps) {
  const isMasked = useAppStore((s) => s.isMasked);

  const fmt = (v: number | null) => (v != null ? v.toFixed(2) : null);
  const fmtPrice = (v: number | null) => (v != null ? formatMaskedKrw(v, isMasked) : isMasked ? `${MASK}원` : "-");

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <CardTitle className="text-base">기본적 분석</CardTitle>
            {data.companyName && (
              <p className="text-sm text-muted-foreground">
                {data.companyName}
                {data.sector && ` · ${data.sector}`}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {data.valuationSignal && (
              <Badge variant="outline" className={signalConfig[data.valuationSignal].className}>
                {signalConfig[data.valuationSignal].label}
              </Badge>
            )}
            <DataFreshnessBadge dataSource={data.dataSource} updatedAt={data.updatedAt} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 핵심 지표 */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {([
            { label: "PER", value: fmt(data.per), sector: fmt(data.sectorAvgPer) },
            { label: "PBR", value: fmt(data.pbr), sector: fmt(data.sectorAvgPbr) },
            { label: "ROE", value: data.roe != null ? `${data.roe.toFixed(2)}%` : null, sector: null },
            { label: "EPS", value: data.eps != null ? (isMasked ? MASK : data.eps.toLocaleString("ko-KR")) : null, sector: null },
          ] as const).map((item) => (
            <div key={item.label} className="rounded-lg border border-border bg-muted/30 p-3 text-center">
              <p className="text-xs text-muted-foreground">{item.label}</p>
              <p className="mt-1 text-lg font-semibold">{item.value ?? "-"}</p>
              {item.sector && (
                <p className="mt-0.5 text-xs text-muted-foreground">섹터 {item.sector}</p>
              )}
            </div>
          ))}
        </div>

        {/* DCF 적정가 */}
        <div className="space-y-1 rounded-lg border border-border p-3">
          <MetricRow label="현재가" value={fmtPrice(data.currentPrice)} />
          <MetricRow label="PER 기반 적정가" value={fmtPrice(data.perBasedFairValue)} />
          {data.priceGapPct != null && (
            <MetricRow
              label="괴리율"
              value={`${data.priceGapPct >= 0 ? "+" : ""}${data.priceGapPct.toFixed(1)}%`}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
