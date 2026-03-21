"use client";

import { useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Button } from "@/components/ui/button";
import type { DashboardSummary, AssetType } from "@/types";
import { useAppStore } from "@/stores/appStore";
import {
  formatMaskedKrw,
  formatPercent,
  formatChangeKrw,
  pnlColorClass,
  assetTypeLabels,
} from "@/lib/format";

const PIE_COLORS = ["#3b82f6", "#8b5cf6", "#f97316", "#eab308", "#14b8a6"];

type ViewMode = "type" | "group";

interface Props {
  summary: DashboardSummary;
}

interface PieEntry {
  name: string;
  value: number;
  ratio: number;
}

function buildPieData(summary: DashboardSummary, mode: ViewMode): PieEntry[] {
  if (mode === "type") {
    return (Object.entries(summary.byType) as [AssetType, { valueKrw: number; ratio: number }][])
      .filter(([, v]) => v.valueKrw > 0)
      .map(([type, v]) => ({
        name: assetTypeLabels[type],
        value: v.valueKrw,
        ratio: v.ratio,
      }));
  }
  return Object.values(summary.byGroup)
    .filter((v) => v.valueKrw > 0)
    .map((v) => ({
      name: v.name,
      value: v.valueKrw,
      ratio: v.ratio,
    }));
}

interface PieTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: PieEntry }>;
  isMasked: boolean;
}

function PieTooltipContent({ active, payload, isMasked }: PieTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-lg">
      <div className="font-medium">{d.name}</div>
      <div className="text-muted-foreground">
        {formatMaskedKrw(d.value, isMasked)} ({d.ratio.toFixed(1)}%)
      </div>
    </div>
  );
}

export function TerminalSummaryPanel({ summary }: Props) {
  const { isMasked } = useAppStore();
  const [pieMode, setPieMode] = useState<ViewMode>("type");
  const pieData = buildPieData(summary, pieMode);

  const pnlTabs = [
    { key: "total", label: "합산", value: summary.pnl.total },
    { key: "realized", label: "실현", value: summary.pnl.realized },
    { key: "unrealized", label: "미실현", value: summary.pnl.unrealized },
  ] as const;
  const [pnlTab, setPnlTab] = useState<string>("total");
  const currentPnl = pnlTabs.find((t) => t.key === pnlTab)!;

  return (
    <div className="flex flex-col h-full gap-0">
      {/* 총 자산 */}
      <div className="px-3 py-2 border-b border-border">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-0.5">
          총 자산
        </div>
        <div className="text-xl font-bold font-[family-name:var(--font-geist-mono)]">
          {formatMaskedKrw(summary.totalValueKrw, isMasked)}
        </div>
        <div className={`text-xs ${pnlColorClass(summary.previousDayChange.amount)}`}>
          전일 대비{" "}
          {formatChangeKrw(summary.previousDayChange.amount, isMasked)}{" "}
          ({formatPercent(summary.previousDayChange.ratio)})
        </div>
      </div>

      {/* 수익률 탭 */}
      <div className="px-3 py-2 border-b border-border">
        <div className="flex gap-0.5 mb-2">
          {pnlTabs.map((tab) => (
            <Button
              key={tab.key}
              variant={pnlTab === tab.key ? "secondary" : "ghost"}
              size="sm"
              className="h-5 px-2 text-[10px] flex-1"
              onClick={() => setPnlTab(tab.key)}
            >
              {tab.label}
            </Button>
          ))}
        </div>
        <div className={`text-lg font-bold font-[family-name:var(--font-geist-mono)] ${pnlColorClass(currentPnl.value)}`}>
          {formatChangeKrw(currentPnl.value, isMasked)}
        </div>
        <div className={`text-xs ${pnlColorClass(summary.pnl.totalRatio)}`}>
          총 수익률 {formatPercent(summary.pnl.totalRatio)}
        </div>
      </div>

      {/* 자산 비중 도넛 */}
      <div className="px-3 py-2 border-b border-border flex-1 min-h-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            자산 비중
          </span>
          <div className="flex gap-0.5">
            <Button
              variant={pieMode === "type" ? "secondary" : "ghost"}
              size="sm"
              className="h-5 px-1.5 text-[10px]"
              onClick={() => setPieMode("type")}
            >
              유형
            </Button>
            <Button
              variant={pieMode === "group" ? "secondary" : "ghost"}
              size="sm"
              className="h-5 px-1.5 text-[10px]"
              onClick={() => setPieMode("group")}
            >
              그룹
            </Button>
          </div>
        </div>

        <div className="h-[140px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={35}
                outerRadius={55}
                dataKey="value"
                stroke="none"
                animationDuration={500}
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<PieTooltipContent isMasked={isMasked} />} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* 범례 */}
        <div className="space-y-1 mt-1">
          {pieData.map((entry, i) => (
            <div key={entry.name} className="flex items-center justify-between text-[11px]">
              <div className="flex items-center gap-1.5">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                />
                <span className="text-muted-foreground">{entry.name}</span>
              </div>
              <span className="font-[family-name:var(--font-geist-mono)] text-foreground">
                {entry.ratio.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 그룹별 소계 */}
      <div className="px-3 py-2">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">
          그룹별 소계
        </div>
        <div className="space-y-1.5">
          {Object.values(summary.byGroup).map((group) => (
            <div key={group.name} className="flex justify-between text-xs">
              <span className="text-muted-foreground">{group.name}</span>
              <span className="font-[family-name:var(--font-geist-mono)]">
                {formatMaskedKrw(group.valueKrw, isMasked)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
