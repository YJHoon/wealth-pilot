"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { useAppStore } from "@/stores/appStore";
import { MASK, formatMaskedKrw } from "@/lib/format";
import { useSimulation } from "@/hooks/useSimulation";
import { MARKETS, type MarketType, type ScenarioSimulationResult } from "@/types";
import { toNumber } from "@/lib/form-utils";
import { Loader2, TrendingUp, TrendingDown } from "lucide-react";

const scenarioSchema = z.object({
  ticker: z.string().min(1, "종목코드를 입력해주세요"),
  market: z.enum(MARKETS),
  entryPrice: z.number({ error: "진입가를 입력해주세요" }).positive(),
  quantity: z.number({ error: "수량을 입력해주세요" }).positive(),
  targetPrice: z.number({ error: "목표가를 입력해주세요" }).positive(),
  stopLossPrice: z.number({ error: "손절가를 입력해주세요" }).positive(),
});

type ScenarioFormValues = z.infer<typeof scenarioSchema>;

export function ScenarioCalculator() {
  const isMasked = useAppStore((s) => s.isMasked);
  const { result, loading, error, runSimulation, reset: resetSimulation } = useSimulation();
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ScenarioFormValues>({
    resolver: zodResolver(scenarioSchema),
    defaultValues: { ticker: "", market: MARKETS[0] },
  });

  const marketValue = watch("market");

  const onSubmit = handleSubmit(async (values) => {
    setSubmitted(true);
    try {
      await runSimulation({ type: "scenario", ...values });
    } catch {
      // error handled by useSimulation
    }
  });

  const scenarioResult =
    result?.type === "scenario" ? (result.result as ScenarioSimulationResult) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">시나리오 계산기</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={onSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="sc-ticker">종목코드</Label>
              <Input id="sc-ticker" placeholder="005930" {...register("ticker")} />
              {errors.ticker && <p className="text-xs text-destructive">{errors.ticker.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label>시장</Label>
              <Select value={marketValue} onValueChange={(v) => setValue("market", v as MarketType)}>
                <SelectTrigger><span>{marketValue}</span></SelectTrigger>
                <SelectContent>
                  {MARKETS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sc-quantity">수량(주)</Label>
              <Input id="sc-quantity" type="number" placeholder="10" {...register("quantity", { setValueAs: toNumber })} />
              {errors.quantity && <p className="text-xs text-destructive">{errors.quantity.message}</p>}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="sc-entry">진입가(원)</Label>
              <Input id="sc-entry" type="number" placeholder="70000" {...register("entryPrice", { setValueAs: toNumber })} />
              {errors.entryPrice && <p className="text-xs text-destructive">{errors.entryPrice.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sc-target">목표가(원)</Label>
              <Input id="sc-target" type="number" placeholder="85000" {...register("targetPrice", { setValueAs: toNumber })} />
              {errors.targetPrice && <p className="text-xs text-destructive">{errors.targetPrice.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sc-stoploss">손절가(원)</Label>
              <Input id="sc-stoploss" type="number" placeholder="65000" {...register("stopLossPrice", { setValueAs: toNumber })} />
              {errors.stopLossPrice && <p className="text-xs text-destructive">{errors.stopLossPrice.message}</p>}
            </div>
          </div>

          <div className="flex gap-2">
            <Button type="submit" disabled={loading}>
              {loading ? <Loader2 className="mr-1 size-4 animate-spin" /> : null}
              계산
            </Button>
            {submitted && (
              <Button type="button" variant="outline" onClick={() => { resetSimulation(); setSubmitted(false); }}>
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

        {scenarioResult && (
          <div className="grid grid-cols-2 gap-4">
            {/* 수익 시나리오 */}
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="size-5 text-emerald-400" />
                <p className="text-sm font-medium text-emerald-400">목표가 도달 시</p>
              </div>
              <p className="mt-2 text-2xl font-bold text-emerald-400">
                {isMasked ? `${MASK}원` : `+${formatMaskedKrw(scenarioResult.potentialProfit, false)}`}
              </p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                +{scenarioResult.profitPct.toFixed(2)}%
              </p>
            </div>

            {/* 손실 시나리오 */}
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
              <div className="flex items-center gap-2">
                <TrendingDown className="size-5 text-red-400" />
                <p className="text-sm font-medium text-red-400">손절가 도달 시</p>
              </div>
              <p className="mt-2 text-2xl font-bold text-red-400">
                {isMasked ? `${MASK}원` : `-${formatMaskedKrw(Math.abs(scenarioResult.potentialLoss), false)}`}
              </p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {scenarioResult.lossPct.toFixed(2)}%
              </p>
            </div>

            {/* 위험보상비율 */}
            <div className="col-span-2 rounded-lg border border-border p-4 text-center">
              <p className="text-sm text-muted-foreground">위험보상비율 (Risk/Reward)</p>
              <p className={`mt-1 text-3xl font-bold ${scenarioResult.riskRewardRatio >= 2 ? "text-emerald-400" : scenarioResult.riskRewardRatio >= 1 ? "text-amber-400" : "text-red-400"}`}>
                1 : {scenarioResult.riskRewardRatio.toFixed(2)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {scenarioResult.riskRewardRatio >= 2
                  ? "양호한 위험보상비율"
                  : scenarioResult.riskRewardRatio >= 1
                    ? "보통 수준"
                    : "위험 대비 보상이 부족합니다"}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
