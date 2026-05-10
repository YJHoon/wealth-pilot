"use client";

import { useEffect, useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw, formatQuantity } from "@/lib/format";
import type { AnalysisRunItem } from "@/types/advisory";
import { itemActionLabels } from "@/types/advisory";
import type { TradingMode } from "@/types/trading";

export interface ExecuteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: TradingMode;
  approvedItems: AnalysisRunItem[];
  isExecuting: boolean;
  onConfirm: (totpCode?: string) => void;
}

export function ExecuteDialog({
  open,
  onOpenChange,
  mode,
  approvedItems,
  isExecuting,
  onConfirm,
}: ExecuteDialogProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const [totpCode, setTotpCode] = useState("");

  useEffect(() => {
    if (!open) setTotpCode("");
  }, [open]);

  const totalKrw = approvedItems.reduce((sum, item) => {
    if (item.action !== "buy") return sum;
    if (item.refPrice == null || item.suggestedQty == null) return sum;
    return sum + item.refPrice * item.suggestedQty;
  }, 0);

  const buyCount = approvedItems.filter((i) => i.action === "buy").length;
  const sellCount = approvedItems.filter((i) => i.action === "sell").length;

  const requireTotp = mode === "live";
  const totpValid = !requireTotp || /^\d{6}$/.test(totpCode);
  const canConfirm = approvedItems.length > 0 && totpValid && !isExecuting;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>발주 확인</AlertDialogTitle>
          <AlertDialogDescription>
            승인 항목 {approvedItems.length}건을{" "}
            <span className="font-medium">
              {mode === "live" ? "실거래(live)" : "모의(paper)"}
            </span>{" "}
            계좌로 발주합니다.
            {mode === "live" && (
              <>
                {" "}
                실거래는 되돌릴 수 없습니다. 신중히 확인하세요.
              </>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-500/30">
              매수 {buyCount}
            </Badge>
            <Badge className="bg-red-500/20 text-red-300 border-red-500/30">
              매도 {sellCount}
            </Badge>
            <span className="text-muted-foreground">
              매수 예상 합계{" "}
              <span className="text-foreground tabular-nums">
                {formatMaskedKrw(totalKrw, isMasked)}
              </span>
            </span>
          </div>

          <div className="max-h-56 overflow-y-auto rounded-md border border-border/60 bg-muted/30 p-2 text-xs">
            {approvedItems.length === 0 ? (
              <p className="text-muted-foreground py-4 text-center">
                승인된 항목이 없습니다.
              </p>
            ) : (
              <ul className="space-y-1">
                {approvedItems.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge
                        variant="outline"
                        className={
                          item.action === "buy"
                            ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                            : "bg-red-500/15 text-red-300 border-red-500/30"
                        }
                      >
                        {itemActionLabels[item.action]}
                      </Badge>
                      <span className="font-medium truncate">
                        {item.tickerName || item.ticker}
                      </span>
                      <span className="text-[11px] font-mono text-muted-foreground">
                        {item.ticker}
                      </span>
                    </div>
                    <span className="tabular-nums text-muted-foreground">
                      {item.suggestedQty != null
                        ? `${formatQuantity(item.suggestedQty, isMasked)}주`
                        : "-"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {requireTotp && (
            <div className="space-y-1.5">
              <Label htmlFor="totp" className="text-xs">
                TOTP 인증 코드 (6자리)
              </Label>
              <Input
                id="totp"
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="123456"
                value={totpCode}
                onChange={(e) =>
                  setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
                autoFocus
                autoComplete="one-time-code"
              />
            </div>
          )}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isExecuting}>취소</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => onConfirm(requireTotp ? totpCode : undefined)}
            disabled={!canConfirm}
            className={
              mode === "live"
                ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                : ""
            }
          >
            {isExecuting ? "발주 중..." : `${approvedItems.length}건 발주`}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
