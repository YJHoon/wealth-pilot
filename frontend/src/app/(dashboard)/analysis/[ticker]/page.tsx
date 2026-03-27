"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { useStockAnalysis } from "@/hooks/useStockAnalysis";
import { InvestmentDisclaimer } from "@/components/analysis/InvestmentDisclaimer";
import { FundamentalCard } from "@/components/analysis/FundamentalCard";
import { TechnicalChart } from "@/components/analysis/TechnicalChart";
import { SignalCard } from "@/components/analysis/SignalCard";
import { ValuationGauge } from "@/components/analysis/ValuationGauge";
import type { MarketType } from "@/types";
import { ArrowLeft, Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";

export default function TickerDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();

  const ticker = decodeURIComponent(params.ticker as string);
  const market = (searchParams.get("market") ?? "KRX") as MarketType;

  const { fundamental, technical, signals, loading, error, refetch } =
    useStockAnalysis({ ticker, market });

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/analysis">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="size-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{ticker}</h1>
            <p className="text-sm text-muted-foreground">
              {fundamental?.companyName ?? ticker} · {market}
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={refetch} disabled={loading}>
          <RefreshCw className={`mr-1.5 size-3.5 ${loading ? "animate-spin" : ""}`} />
          새로고침
        </Button>
      </div>

      <InvestmentDisclaimer
        text={fundamental?.disclaimer || signals?.disclaimer}
      />

      {/* 로딩/에러 */}
      {loading && (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* 데이터 */}
      {!loading && !error && (fundamental || technical || signals) && (
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">종합</TabsTrigger>
            <TabsTrigger value="fundamental">기본적 분석</TabsTrigger>
            <TabsTrigger value="technical">기술적 분석</TabsTrigger>
            <TabsTrigger value="signal">매매 시그널</TabsTrigger>
          </TabsList>

          {/* 종합 탭 */}
          <TabsContent value="overview" className="mt-4 space-y-4">
            {signals && <SignalCard data={signals} />}
            {fundamental && (
              <div className="grid gap-4 lg:grid-cols-2">
                <FundamentalCard data={fundamental} />
                <ValuationGauge data={fundamental} />
              </div>
            )}
            {technical && <TechnicalChart data={technical} />}
          </TabsContent>

          {/* 기본적 분석 탭 */}
          <TabsContent value="fundamental" className="mt-4 space-y-4">
            {fundamental ? (
              <>
                <FundamentalCard data={fundamental} />
                <ValuationGauge data={fundamental} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">기본적 분석 데이터가 없습니다.</p>
            )}
          </TabsContent>

          {/* 기술적 분석 탭 */}
          <TabsContent value="technical" className="mt-4">
            {technical ? (
              <TechnicalChart data={technical} />
            ) : (
              <p className="text-sm text-muted-foreground">기술적 분석 데이터가 없습니다.</p>
            )}
          </TabsContent>

          {/* 매매 시그널 탭 */}
          <TabsContent value="signal" className="mt-4">
            {signals ? (
              <SignalCard data={signals} />
            ) : (
              <p className="text-sm text-muted-foreground">매매 시그널 데이터가 없습니다.</p>
            )}
          </TabsContent>
        </Tabs>
      )}

      {/* 데이터 없음 */}
      {!loading && !error && !fundamental && !technical && !signals && (
        <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
          분석 데이터를 불러올 수 없습니다.
        </div>
      )}
    </div>
  );
}
