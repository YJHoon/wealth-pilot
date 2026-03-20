"use client";

import { useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardAction } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { formatAmount, formatAmountAbbreviated } from "@/lib/format";
import { useDashboardHistory } from "@/hooks/useDashboardHistory";
import { PERIOD_OPTIONS } from "./constants";
import { Loader2 } from "lucide-react";

export function AssetTrendChart() {
  const isMasked = useAppStore((s) => s.isMasked);
  const [period, setPeriod] = useState("3M");
  const { history, loading, error } = useDashboardHistory(period);

  const formatDate = (date: string) => {
    const d = new Date(date);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          자산 추이
        </CardTitle>
        <CardAction>
          <div className="flex gap-1">
            {PERIOD_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                variant={period === opt.value ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setPeriod(opt.value)}
              >
                {opt.label}
              </Button>
            ))}
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex h-52 items-center justify-center text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        ) : error ? (
          <div className="flex h-52 items-center justify-center text-sm text-muted-foreground">
            {error}
          </div>
        ) : history.length === 0 ? (
          <div className="flex h-52 items-center justify-center text-sm text-muted-foreground">
            기간 내 데이터가 없습니다
          </div>
        ) : (
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 5, right: 5, bottom: 0, left: 5 }}>
                <defs>
                  <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatDate}
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={(v: number) => isMasked ? "●●●" : formatAmountAbbreviated(v)}
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  axisLine={false}
                  tickLine={false}
                  width={60}
                />
                {!isMasked && (
                  <RechartsTooltip
                    formatter={(value) => [formatAmount(Number(value), "KRW", false), "총 자산"]}
                    labelFormatter={(label) => formatDate(String(label))}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      borderColor: "hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                )}
                <Area
                  type="monotone"
                  dataKey="totalValueKrw"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="url(#trendGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
