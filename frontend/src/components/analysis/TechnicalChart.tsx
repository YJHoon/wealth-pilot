"use client";

import { useState } from "react";
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardAction } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/stores/appStore";
import { formatAmountAbbreviated } from "@/lib/format";
import { DataFreshnessBadge } from "./DataFreshnessBadge";
import type { TechnicalAnalysis } from "@/types";

interface TechnicalChartProps {
  data: TechnicalAnalysis;
}

type ChartTab = "ma" | "bollinger" | "rsi" | "macd";

const TABS: { value: ChartTab; label: string }[] = [
  { value: "ma", label: "이동평균" },
  { value: "bollinger", label: "볼린저밴드" },
  { value: "rsi", label: "RSI" },
  { value: "macd", label: "MACD" },
];

function getRsiStatus(rsi: number): { label: string; className: string } {
  if (rsi >= 70) return { label: "과매수", className: "text-red-400" };
  if (rsi <= 30) return { label: "과매도", className: "text-emerald-400" };
  return { label: "중립", className: "text-muted-foreground" };
}

export function TechnicalChart({ data }: TechnicalChartProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const [activeTab, setActiveTab] = useState<ChartTab>("ma");

  // 이동평균선 데이터 (현재 스냅샷 포인트 기반)
  const maData = [
    { name: "5일", value: data.sma5 },
    { name: "20일", value: data.sma20 },
    { name: "60일", value: data.sma60 },
    { name: "120일", value: data.sma120 },
  ].filter((d) => d.value != null);

  // 볼린저밴드 데이터
  const bollingerData = [
    { name: "상단", value: data.bollingerUpper },
    { name: "중단", value: data.bollingerMiddle },
    { name: "현재가", value: data.currentPrice },
    { name: "하단", value: data.bollingerLower },
  ].filter((d) => d.value != null);

  // MACD 데이터
  const macdData = [
    { name: "MACD", macd: data.macd, signal: data.macdSignal, histogram: data.macdHistogram },
  ];

  const tickFormatter = (v: number) => (isMasked ? "●●●" : formatAmountAbbreviated(v));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">기술적 분석</CardTitle>
          <DataFreshnessBadge dataSource={data.dataSource} updatedAt={data.updatedAt} />
        </div>
        <CardAction>
          <div className="flex gap-1">
            {TABS.map((tab) => (
              <Button
                key={tab.value}
                variant={activeTab === tab.value ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setActiveTab(tab.value)}
              >
                {tab.label}
              </Button>
            ))}
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        {/* 이동평균선 */}
        {activeTab === "ma" && (
          <div className="space-y-3">
            <div className="h-52">
              {maData.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  이동평균 데이터가 없습니다
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={maData} margin={{ top: 5, right: 5, bottom: 0, left: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tickFormatter={tickFormatter}
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                      width={60}
                    />
                    {!isMasked && (
                      <RechartsTooltip
                        formatter={(value) => [formatAmountAbbreviated(Number(value)), ""]}
                        contentStyle={{
                          backgroundColor: "hsl(var(--card))",
                          borderColor: "hsl(var(--border))",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                      />
                    )}
                    <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} />
                    {data.currentPrice != null && (
                      <ReferenceLine
                        y={data.currentPrice}
                        stroke="#f59e0b"
                        strokeDasharray="5 5"
                        label={{ value: "현재가", fontSize: 11, fill: "#f59e0b" }}
                      />
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </div>
            {/* 지지/저항선 */}
            {(data.supportLevel != null || data.resistanceLevel != null) && (
              <div className="flex gap-4 text-sm">
                {data.supportLevel != null && (
                  <span className="text-muted-foreground">
                    지지선: <span className="font-medium text-emerald-400">{isMasked ? "●●●" : data.supportLevel.toLocaleString("ko-KR")}</span>
                  </span>
                )}
                {data.resistanceLevel != null && (
                  <span className="text-muted-foreground">
                    저항선: <span className="font-medium text-red-400">{isMasked ? "●●●" : data.resistanceLevel.toLocaleString("ko-KR")}</span>
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* 볼린저밴드 */}
        {activeTab === "bollinger" && (
          <div className="h-52">
            {bollingerData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                볼린저밴드 데이터가 없습니다
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={bollingerData} margin={{ top: 5, right: 5, bottom: 0, left: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tickFormatter={tickFormatter}
                    tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={false}
                    tickLine={false}
                    width={60}
                  />
                  {!isMasked && (
                    <RechartsTooltip
                      formatter={(value) => [formatAmountAbbreviated(Number(value)), ""]}
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        borderColor: "hsl(var(--border))",
                        borderRadius: "8px",
                        fontSize: "12px",
                      }}
                    />
                  )}
                  <Line type="monotone" dataKey="value" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 4 }} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        )}

        {/* RSI */}
        {activeTab === "rsi" && (
          <div className="flex h-52 flex-col items-center justify-center gap-3">
            {data.rsi != null ? (
              <>
                <div className="text-center">
                  <p className="text-5xl font-bold">{data.rsi.toFixed(1)}</p>
                  <p className={`mt-1 text-sm font-medium ${getRsiStatus(data.rsi).className}`}>
                    {getRsiStatus(data.rsi).label}
                  </p>
                </div>
                {/* RSI 바 */}
                <div className="w-full max-w-xs">
                  <div className="relative h-3 rounded-full bg-muted">
                    <div
                      className="absolute left-0 top-0 h-full rounded-full bg-gradient-to-r from-emerald-500 via-blue-500 to-red-500"
                      style={{ width: "100%" }}
                    />
                    <div
                      className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground"
                      style={{ left: `${Math.min(Math.max(data.rsi, 0), 100)}%` }}
                    />
                  </div>
                  <div className="mt-1 flex justify-between text-xs text-muted-foreground">
                    <span>0 (과매도)</span>
                    <span>50</span>
                    <span>100 (과매수)</span>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">RSI 데이터가 없습니다</p>
            )}
          </div>
        )}

        {/* MACD */}
        {activeTab === "macd" && (
          <div className="space-y-3">
            {data.macd != null ? (
              <>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-xs text-muted-foreground">MACD</p>
                    <p className="mt-1 text-lg font-semibold">{data.macd.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Signal</p>
                    <p className="mt-1 text-lg font-semibold">{data.macdSignal?.toFixed(2) ?? "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Histogram</p>
                    <p className={`mt-1 text-lg font-semibold ${(data.macdHistogram ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {data.macdHistogram?.toFixed(2) ?? "-"}
                    </p>
                  </div>
                </div>
                <div className="h-36">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={macdData} margin={{ top: 5, right: 5, bottom: 0, left: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="name" hide />
                      <YAxis
                        tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                        axisLine={false}
                        tickLine={false}
                        width={50}
                      />
                      <Bar dataKey="histogram" fill={(data.macdHistogram ?? 0) >= 0 ? "#10b981" : "#ef4444"} barSize={40} />
                      <Line type="monotone" dataKey="macd" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} />
                      <Line type="monotone" dataKey="signal" stroke="#f59e0b" strokeWidth={2} dot={{ r: 4 }} />
                      <ReferenceLine y={0} stroke="hsl(var(--border))" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex justify-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <span className="inline-block size-2 rounded-full bg-blue-500" /> MACD
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block size-2 rounded-full bg-amber-500" /> Signal
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block size-2 rounded-full bg-emerald-500" /> Histogram
                  </span>
                </div>
              </>
            ) : (
              <div className="flex h-52 items-center justify-center text-sm text-muted-foreground">
                MACD 데이터가 없습니다
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
