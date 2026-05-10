"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw, formatQuantity } from "@/lib/format";
import type {
  AnalysisRunItem,
  AnalysisItemAction,
  AnalysisItemDecision,
} from "@/types/advisory";
import {
  itemActionLabels,
  itemDecisionLabels,
  itemSourceLabels,
} from "@/types/advisory";
import { cn } from "@/lib/utils";

const ACTION_BADGE_CLASS: Record<AnalysisItemAction, string> = {
  buy: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  sell: "bg-red-500/20 text-red-300 border-red-500/30",
  hold: "bg-muted text-muted-foreground border-border",
};

const DECISION_BADGE_CLASS: Record<AnalysisItemDecision, string> = {
  pending: "bg-muted text-muted-foreground border-border",
  approved: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  skipped: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  rejected: "bg-red-500/20 text-red-300 border-red-500/30",
};

export interface ResultCardListProps {
  items: AnalysisRunItem[];
  selectedIds: Set<string>;
  onToggle: (itemId: string, checked: boolean) => void;
  readOnly: boolean;
}

export function ResultCardList({
  items,
  selectedIds,
  onToggle,
  readOnly,
}: ResultCardListProps) {
  const isMasked = useAppStore((s) => s.isMasked);

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          분석 결과가 비어있습니다.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-2">
      {items.map((item) => {
        const isCheckable =
          !readOnly &&
          item.decision === "pending" &&
          (item.action === "buy" || item.action === "sell");
        const checked = selectedIds.has(item.id);
        const dimmed =
          item.decision === "skipped" || item.action === "hold";

        return (
          <Card
            key={item.id}
            className={cn(
              "transition-colors",
              dimmed && "opacity-60",
              checked && "ring-1 ring-sky-500/50",
            )}
          >
            <CardContent className="pt-3 pb-3">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1 size-4 rounded border-border"
                  disabled={!isCheckable}
                  checked={checked}
                  onChange={(e) => onToggle(item.id, e.target.checked)}
                  aria-label={`${item.tickerName ?? item.ticker} 선택`}
                />

                <div className="flex-1 min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {item.tickerName || item.ticker}
                    </span>
                    <span className="text-[11px] font-mono text-muted-foreground">
                      {item.ticker}
                    </span>
                    <Badge
                      variant="outline"
                      className={ACTION_BADGE_CLASS[item.action]}
                    >
                      {itemActionLabels[item.action]}
                    </Badge>
                    <Badge variant="outline">
                      {itemSourceLabels[item.source]}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={cn(
                        "tabular-nums",
                        item.confidence >= 80
                          ? "border-emerald-500/40 text-emerald-300"
                          : item.confidence >= 70
                            ? "border-sky-500/40 text-sky-300"
                            : "border-amber-500/40 text-amber-300",
                      )}
                    >
                      신뢰도 {item.confidence}
                    </Badge>
                    {item.decision !== "pending" && (
                      <Badge
                        variant="outline"
                        className={DECISION_BADGE_CLASS[item.decision]}
                      >
                        {itemDecisionLabels[item.decision]}
                      </Badge>
                    )}
                  </div>

                  {item.reason && (
                    <p className="text-xs text-muted-foreground line-clamp-3">
                      {item.reason}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                    {item.refPrice != null && (
                      <span>
                        참조가{" "}
                        <span className="text-foreground tabular-nums">
                          {formatMaskedKrw(item.refPrice, isMasked)}
                        </span>
                      </span>
                    )}
                    {item.suggestedQty != null && (
                      <span>
                        제안 수량{" "}
                        <span className="text-foreground tabular-nums">
                          {formatQuantity(item.suggestedQty, isMasked)}
                        </span>
                      </span>
                    )}
                    {item.refPrice != null && item.suggestedQty != null && (
                      <span>
                        예상 금액{" "}
                        <span className="text-foreground tabular-nums">
                          {formatMaskedKrw(
                            item.refPrice * item.suggestedQty,
                            isMasked,
                          )}
                        </span>
                      </span>
                    )}
                  </div>

                  {item.blockedReason && (
                    <p className="text-[11px] text-amber-400">
                      차단 사유: {item.blockedReason}
                    </p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
