"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  AccountRebalanceRequest,
  TradingAccount,
  TradingStrategy,
} from "@/types/trading";

interface RebalanceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: TradingAccount | null;
  strategies: TradingStrategy[];
  onSubmit: (data: AccountRebalanceRequest) => Promise<void>;
  isSubmitting: boolean;
}

export function RebalanceDialog({
  open,
  onOpenChange,
  account,
  strategies,
  onSubmit,
  isSubmitting,
}: RebalanceDialogProps) {
  const [allocations, setAllocations] = useState<Record<string, string>>({});

  useEffect(() => {
    if (open) {
      const init: Record<string, string> = {};
      for (const s of strategies) {
        init[s.id] = String(Math.floor(s.initialCapital ?? 0));
      }
      setAllocations(init);
    }
  }, [open, strategies]);

  const accountTotal = account?.initialCapital ?? 0;

  const totalAllocated = useMemo(() => {
    return Object.values(allocations).reduce((sum, v) => {
      const n = Number(v);
      return sum + (Number.isFinite(n) ? n : 0);
    }, 0);
  }, [allocations]);

  const remaining = accountTotal - totalAllocated;
  const isExceeded = totalAllocated > accountTotal;

  const handleChange = (strategyId: string, value: string) => {
    setAllocations((prev) => ({ ...prev, [strategyId]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!account || isExceeded) return;
    const items = Object.entries(allocations).map(([strategy_id, v]) => ({
      strategy_id,
      initial_capital: Number(v) || 0,
    }));
    await onSubmit({ allocations: items });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>전략 자본 재배분</DialogTitle>
          <DialogDescription>
            계좌 내 활성 전략들의 할당 자본을 일괄 조정합니다.
            과거 실현 손익(realized_pnl)은 그대로 유지됩니다.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="flex items-center justify-between rounded-md bg-muted p-3 text-xs">
            <span className="text-muted-foreground">계좌 총 자본</span>
            <span className="font-medium">{accountTotal.toLocaleString()}원</span>
          </div>

          {strategies.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              재배분할 활성 전략이 없습니다.
            </p>
          ) : (
            <div className="grid gap-2 max-h-64 overflow-y-auto">
              {strategies.map((s) => (
                <div key={s.id} className="grid grid-cols-[1fr_140px] items-center gap-2">
                  <Label htmlFor={`alloc-${s.id}`} className="text-sm truncate">
                    {s.name}
                  </Label>
                  <Input
                    id={`alloc-${s.id}`}
                    type="number"
                    min={0}
                    step="1"
                    value={allocations[s.id] ?? ""}
                    onChange={(e) => handleChange(s.id, e.target.value)}
                    placeholder="0"
                  />
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-1 rounded-md border border-border p-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">할당 합계</span>
              <span className={isExceeded ? "text-destructive font-medium" : "font-medium"}>
                {totalAllocated.toLocaleString()}원
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">잔여</span>
              <span className={remaining < 0 ? "text-destructive font-medium" : "font-medium"}>
                {remaining.toLocaleString()}원
              </span>
            </div>
            {isExceeded && (
              <p className="text-destructive mt-1">
                할당 합계가 계좌 총 자본을 초과했습니다.
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              취소
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting || isExceeded || strategies.length === 0}
            >
              {isSubmitting ? "처리 중..." : "재배분 실행"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
