"use client";

import { useEffect, useState, useCallback } from "react";
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
  AutoTickerPreviewResponse,
  AutoTickerSelectionHistory,
  StrategyType,
  TradingStrategy,
  TradingStrategyCreateRequest,
  TradingStrategyUpdateRequest,
} from "@/types/trading";
import { strategyTypeLabels } from "@/types/trading";

const MAX_TICKERS = 50;
const MAX_BLACKLIST = 50;

const DEFAULT_PARAMS: Record<StrategyType, Record<string, number>> = {
  ma_crossover: { fast_period: 5, slow_period: 20, rsi_period: 14, rsi_overbought: 70, rsi_oversold: 30 },
  mean_reversion: { lookback: 20, std_multiplier: 2, rsi_period: 14 },
  custom: {},
};

const DEFAULT_AUTO_SELECT = {
  enabled: false,
  top_n: 10,
  market: "ALL" as const,
  min_volume_value: 10_000_000_000,
  blacklist: [] as string[],
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
  target_tickers: z
    .array(z.string().regex(/^\d{6}$/, "6자리 종목코드만 허용됩니다"))
    .max(MAX_TICKERS, `종목은 최대 ${MAX_TICKERS}개까지 선택할 수 있습니다`),
  auto_enabled: z.boolean(),
  auto_top_n: z.preprocess(
    toNum,
    z.number({ message: "숫자를 입력해주세요" }).int().min(3).max(30),
  ),
  auto_market: z.enum(["KOSPI", "KOSDAQ", "ALL"]),
  auto_min_volume_value: z.preprocess(
    toNum,
    z.number({ message: "숫자를 입력해주세요" }).int().min(0),
  ),
  auto_blacklist: z
    .array(z.string().regex(/^\d{6}$/, "6자리 종목코드만 허용됩니다"))
    .max(MAX_BLACKLIST, `제외 종목은 최대 ${MAX_BLACKLIST}개까지 선택할 수 있습니다`),
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
  // 자동 선정 (편집 모드 전용 — 저장된 전략에서만 호출 가능)
  onPreviewAuto?: (strategyId: string) => Promise<AutoTickerPreviewResponse>;
  onRefreshAuto?: (strategyId: string) => Promise<TradingStrategy>;
  onLoadAutoHistory?: (strategyId: string) => Promise<AutoTickerSelectionHistory[]>;
}

const MARKET_LABELS: Record<"KOSPI" | "KOSDAQ" | "ALL", string> = {
  KOSPI: "코스피",
  KOSDAQ: "코스닥",
  ALL: "전체",
};

export function StrategyFormDialog({
  open,
  onOpenChange,
  accountId,
  editingStrategy,
  onSubmitCreate,
  onSubmitUpdate,
  isSubmitting,
  onPreviewAuto,
  onRefreshAuto,
  onLoadAutoHistory,
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
      auto_enabled: DEFAULT_AUTO_SELECT.enabled,
      auto_top_n: DEFAULT_AUTO_SELECT.top_n,
      auto_market: DEFAULT_AUTO_SELECT.market,
      auto_min_volume_value: DEFAULT_AUTO_SELECT.min_volume_value,
      auto_blacklist: DEFAULT_AUTO_SELECT.blacklist,
    },
  });

  useEffect(() => {
    if (editingStrategy) {
      const auto = editingStrategy.autoSelectConfig;
      form.reset({
        name: editingStrategy.name,
        strategy_type: editingStrategy.strategyType,
        interval_minutes: editingStrategy.intervalMinutes,
        market_hours_only: editingStrategy.marketHoursOnly,
        priority: editingStrategy.priority ?? 0,
        target_tickers: editingStrategy.targetTickers,
        auto_enabled: auto.enabled,
        auto_top_n: auto.topN,
        auto_market: auto.market,
        auto_min_volume_value: auto.minVolumeValue,
        auto_blacklist: auto.blacklist,
      });
    } else {
      form.reset({
        name: "",
        strategy_type: "ma_crossover",
        interval_minutes: 10,
        market_hours_only: true,
        priority: 0,
        target_tickers: [],
        auto_enabled: DEFAULT_AUTO_SELECT.enabled,
        auto_top_n: DEFAULT_AUTO_SELECT.top_n,
        auto_market: DEFAULT_AUTO_SELECT.market,
        auto_min_volume_value: DEFAULT_AUTO_SELECT.min_volume_value,
        auto_blacklist: DEFAULT_AUTO_SELECT.blacklist,
      });
    }
  }, [editingStrategy, form, open]);

  const handleSubmit = form.handleSubmit(async (values) => {
    const autoSelect = {
      enabled: values.auto_enabled,
      top_n: values.auto_top_n,
      market: values.auto_market,
      min_volume_value: values.auto_min_volume_value,
      blacklist: values.auto_blacklist,
    };
    if (isEditing && editingStrategy) {
      await onSubmitUpdate(editingStrategy.id, {
        name: values.name,
        target_tickers: values.target_tickers,
        interval_minutes: values.interval_minutes,
        market_hours_only: values.market_hours_only,
        priority: values.priority,
        auto_select_config: autoSelect,
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
        auto_select_config: autoSelect,
      });
    }
  });

  const watchType = form.watch("strategy_type");
  const watchAutoEnabled = form.watch("auto_enabled");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? "전략 수정" : "전략 생성"}</DialogTitle>
          <DialogDescription>
            자동매매 전략을 설정합니다. 감시할 종목을 직접 선택하거나 자동 선정을 켜주세요.
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
            <Label>감시 종목 (수동)</Label>
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
              종목명으로 검색해 추가하세요. 자동 선정과 함께 사용 가능합니다. (최대 {MAX_TICKERS}개)
            </p>
            {form.formState.errors.target_tickers && (
              <p className="text-xs text-destructive">
                {form.formState.errors.target_tickers.message}
              </p>
            )}
          </div>

          {/* ── 자동 종목 선정 ── */}
          <div className="rounded-md border border-border p-3 grid gap-3">
            <div className="flex items-center gap-2">
              <input
                id="auto_enabled"
                type="checkbox"
                className="size-4 rounded border-border"
                {...form.register("auto_enabled")}
              />
              <Label htmlFor="auto_enabled" className="text-sm font-medium">
                자동 종목 선정 활성화 (거래대금 상위 N)
              </Label>
            </div>
            {watchAutoEnabled && (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <div className="grid gap-1.5">
                    <Label htmlFor="auto_top_n">상위 N개 (3~30)</Label>
                    <Input
                      id="auto_top_n"
                      type="number"
                      min={3}
                      max={30}
                      {...form.register("auto_top_n")}
                    />
                    {form.formState.errors.auto_top_n && (
                      <p className="text-xs text-destructive">
                        {form.formState.errors.auto_top_n.message}
                      </p>
                    )}
                  </div>
                  <div className="grid gap-1.5">
                    <Label>시장</Label>
                    <Controller
                      control={form.control}
                      name="auto_market"
                      render={({ field }) => (
                        <Select
                          value={field.value}
                          onValueChange={(val) =>
                            val && field.onChange(val as "KOSPI" | "KOSDAQ" | "ALL")
                          }
                        >
                          <SelectTrigger className="w-full">
                            <span>{MARKET_LABELS[field.value]}</span>
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(MARKET_LABELS).map(([value, label]) => (
                              <SelectItem key={value} value={value}>
                                {label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="auto_min_volume_value">최소 거래대금 (원)</Label>
                    <Input
                      id="auto_min_volume_value"
                      type="number"
                      min={0}
                      step={1_000_000_000}
                      {...form.register("auto_min_volume_value")}
                    />
                    {form.formState.errors.auto_min_volume_value && (
                      <p className="text-xs text-destructive">
                        {form.formState.errors.auto_min_volume_value.message}
                      </p>
                    )}
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <Label>제외 종목 (블랙리스트)</Label>
                  <Controller
                    control={form.control}
                    name="auto_blacklist"
                    render={({ field }) => (
                      <TickerCombobox
                        mode="multiple"
                        value={field.value}
                        onChange={field.onChange}
                        max={MAX_BLACKLIST}
                        placeholder="자동 선정에서 제외할 종목 검색"
                      />
                    )}
                  />
                  {form.formState.errors.auto_blacklist && (
                    <p className="text-xs text-destructive">
                      {form.formState.errors.auto_blacklist.message}
                    </p>
                  )}
                </div>
              </>
            )}
            <p className="text-xs text-muted-foreground">
              매일 08:30에 거래대금 상위 종목을 자동 선정합니다. 수동 종목 + 자동 선정 + 보유
              포지션을 모두 평가합니다.
            </p>
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

        {/* ── 편집 모드 전용: 미리보기 / 수동 갱신 / 이력 ── */}
        {isEditing && editingStrategy && (
          <AutoTickerPanel
            strategy={editingStrategy}
            onPreview={onPreviewAuto}
            onRefresh={onRefreshAuto}
            onLoadHistory={onLoadAutoHistory}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface AutoTickerPanelProps {
  strategy: TradingStrategy;
  onPreview?: (id: string) => Promise<AutoTickerPreviewResponse>;
  onRefresh?: (id: string) => Promise<TradingStrategy>;
  onLoadHistory?: (id: string) => Promise<AutoTickerSelectionHistory[]>;
}

function AutoTickerPanel({
  strategy,
  onPreview,
  onRefresh,
  onLoadHistory,
}: AutoTickerPanelProps) {
  const [busy, setBusy] = useState<"preview" | "refresh" | "history" | null>(null);
  const [preview, setPreview] = useState<AutoTickerPreviewResponse | null>(null);
  const [history, setHistory] = useState<AutoTickerSelectionHistory[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enabled = strategy.autoSelectConfig.enabled;
  const last = strategy.autoSelectedTickers;

  const handlePreview = useCallback(async () => {
    if (!onPreview) return;
    setBusy("preview");
    setError(null);
    try {
      const r = await onPreview(strategy.id);
      setPreview(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "미리보기 실패");
    } finally {
      setBusy(null);
    }
  }, [onPreview, strategy.id]);

  const handleRefresh = useCallback(async () => {
    if (!onRefresh) return;
    setBusy("refresh");
    setError(null);
    try {
      await onRefresh(strategy.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "갱신 실패");
    } finally {
      setBusy(null);
    }
  }, [onRefresh, strategy.id]);

  const handleHistory = useCallback(async () => {
    if (!onLoadHistory) return;
    setBusy("history");
    setError(null);
    try {
      const r = await onLoadHistory(strategy.id);
      setHistory(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "이력 로드 실패");
    } finally {
      setBusy(null);
    }
  }, [onLoadHistory, strategy.id]);

  return (
    <div className="mt-4 rounded-md border border-border p-3 grid gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">자동 선정 결과</p>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handlePreview}
            disabled={busy !== null}
          >
            {busy === "preview" ? "..." : "미리보기"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={busy !== null || !enabled}
          >
            {busy === "refresh" ? "..." : "지금 갱신"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleHistory}
            disabled={busy !== null}
          >
            {busy === "history" ? "..." : "이력"}
          </Button>
        </div>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {last ? (
        <div className="text-xs">
          <p className="text-muted-foreground">
            마지막 갱신: {new Date(last.generatedAt).toLocaleString("ko-KR")} (
            {last.ruleVersion})
          </p>
          <p className="mt-1">
            현재 자동 선정 종목 ({last.tickers.length}개):{" "}
            <span className="font-mono">{last.tickers.join(", ") || "없음"}</span>
          </p>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          아직 자동 선정 결과가 없습니다. 활성화한 뒤 미리보기 또는 지금 갱신을 눌러보세요.
        </p>
      )}

      {preview && (
        <div className="text-xs grid gap-1">
          <p className="font-medium">미리보기 ({preview.ruleVersion})</p>
          <p className="text-muted-foreground">
            가용 현금 {Math.round(preview.availableCash).toLocaleString()}원 / 평가액{" "}
            {Math.round(preview.totalEval).toLocaleString()}원 / 비중한도{" "}
            {(preview.maxPositionPct * 100).toFixed(0)}%
          </p>
          <ul className="list-disc pl-4 space-y-0.5">
            {preview.selected.map((s, i) => (
              <li key={i}>
                <span className="font-mono">{String(s.ticker)}</span> {String(s.name)} —{" "}
                {String(s.reason)}
              </li>
            ))}
            {preview.selected.length === 0 && (
              <li className="text-muted-foreground">선정된 종목이 없습니다 (필터를 완화해보세요)</li>
            )}
          </ul>
        </div>
      )}

      {history && (
        <div className="text-xs grid gap-1">
          <p className="font-medium">이력 ({history.length}건)</p>
          <ul className="space-y-1 max-h-48 overflow-y-auto">
            {history.map((h) => (
              <li key={h.id} className="border-b border-border/50 pb-1">
                <span className="text-muted-foreground">
                  {new Date(h.generatedAt).toLocaleString("ko-KR")}
                </span>{" "}
                <span className="font-mono">[{h.triggeredBy}]</span> ({h.selectedTickers.length}개)
              </li>
            ))}
            {history.length === 0 && <li className="text-muted-foreground">이력 없음</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
