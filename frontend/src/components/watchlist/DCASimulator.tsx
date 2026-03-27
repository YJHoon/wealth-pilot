"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
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
import { MASK, formatMaskedKrw, formatAmountAbbreviated } from "@/lib/format";
import { useSimulation } from "@/hooks/useSimulation";
import { MARKETS, type MarketType, type DcaSimulationResult } from "@/types";
import { toNumber } from "@/lib/form-utils";
import { Loader2 } from "lucide-react";

const dcaSchema = z.object({
  ticker: z.string().min(1, "종목코드를 입력해주세요"),
  market: z.enum(MARKETS),
  monthlyAmount: z.number({ error: "월 투자금을 입력해주세요" }).positive("0보다 커야 합니다"),
  months: z.number({ error: "투자 기간을 입력해주세요" }).int().min(1).max(120),
});

type DcaFormValues = z.infer<typeof dcaSchema>;

export function DCASimulator() {
  const isMasked = useAppStore((s) => s.isMasked);
  const { result, loading, error, runSimulation, reset: resetSimulation } = useSimulation();
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<DcaFormValues>({
    resolver: zodResolver(dcaSchema),
    defaultValues: { ticker: "", market: MARKETS[0], monthlyAmount: undefined, months: 12 },
  });

  const marketValue = watch("market");

  const onSubmit = handleSubmit(async (values) => {
    setSubmitted(true);
    try {
      await runSimulation({ type: "dca", ...values });
    } catch {
      // error is handled by useSimulation
    }
  });

  const dcaResult = result?.type === "dca" ? (result.result as DcaSimulationResult) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">DCA (적립식 투자) 시뮬레이터</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={onSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="dca-ticker">종목코드</Label>
              <Input id="dca-ticker" placeholder="005930" {...register("ticker")} />
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
              <Label htmlFor="dca-amount">월 투자금(원)</Label>
              <Input id="dca-amount" type="number" placeholder="500000" {...register("monthlyAmount", { setValueAs: toNumber })} />
              {errors.monthlyAmount && <p className="text-xs text-destructive">{errors.monthlyAmount.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dca-months">기간(개월)</Label>
              <Input id="dca-months" type="number" defaultValue={12} {...register("months", { setValueAs: toNumber })} />
              {errors.months && <p className="text-xs text-destructive">{errors.months.message}</p>}
            </div>
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={loading}>
              {loading ? <Loader2 className="mr-1 size-4 animate-spin" /> : null}
              시뮬레이션 실행
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

        {dcaResult && (
          <div className="space-y-4">
            {/* 요약 */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-border p-3 text-center">
                <p className="text-xs text-muted-foreground">총 투자금</p>
                <p className="mt-1 text-lg font-semibold">
                  {isMasked ? `${MASK}원` : formatMaskedKrw(dcaResult.totalInvested, false)}
                </p>
              </div>
              <div className="rounded-lg border border-border p-3 text-center">
                <p className="text-xs text-muted-foreground">최종 가치</p>
                <p className="mt-1 text-lg font-semibold">
                  {isMasked ? `${MASK}원` : formatMaskedKrw(dcaResult.finalValue, false)}
                </p>
              </div>
              <div className="rounded-lg border border-border p-3 text-center">
                <p className="text-xs text-muted-foreground">수익률</p>
                <p className={`mt-1 text-lg font-semibold ${dcaResult.returnRate >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {dcaResult.returnRate >= 0 ? "+" : ""}{dcaResult.returnRate.toFixed(2)}%
                </p>
              </div>
            </div>

            {/* 차트 */}
            {dcaResult.monthlyBreakdown.length > 0 && (
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={dcaResult.monthlyBreakdown} margin={{ top: 5, right: 5, bottom: 0, left: 5 }}>
                    <defs>
                      <linearGradient id="dcaGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="month"
                      tickFormatter={(v) => `${v}월`}
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tickFormatter={(v: number) => isMasked ? `${MASK}원` : formatAmountAbbreviated(v)}
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                      width={70}
                    />
                    {!isMasked && (
                      <RechartsTooltip
                        formatter={(value, name) => [
                          formatMaskedKrw(Number(value), false),
                          name === "portfolioValue" ? "포트폴리오 가치" : "누적 투자금",
                        ]}
                        labelFormatter={(label) => `${label}개월`}
                        contentStyle={{
                          backgroundColor: "hsl(var(--card))",
                          borderColor: "hsl(var(--border))",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                      />
                    )}
                    <Area type="monotone" dataKey="cumulativeInvested" stroke="#6b7280" strokeWidth={1} strokeDasharray="5 5" fill="none" />
                    <Area type="monotone" dataKey="portfolioValue" stroke="#3b82f6" strokeWidth={2} fill="url(#dcaGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
