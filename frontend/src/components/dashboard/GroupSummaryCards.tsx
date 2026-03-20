"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppStore } from "@/stores/appStore";
import { formatAmount } from "@/lib/format";
import type { DashboardSummary } from "@/types";

interface GroupSummaryCardsProps {
  summary: DashboardSummary;
}

export function GroupSummaryCards({ summary }: GroupSummaryCardsProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const groups = Object.entries(summary.byGroup).filter(([, v]) => v.valueKrw > 0);

  if (groups.length === 0) return null;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-muted-foreground">그룹별 요약</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {groups.map(([id, group]) => (
          <Card key={id} size="sm">
            <CardHeader>
              <CardTitle>{group.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-lg font-semibold font-mono" data-testid={`group-value-${id}`}>
                {formatAmount(group.valueKrw, "KRW", isMasked)}
              </p>
              {/* progress bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>비중</span>
                  <span>{isMasked ? "●●%" : `${group.ratio.toFixed(1)}%`}</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${Math.min(group.ratio, 100)}%` }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
