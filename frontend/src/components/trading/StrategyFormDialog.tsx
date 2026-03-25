"use client";

import { useEffect } from "react";
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
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { toNumber as toNum } from "@/lib/form-utils";
import type {
  StrategyType,
  TradingStrategy,
  TradingStrategyCreateRequest,
  TradingStrategyUpdateRequest,
} from "@/types/trading";
import { strategyTypeLabels } from "@/types/trading";

const DEFAULT_PARAMS: Record<StrategyType, Record<string, number>> = {
  ma_crossover: { fast_period: 5, slow_period: 20, rsi_period: 14, rsi_overbought: 70, rsi_oversold: 30 },
  mean_reversion: { lookback: 20, std_multiplier: 2, rsi_period: 14 },
  custom: {},
};

interface StrategyFormValues {
  name: string;
  strategy_type: StrategyType;
  target_tickers: string;
  interval_minutes: number | undefined;
  market_hours_only: boolean;
}

const schema = z.object({
  name: z.string().min(1, "전략명을 입력해주세요").max(100),
  strategy_type: z.enum(["ma_crossover", "mean_reversion", "custom"]),
  target_tickers: z.string().min(1, "대상 종목을 입력해주세요"),
  interval_minutes: z.preprocess(
    toNum,
    z.number({ message: "숫자를 입력해주세요" }).int().min(1).max(60),
  ),
  market_hours_only: z.boolean(),
});

interface StrategyFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accountId: string;
  editingStrategy?: TradingStrategy | null;
  onSubmitCreate: (data: TradingStrategyCreateRequest) => Promise<void>;
  onSubmitUpdate: (id: string, data: TradingStrategyUpdateRequest) => Promise<void>;
  isSubmitting: boolean;
}

export function StrategyFormDialog({
  open,
  onOpenChange,
  accountId,
  editingStrategy,
  onSubmitCreate,
  onSubmitUpdate,
  isSubmitting,
}: StrategyFormDialogProps) {
  const isEditing = !!editingStrategy;

  const form = useForm<StrategyFormValues>({
    resolver: zodResolver(schema) as Resolver<StrategyFormValues>,
    defaultValues: {
      name: "",
      strategy_type: "ma_crossover",
      target_tickers: "",
      interval_minutes: 10,
      market_hours_only: true,
    },
  });

  useEffect(() => {
    if (editingStrategy) {
      form.reset({
        name: editingStrategy.name,
        strategy_type: editingStrategy.strategyType,
        target_tickers: editingStrategy.targetTickers.join(", "),
        interval_minutes: editingStrategy.intervalMinutes,
        market_hours_only: editingStrategy.marketHoursOnly,
      });
    } else {
      form.reset({
        name: "",
        strategy_type: "ma_crossover",
        target_tickers: "",
        interval_minutes: 10,
        market_hours_only: true,
      });
    }
  }, [editingStrategy, form, open]);

  const handleSubmit = form.handleSubmit(async (values) => {
    const tickers = values.target_tickers
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    if (isEditing && editingStrategy) {
      await onSubmitUpdate(editingStrategy.id, {
        name: values.name,
        target_tickers: tickers,
        interval_minutes: values.interval_minutes!,
        market_hours_only: values.market_hours_only,
      });
    } else {
      await onSubmitCreate({
        account_id: accountId,
        name: values.name,
        strategy_type: values.strategy_type,
        params_json: DEFAULT_PARAMS[values.strategy_type],
        target_tickers: tickers,
        interval_minutes: values.interval_minutes!,
        market_hours_only: values.market_hours_only,
      });
    }
  });

  const watchType = form.watch("strategy_type");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? "전략 수정" : "전략 생성"}</DialogTitle>
          <DialogDescription>
            자동매매 전략을 설정합니다.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="name">전략명</Label>
            <Input id="name" placeholder="예: 삼성전자 골든크로스" {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
            )}
          </div>

          <div className="grid gap-1.5">
            <Label>전략 유형</Label>
            <Select
              value={watchType}
              onValueChange={(val) => {
                if (val) form.setValue("strategy_type", val as StrategyType);
              }}
              disabled={isEditing}
            >
              <SelectTrigger className="w-full">
                <span>{strategyTypeLabels[watchType]}</span>
              </SelectTrigger>
              <SelectContent>
                {Object.entries(strategyTypeLabels).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="target_tickers">대상 종목 (쉼표 구분)</Label>
            <Input
              id="target_tickers"
              placeholder="005930, 000660, 035720"
              {...form.register("target_tickers")}
            />
            {form.formState.errors.target_tickers && (
              <p className="text-xs text-destructive">
                {form.formState.errors.target_tickers.message}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="interval_minutes">실행 간격 (분)</Label>
              <Input
                id="interval_minutes"
                type="number"
                min={1}
                max={60}
                {...form.register("interval_minutes")}
              />
              {form.formState.errors.interval_minutes && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.interval_minutes.message}
                </p>
              )}
            </div>
            <div className="flex items-end gap-2 pb-0.5">
              <input
                id="market_hours_only"
                type="checkbox"
                className="size-4 rounded border-border"
                {...form.register("market_hours_only")}
              />
              <Label htmlFor="market_hours_only" className="text-sm">
                장중에만 실행
              </Label>
            </div>
          </div>

          {!isEditing && (
            <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
              <p className="font-medium mb-1">기본 파라미터 ({strategyTypeLabels[watchType]})</p>
              {Object.entries(DEFAULT_PARAMS[watchType]).map(([key, val]) => (
                <span key={key} className="mr-3">
                  {key}: {val}
                </span>
              ))}
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
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "처리 중..." : isEditing ? "수정" : "생성"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
