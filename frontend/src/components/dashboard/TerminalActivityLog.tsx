"use client";

import { ArrowDownRight, ArrowUpRight, RefreshCw } from "lucide-react";
import type { ActivityItem } from "@/hooks/useDashboardData";
import { useAppStore } from "@/stores/appStore";

const typeConfig = {
  buy: { icon: ArrowDownRight, color: "text-emerald-400", label: "매수" },
  sell: { icon: ArrowUpRight, color: "text-red-400", label: "매도" },
  priceUpdate: { icon: RefreshCw, color: "text-blue-400", label: "시세" },
} as const;

function formatRelativeTime(iso: string): string {
  const ts = new Date(iso).getTime();
  if (isNaN(ts)) return "-";
  const diff = Math.max(Date.now() - ts, 0);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "방금";
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  return `${days}일 전`;
}

interface Props {
  activity: ActivityItem[];
}

export function TerminalActivityLog({ activity }: Props) {
  const { isMasked } = useAppStore();

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          최근 거래 · 변동
        </h3>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-card">
            <tr className="text-muted-foreground border-b border-border">
              <th className="text-left py-1.5 px-3 font-medium">유형</th>
              <th className="text-left py-1.5 px-2 font-medium">종목</th>
              <th className="text-left py-1.5 px-2 font-medium">내용</th>
              <th className="text-right py-1.5 px-2 font-medium">금액</th>
              <th className="text-right py-1.5 px-3 font-medium">시간</th>
            </tr>
          </thead>
          <tbody className="font-[family-name:var(--font-geist-mono)]">
            {activity.map((item) => {
              const config = typeConfig[item.type];
              const Icon = config.icon;
              return (
                <tr
                  key={item.id}
                  className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                >
                  <td className="py-1.5 px-3">
                    <div className={`flex items-center gap-1 ${config.color}`}>
                      <Icon className="h-3 w-3" />
                      <span>{config.label}</span>
                    </div>
                  </td>
                  <td className="py-1.5 px-2 text-foreground">{item.assetName}</td>
                  <td className="py-1.5 px-2 text-muted-foreground">{item.description}</td>
                  <td className="py-1.5 px-2 text-right text-foreground">
                    {item.amount == null
                      ? "-"
                      : isMasked
                        ? "●●●●●●원"
                        : `${Math.round(item.amount).toLocaleString("ko-KR")}원`}
                  </td>
                  <td className="py-1.5 px-3 text-right text-muted-foreground">
                    {formatRelativeTime(item.timestamp)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
