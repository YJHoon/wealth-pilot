"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import type {
  AccountDepositRequest,
  DepositAllocationMode,
  TradingAccount,
  TradingStrategy,
} from "@/types/trading";

interface DepositDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: TradingAccount | null;
  strategies: TradingStrategy[];
  onSubmit: (data: AccountDepositRequest) => Promise<void>;
  isSubmitting: boolean;
}

const MODE_LABELS: Record<DepositAllocationMode, string> = {
  manual: "수동 배분",
  pro_rata: "비율 자동 분배",
  reserve: "계좌 총액만 증액",
};

const MODE_DESC: Record<DepositAllocationMode, string> = {
  manual: "전략별 추가 금액을 직접 입력합니다. 합계 = 입금액.",
  pro_rata: "기존 전략의 할당 자본 비율에 맞춰 자동 분배합니다.",
  reserve: "전략에 배분하지 않고 계좌 총액만 늘립니다. 이후 재배분으로 분배하세요.",
};

export function DepositDialog({
  open,
  onOpenChange,
  account,
  strategies,
  onSubmit,
  isSubmitting,
}: DepositDialogProps) {
  const [amountStr, setAmountStr] = useState<string>("");
  const [mode, setMode] = useState<DepositAllocationMode>("pro_rata");
  const [manualAlloc, setManualAlloc] = useState<Record<string, string>>({});

  // 다이얼로그가 열려 있는 동안 부모가 strategies를 refetch해도 입력 상태가
  // 초기화되지 않도록, 초기화는 open이 false → true로 바뀔 때만 수행한다.
  // 초기화 시점의 전략 스냅샷을 읽기 위해 ref로 최신값을 추적한다.
  const strategiesRef = useRef(strategies);
  strategiesRef.current = strategies;

  useEffect(() => {
    if (open) {
      const snapshot = strategiesRef.current;
      setAmountStr("");
      setMode(snapshot.length > 0 ? "pro_rata" : "reserve");
      const init: Record<string, string> = {};
      for (const s of snapshot) init[s.id] = "";
      setManualAlloc(init);
    }
  }, [open]);

  const amount = Number(amountStr) || 0;

  const manualTotal = useMemo(() => {
    return Object.values(manualAlloc).reduce((sum, v) => {
      const n = Number(v);
      return sum + (Number.isFinite(n) ? n : 0);
    }, 0);
  }, [manualAlloc]);

  const manualMismatch = mode === "manual" && amount > 0 && manualTotal !== amount;
  const proRataInvalid =
    mode === "pro_rata" &&
    (strategies.length === 0 ||
      strategies.reduce((s, st) => s + (st.initialCapital ?? 0), 0) <= 0);

  const canSubmit =
    !!account &&
    amount > 0 &&
    !manualMismatch &&
    !(mode === "pro_rata" && proRataInvalid) &&
    !(mode === "manual" && strategies.length === 0);

  const handleManualChange = (strategyId: string, v: string) => {
    setManualAlloc((prev) => ({ ...prev, [strategyId]: v }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const payload: AccountDepositRequest = { amount, mode };
    if (mode === "manual") {
      payload.allocations = Object.entries(manualAlloc).map(([strategy_id, v]) => ({
        strategy_id,
        amount: Number(v) || 0,
      }));
    }
    await onSubmit(payload);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>신규 입금 반영</DialogTitle>
          <DialogDescription>
            계좌에 추가 자본을 반영하고 전략에 할당합니다. 기존 실현 손익은 유지됩니다.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="deposit-amount">입금액 (원)</Label>
            <Input
              id="deposit-amount"
              type="number"
              min={0}
              step="1"
              value={amountStr}
              onChange={(e) => setAmountStr(e.target.value)}
              placeholder="예: 1000000"
            />
          </div>

          <div className="grid gap-1.5">
            <Label>할당 방식</Label>
            <Select
              value={mode}
              onValueChange={(val) => {
                if (val) setMode(val as DepositAllocationMode);
              }}
            >
              <SelectTrigger className="w-full">
                <span>{MODE_LABELS[mode]}</span>
              </SelectTrigger>
              <SelectContent>
                {Object.entries(MODE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{MODE_DESC[mode]}</p>
          </div>

          {mode === "manual" && strategies.length > 0 && (
            <div className="grid gap-2 max-h-48 overflow-y-auto">
              {strategies.map((s) => (
                <div key={s.id} className="grid grid-cols-[1fr_140px] items-center gap-2">
                  <Label htmlFor={`dep-${s.id}`} className="text-sm truncate">
                    {s.name}
                  </Label>
                  <Input
                    id={`dep-${s.id}`}
                    type="number"
                    min={0}
                    step="1"
                    value={manualAlloc[s.id] ?? ""}
                    onChange={(e) => handleManualChange(s.id, e.target.value)}
                    placeholder="0"
                  />
                </div>
              ))}
              <div className="flex items-center justify-between text-xs border-t border-border pt-2">
                <span className="text-muted-foreground">할당 합계</span>
                <span className={manualMismatch ? "text-destructive font-medium" : "font-medium"}>
                  {manualTotal.toLocaleString()}원
                </span>
              </div>
              {manualMismatch && (
                <p className="text-xs text-destructive">
                  합계({manualTotal.toLocaleString()}원)가 입금액({amount.toLocaleString()}원)과 달라요.
                </p>
              )}
            </div>
          )}

          {mode === "pro_rata" && proRataInvalid && (
            <p className="text-xs text-destructive">
              모든 전략의 할당 자본이 0이라 비율 분배가 불가합니다. 수동 배분을 이용하세요.
            </p>
          )}

          {mode === "manual" && strategies.length === 0 && (
            <p className="text-xs text-destructive">활성 전략이 없어 수동 배분이 불가합니다.</p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              취소
            </Button>
            <Button type="submit" disabled={isSubmitting || !canSubmit}>
              {isSubmitting ? "처리 중..." : "입금 반영"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
