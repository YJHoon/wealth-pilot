"use client";

import { useEffect } from "react";
import { useForm, Controller, type Resolver } from "react-hook-form";
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
import { TickerCombobox } from "@/components/common/TickerCombobox";
import { toNumber as toNum } from "@/lib/form-utils";
import type {
  StrategyType,
  TradingStrategy,
  TradingStrategyCreateRequest,
  TradingStrategyUpdateRequest,
} from "@/types/trading";
import { strategyTypeLabels } from "@/types/trading";

const MAX_TICKERS = 50;

const DEFAULT_PARAMS: Record<StrategyType, Record<string, number>> = {
  ma_crossover: { fast_period: 5, slow_period: 20, rsi_period: 14, rsi_overbought: 70, rsi_oversold: 30 },
  mean_reversion: { lookback: 20, std_multiplier: 2, rsi_period: 14 },
  custom: {},
};

const schema = z.object({
  name: z.string().min(1, "전략명을 입력해주세요").max(100),
  strategy_type: z.enum(["ma_crossover", "mean_reversion", "custom"]),
  interval_minutes: z.preprocess(
    toNum,
    z.number({ message: "숫자를 입력해주세요" }).int().min(1).max(60),
  ),
  market_hours_only: z.boolean(),
  priority: z.preprocess(
    toNum,
    z.number({ message: "숫자를 입력해주세요" }).int().min(0).max(100),
  ),
  // 콤보박스에서 선택된 6자리 종목코드 리스트. 빈 배열 허용(종목 없는 전략).
  target_tickers: z
    .array(z.string().regex(/^\d{6}$/, "6자리 종목코드만 허용됩니다"))
    .max(MAX_TICKERS, `종목은 최대 ${MAX_TICKERS}개까지 선택할 수 있습니다`),
});

type StrategyFormValues = z.output<typeof schema>;

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
      interval_minutes: 10,
      market_hours_only: true,
      priority: 0,
      target_tickers: [],
    },
  });

  useEffect(() => {
    if (editingStrategy) {
      form.reset({
        name: editingStrategy.name,
        strategy_type: editingStrategy.strategyType,
        interval_minutes: editingStrategy.intervalMinutes,
        market_hours_only: editingStrategy.marketHoursOnly,
        priority: editingStrategy.priority ?? 0,
        target_tickers: editingStrategy.targetTickers,
      });
    } else {
      form.reset({
        name: "",
        strategy_type: "ma_crossover",
        interval_minutes: 10,
        market_hours_only: true,
        priority: 0,
        target_tickers: [],
      });
    }
  }, [editingStrategy, form, open]);

  const handleSubmit = form.handleSubmit(async (values) => {
    if (isEditing && editingStrategy) {
      await onSubmitUpdate(editingStrategy.id, {
        name: values.name,
        target_tickers: values.target_tickers,
        interval_minutes: values.interval_minutes,
        market_hours_only: values.market_hours_only,
        priority: values.priority,
      });
    } else {
      await onSubmitCreate({
        account_id: accountId,
        name: values.name,
        strategy_type: values.strategy_type,
        params_json: DEFAULT_PARAMS[values.strategy_type],
        target_tickers: values.target_tickers,
        interval_minutes: values.interval_minutes,
        market_hours_only: values.market_hours_only,
        priority: values.priority,
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
            자동매매 전략을 설정합니다. 감시할 종목코드를 직접 지정하세요.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="name">전략명</Label>
            <Input id="name" placeholder="예: 골든크로스 자동매매" {...form.register("name")} />
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

          <div className="grid gap-1.5">
            <Label htmlFor="priority">우선순위 (0~100, 높을수록 우선)</Label>
            <Input
              id="priority"
              type="number"
              min={0}
              max={100}
              {...form.register("priority")}
            />
            {form.formState.errors.priority && (
              <p className="text-xs text-destructive">
                {form.formState.errors.priority.message}
              </p>
            )}
          </div>

          <div className="grid gap-1.5">
            <Label>감시 종목</Label>
            <Controller
              control={form.control}
              name="target_tickers"
              render={({ field }) => (
                <TickerCombobox
                  mode="multiple"
                  value={field.value}
                  onChange={field.onChange}
                  max={MAX_TICKERS}
                  placeholder="종목명 또는 코드 검색 (예: 삼성전자)"
                />
              )}
            />
            <p className="text-xs text-muted-foreground">
              종목명으로 검색해 추가하세요. 비워두면 매매하지 않습니다. (최대 {MAX_TICKERS}개)
            </p>
            {form.formState.errors.target_tickers && (
              <p className="text-xs text-destructive">
                {form.formState.errors.target_tickers.message}
              </p>
            )}
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
