"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { TickerCombobox } from "@/components/common/TickerCombobox";
import { MARKETS, type MarketType, type WatchlistItem } from "@/types";
import { toNumber } from "@/lib/form-utils";

const watchlistSchema = z.object({
  ticker: z.string().trim().min(1, "종목코드를 입력해주세요").max(20),
  market: z.enum(MARKETS),
  targetBuyPrice: z.number().positive().optional(),
  targetSellPrice: z.number().positive().optional(),
  alertThresholdPct: z.number().min(0).max(100).optional(),
  notes: z.string().max(500).optional(),
});

type WatchlistFormValues = z.infer<typeof watchlistSchema>;

interface WatchlistAddDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingItem: WatchlistItem | null;
  onSubmit: (values: WatchlistFormValues) => Promise<void>;
  isSubmitting: boolean;
}

export type { WatchlistFormValues };

export function WatchlistAddDialog({
  open,
  onOpenChange,
  editingItem,
  onSubmit,
  isSubmitting,
}: WatchlistAddDialogProps) {
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<WatchlistFormValues>({
    resolver: zodResolver(watchlistSchema),
    defaultValues: {
      ticker: "",
      market: MARKETS[0],
      notes: "",
    },
  });

  const marketValue = watch("market");

  useEffect(() => {
    if (open) {
      if (editingItem) {
        reset({
          ticker: editingItem.ticker,
          market: editingItem.market as MarketType,
          targetBuyPrice: editingItem.targetBuyPrice ?? undefined,
          targetSellPrice: editingItem.targetSellPrice ?? undefined,
          alertThresholdPct: editingItem.alertThresholdPct ?? undefined,
          notes: editingItem.notes ?? "",
        });
      } else {
        reset({
          ticker: "",
          market: MARKETS[0],
          notes: "",
        });
      }
    }
  }, [open, editingItem, reset]);

  const handleFormSubmit = handleSubmit(async (values) => {
    await onSubmit(values);
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{editingItem ? "관심종목 수정" : "관심종목 추가"}</DialogTitle>
          <DialogDescription>
            {editingItem
              ? "관심종목 정보를 수정합니다."
              : "관심 있는 종목을 등록하고 알림을 설정하세요."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleFormSubmit} className="space-y-4">
          {/* 종목코드 + 시장 */}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="ticker">종목코드</Label>
              {marketValue === "KRX" && !editingItem ? (
                <TickerCombobox
                  mode="single"
                  value={watch("ticker") || null}
                  onChange={(ticker) =>
                    setValue("ticker", ticker ?? "", { shouldValidate: true })
                  }
                  placeholder="종목명 또는 코드 검색 (예: 삼성전자)"
                />
              ) : (
                <Input
                  id="ticker"
                  placeholder={marketValue === "KRX" ? "005930" : "AAPL"}
                  disabled={!!editingItem}
                  {...register("ticker")}
                />
              )}
              {errors.ticker && (
                <p className="text-xs text-destructive">{errors.ticker.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>시장</Label>
              <Select
                value={marketValue}
                onValueChange={(v) => {
                  setValue("market", v as MarketType);
                  if (!editingItem) setValue("ticker", "");
                }}
                disabled={!!editingItem}
              >
                <SelectTrigger>
                  <span>{marketValue}</span>
                </SelectTrigger>
                <SelectContent>
                  {MARKETS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* 목표가 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="targetBuyPrice">목표 매수가</Label>
              <Input
                id="targetBuyPrice"
                type="number"
                step="any"
                placeholder="선택사항"
                {...register("targetBuyPrice", { setValueAs: toNumber })}
              />
              {errors.targetBuyPrice && (
                <p className="text-xs text-destructive">{errors.targetBuyPrice.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="targetSellPrice">목표 매도가</Label>
              <Input
                id="targetSellPrice"
                type="number"
                step="any"
                placeholder="선택사항"
                {...register("targetSellPrice", { setValueAs: toNumber })}
              />
              {errors.targetSellPrice && (
                <p className="text-xs text-destructive">{errors.targetSellPrice.message}</p>
              )}
            </div>
          </div>

          {/* 알림 기준 */}
          <div className="space-y-1.5">
            <Label htmlFor="alertThresholdPct">알림 기준 (%)</Label>
            <Input
              id="alertThresholdPct"
              type="number"
              step="0.1"
              placeholder="예: 5 (±5% 변동 시 알림)"
              {...register("alertThresholdPct", { setValueAs: toNumber })}
            />
            {errors.alertThresholdPct && (
              <p className="text-xs text-destructive">{errors.alertThresholdPct.message}</p>
            )}
          </div>

          {/* 메모 */}
          <div className="space-y-1.5">
            <Label htmlFor="notes">메모</Label>
            <Textarea
              id="notes"
              placeholder="투자 아이디어, 관심 이유 등"
              rows={3}
              {...register("notes")}
            />
            {errors.notes && (
              <p className="text-xs text-destructive">{errors.notes.message}</p>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              취소
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "저장 중..." : editingItem ? "수정" : "추가"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
