"use client";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { Button } from "@/components/ui/button";
import type { HistoryPoint } from "@/hooks/useDashboardData";
import { useAppStore } from "@/stores/appStore";

const PERIODS = ["1M", "3M", "6M", "1Y"] as const;

interface Props {
  data: HistoryPoint[];
  period: string;
  onPeriodChange: (p: string) => void;
}

function formatAxisKrw(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}억`;
  if (value >= 10_000) return `${(value / 10_000).toFixed(0)}만`;
  return value.toLocaleString();
}

function formatDateLabel(date: string): string {
  const d = new Date(date);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
  isMasked: boolean;
}

function ChartTooltip({ active, payload, label, isMasked }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-lg">
      <div className="text-muted-foreground mb-1">{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="flex justify-between gap-4">
          <span className="text-muted-foreground">
            {entry.name === "totalKrw"
              ? "총 자산"
              : entry.name === "stock"
                ? "주식"
                : entry.name === "crypto"
                  ? "코인"
                  : "현금"}
          </span>
          <span className="font-[family-name:var(--font-geist-mono)] text-foreground">
            {isMasked ? "●●●●●●원" : `${Math.round(entry.value).toLocaleString("ko-KR")}원`}
          </span>
        </div>
      ))}
    </div>
  );
}

export function TerminalChart({ data, period, onPeriodChange }: Props) {
  const { isMasked } = useAppStore();

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          자산 추이
        </h3>
        <div className="flex gap-0.5">
          {PERIODS.map((p) => (
            <Button
              key={p}
              variant={period === p ? "secondary" : "ghost"}
              size="sm"
              className="h-6 px-2 text-[10px]"
              onClick={() => onPeriodChange(p)}
            >
              {p}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex-1 px-2 py-3 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id="gradTotal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="oklch(0.546 0.245 262.881)" stopOpacity={0.4} />
                <stop offset="100%" stopColor="oklch(0.546 0.245 262.881)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradStock" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradCrypto" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f97316" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="oklch(1 0 0 / 5%)"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              tickFormatter={formatDateLabel}
              tick={{ fontSize: 10, fill: "oklch(0.708 0 0)" }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              tickFormatter={(v) => (isMasked ? "●●●" : formatAxisKrw(v))}
              tick={{ fontSize: 10, fill: "oklch(0.708 0 0)" }}
              axisLine={false}
              tickLine={false}
              width={50}
            />
            <Tooltip content={<ChartTooltip isMasked={isMasked} />} />
            <Area
              type="monotone"
              dataKey="totalKrw"
              stroke="oklch(0.546 0.245 262.881)"
              strokeWidth={2}
              fill="url(#gradTotal)"
              dot={false}
              animationDuration={500}
            />
            <Area
              type="monotone"
              dataKey="stock"
              stroke="#3b82f6"
              strokeWidth={1}
              fill="url(#gradStock)"
              dot={false}
              animationDuration={500}
            />
            <Area
              type="monotone"
              dataKey="crypto"
              stroke="#f97316"
              strokeWidth={1}
              fill="url(#gradCrypto)"
              dot={false}
              animationDuration={500}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
