"use client";

import { useState } from "react";
import { useForm, type Resolver } from "react-hook-form";
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
import type { Asset } from "@/types";
import { formatAmount } from "@/lib/format";

const toNumber = (val: unknown) => {
  if (val === "" || val === undefined || val === null) return undefined;
  const n = Number(val);
  return isNaN(n) ? val : n;
};

const sellSchema = z.object({
  sold_price: z.preprocess(toNumber, z.number({ message: "매도가를 입력해주세요" }).min(0, "매도가는 0 이상이어야 합니다")),
});

interface SellFormValues {
  sold_price: number;
}

interface SellDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  asset: Asset | null;
  onSubmit: (assetId: string, soldPrice: number) => Promise<void>;
}

export function SellDialog({ open, onOpenChange, asset, onSubmit }: SellDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const form = useForm<SellFormValues>({
    resolver: zodResolver(sellSchema) as Resolver<SellFormValues>,
    defaultValues: { sold_price: undefined as unknown as number },
  });

  const watchPrice = form.watch("sold_price");

  // 예상 손익 계산
  const estimatedPnl =
    asset && watchPrice != null && !isNaN(watchPrice)
      ? (watchPrice - asset.purchasePrice) * asset.quantity
      : null;

  const handleSubmit = form.handleSubmit(async (values) => {
    if (!asset) return;
    setIsSubmitting(true);
    try {
      await onSubmit(asset.id, values.sold_price);
      form.reset();
      onOpenChange(false);
    } finally {
      setIsSubmitting(false);
    }
  });

  if (!asset) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>매도 처리</DialogTitle>
          <DialogDescription>
            <span className="font-medium text-foreground">{asset.name}</span>을(를) 매도합니다.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg bg-muted/50 p-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">보유 수량</span>
            <span>{asset.quantity.toLocaleString("ko-KR")}</span>
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-muted-foreground">매입가</span>
            <span>{formatAmount(asset.purchasePrice, asset.currency, false)}</span>
          </div>
          {asset.currentPrice != null && (
            <div className="flex justify-between mt-1">
              <span className="text-muted-foreground">현재가</span>
              <span>{formatAmount(asset.currentPrice, asset.currency, false)}</span>
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="sold_price">매도가</Label>
            <Input
              id="sold_price"
              type="number"
              step="any"
              placeholder="매도 단가를 입력하세요"
              {...form.register("sold_price")}
            />
            {form.formState.errors.sold_price && (
              <p className="text-xs text-destructive">
                {form.formState.errors.sold_price.message}
              </p>
            )}
          </div>

          {/* 예상 손익 */}
          {estimatedPnl !== null && (
            <div className="rounded-lg border p-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">예상 실현 손익</span>
                <span
                  className={
                    estimatedPnl >= 0 ? "text-emerald-500 font-medium" : "text-red-500 font-medium"
                  }
                >
                  {estimatedPnl >= 0 ? "+" : ""}
                  {formatAmount(estimatedPnl, asset.currency, false)}
                </span>
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-muted-foreground">매도 대금</span>
                <span>
                  {formatAmount(watchPrice * asset.quantity, asset.currency, false)}
                </span>
              </div>
            </div>
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
            <Button type="submit" disabled={isSubmitting} variant="destructive">
              {isSubmitting ? "처리 중..." : "매도 확정"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
