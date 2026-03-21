"use client";

import { useState, useMemo } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardAction } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { formatAmount, assetTypeLabels } from "@/lib/format";
import type { DashboardSummary, AssetType } from "@/types";
import { ASSET_TYPE_COLORS } from "./constants";

interface AssetDonutChartProps {
  summary: DashboardSummary;
}

type ViewBy = "type" | "group";

interface ChartEntry {
  name: string;
  value: number;
  ratio: number;
  color: string;
}

const GROUP_COLORS = ["#06b6d4", "#a855f7", "#ec4899", "#84cc16", "#f97316", "#6366f1"];

export function AssetDonutChart({ summary }: AssetDonutChartProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const [viewBy, setViewBy] = useState<ViewBy>("type");

  const data = useMemo<ChartEntry[]>(() => {
    if (viewBy === "type") {
      return (Object.entries(summary.byType) as [AssetType, { valueKrw: number; ratio: number }][])
        .filter(([, v]) => v.valueKrw > 0)
        .map(([key, v]) => ({
          name: assetTypeLabels[key],
          value: v.valueKrw,
          ratio: v.ratio,
          color: ASSET_TYPE_COLORS[key],
        }));
    }
    return Object.entries(summary.byGroup)
      .filter(([, v]) => v.valueKrw > 0)
      .map(([, v], i) => ({
        name: v.name,
        value: v.valueKrw,
        ratio: v.ratio,
        color: GROUP_COLORS[i % GROUP_COLORS.length],
      }));
  }, [summary, viewBy]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          자산 구성
        </CardTitle>
        <CardAction>
          <div className="flex gap-1">
            <Button
              variant={viewBy === "type" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewBy("type")}
            >
              유형별
            </Button>
            <Button
              variant={viewBy === "group" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewBy("group")}
            >
              그룹별
            </Button>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-52 items-center justify-center text-sm text-muted-foreground">
            자산 데이터가 없습니다
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <div className="h-44 w-44 shrink-0 sm:h-52 sm:w-52">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {data.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  {!isMasked && (
                    <RechartsTooltip
                      formatter={(value) => formatAmount(Number(value), "KRW", false)}
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        borderColor: "hsl(var(--border))",
                        borderRadius: "8px",
                        fontSize: "12px",
                      }}
                    />
                  )}
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* 범례 */}
            <div className="flex flex-1 flex-col gap-2">
              {data.map((entry) => (
                <div key={entry.name} className="flex items-center justify-between gap-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: entry.color }}
                    />
                    <span className="text-muted-foreground">{entry.name}</span>
                  </div>
                  <div className="text-right font-mono">
                    {isMasked ? "●●%" : (
                      <>
                        <span className="font-medium">{entry.ratio.toFixed(1)}%</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
