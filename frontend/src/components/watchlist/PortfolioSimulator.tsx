"use client";

import { useState } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppStore } from "@/stores/appStore";
import { MASK, formatMaskedKrw } from "@/lib/format";
import { useSimulation } from "@/hooks/useSimulation";
import type { PortfolioSimulationResult } from "@/types";
import { toNumber } from "@/lib/form-utils";
import { Loader2, Plus, Trash2 } from "lucide-react";

const portfolioSchema = z.object({
  assets: z
    .array(
      z.object({
        ticker: z.string().min(1, "종목코드 필요"),
        weight: z.number().min(0).max(100),
      }),
    )
    .min(2, "최소 2개 종목이 필요합니다")
    .refine(
      (assets) => Math.abs(assets.reduce((sum, a) => sum + a.weight, 0) - 100) < 0.01,
      { message: "가중치 합계는 100이어야 합니다" },
    ),
  initialAmount: z.number({ error: "초기 투자금을 입력해주세요" }).positive(),
  months: z.number().int().min(1).max(120),
  rebalanceIntervalMonths: z.number().int().min(1).max(12).optional(),
});

type PortfolioFormValues = z.infer<typeof portfolioSchema>;

export function PortfolioSimulator() {
  const isMasked = useAppStore((s) => s.isMasked);
  const { result, loading, error, runSimulation, reset: resetSimulation } = useSimulation();
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<PortfolioFormValues>({
    resolver: zodResolver(portfolioSchema),
    defaultValues: {
      assets: [
        { ticker: "", weight: 50 },
        { ticker: "", weight: 50 },
      ],
      initialAmount: undefined,
      months: 12,
      rebalanceIntervalMonths: 3,
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "assets" });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitted(true);
    try {
      await runSimulation({
        type: "portfolio",
        tickers: values.assets.map((a) => a.ticker),
        weights: values.assets.map((a) => a.weight / 100),
        initialAmount: values.initialAmount,
        months: values.months,
        rebalanceIntervalMonths: values.rebalanceIntervalMonths,
      });
    } catch {
      // error handled by useSimulation
    }
  });

  const portfolioResult =
    result?.type === "portfolio" ? (result.result as PortfolioSimulationResult) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">포트폴리오 리밸런싱 시뮬레이터</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={onSubmit} className="space-y-3">
          {/* 종목 배분 */}
          <div className="space-y-2">
            <Label>종목 배분</Label>
            {fields.map((field, index) => (
              <div key={field.id} className="space-y-1">
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="종목코드"
                    className="flex-1"
                    {...register(`assets.${index}.ticker`)}
                  />
                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      className="w-20"
                      {...register(`assets.${index}.weight`, { setValueAs: toNumber })}
                    />
                    <span className="text-sm text-muted-foreground">%</span>
                  </div>
                  {fields.length > 2 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`종목 ${index + 1} 삭제`}
                      onClick={() => remove(index)}
                    >
                      <Trash2 className="size-3.5 text-destructive" />
                    </Button>
                  )}
                </div>
                {(errors.assets?.[index]?.ticker || errors.assets?.[index]?.weight) && (
                  <p className="text-xs text-destructive">
                    {errors.assets?.[index]?.ticker?.message || errors.assets?.[index]?.weight?.message}
                  </p>
                )}
              </div>
            ))}
            {errors.assets && (
              <p className="text-xs text-destructive">
                {errors.assets.root?.message || errors.assets.message}
              </p>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => append({ ticker: "", weight: 0 })}
            >
              <Plus className="mr-1 size-3.5" />
              종목 추가
            </Button>
          </div>

          {/* 설정 */}
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="pf-amount">초기 투자금(원)</Label>
              <Input
                id="pf-amount"
                type="number"
                placeholder="10000000"
                {...register("initialAmount", { setValueAs: toNumber })}
              />
              {errors.initialAmount && (
                <p className="text-xs text-destructive">{errors.initialAmount.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pf-months">기간(개월)</Label>
              <Input
                id="pf-months"
                type="number"
                {...register("months", { setValueAs: toNumber })}
              />
              {errors.months && (
                <p className="text-xs text-destructive">{errors.months.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pf-rebalance">리밸런싱 주기(월)</Label>
              <Input
                id="pf-rebalance"
                type="number"
                {...register("rebalanceIntervalMonths", { setValueAs: toNumber })}
              />
              {errors.rebalanceIntervalMonths && (
                <p className="text-xs text-destructive">{errors.rebalanceIntervalMonths.message}</p>
              )}
            </div>
          </div>

          <div className="flex gap-2">
            <Button type="submit" disabled={loading}>
              {loading ? <Loader2 className="mr-1 size-4 animate-spin" /> : null}
              시뮬레이션 실행
            </Button>
            {submitted && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  resetSimulation();
                  setSubmitted(false);
                }}
              >
                초기화
              </Button>
            )}
          </div>
        </form>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {portfolioResult && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-border p-3 text-center">
                <p className="text-xs text-muted-foreground">총 투자금</p>
                <p className="mt-1 text-lg font-semibold">
                  {isMasked ? `${MASK}원` : formatMaskedKrw(portfolioResult.totalInvested, false)}
                </p>
              </div>
              <div className="rounded-lg border border-border p-3 text-center">
                <p className="text-xs text-muted-foreground">최종 가치</p>
                <p className="mt-1 text-lg font-semibold">
                  {isMasked ? `${MASK}원` : formatMaskedKrw(portfolioResult.finalValue, false)}
                </p>
              </div>
              <div className="rounded-lg border border-border p-3 text-center">
                <p className="text-xs text-muted-foreground">수익률</p>
                <p
                  className={`mt-1 text-lg font-semibold ${portfolioResult.returnRate >= 0 ? "text-emerald-400" : "text-red-400"}`}
                >
                  {portfolioResult.returnRate >= 0 ? "+" : ""}
                  {portfolioResult.returnRate.toFixed(2)}%
                </p>
              </div>
            </div>

            {/* 리밸런싱 이벤트 */}
            {portfolioResult.rebalanceEvents.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">리밸런싱 이벤트</p>
                <div className="space-y-1.5">
                  {portfolioResult.rebalanceEvents.map((event, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm"
                    >
                      <span className="text-muted-foreground">{event.month}개월차</span>
                      <span>
                        {isMasked
                          ? `${MASK}원`
                          : `${formatMaskedKrw(event.preRebalanceValue, false)} → ${formatMaskedKrw(event.postRebalanceValue, false)}`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
