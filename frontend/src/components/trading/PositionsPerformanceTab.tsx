"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw, formatQuantity, pnlColorClass, formatPercent } from "@/lib/format";
import type { TradingPosition, TradingPerformance } from "@/types/trading";
import { TrendingUp, TrendingDown, Target, BarChart3 } from "lucide-react";

interface PositionsPerformanceTabProps {
  positions: TradingPosition[];
  performance: TradingPerformance | null;
  loading: boolean;
}

export function PositionsPerformanceTab({
  positions,
  performance,
  loading,
}: PositionsPerformanceTabProps) {
  const { isMasked } = useAppStore();

  if (loading) {
    return <p className="text-sm text-muted-foreground py-8 text-center">불러오는 중...</p>;
  }

  return (
    <div className="space-y-6">
      {/* 성과 요약 카드 */}
      {performance && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <BarChart3 className="size-4" />
                <span className="text-xs">총 거래</span>
              </div>
              <p className="text-2xl font-bold">{performance.totalTrades}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {performance.winningTrades}승 / {performance.losingTrades}패
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <Target className="size-4" />
                <span className="text-xs">승률</span>
              </div>
              <p className="text-2xl font-bold">
                {(performance.winRate * 100).toFixed(1)}%
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <TrendingUp className="size-4" />
                <span className="text-xs">실현손익</span>
              </div>
              <p className={`text-2xl font-bold ${pnlColorClass(performance.totalRealizedPnl)}`}>
                {isMasked
                  ? "●●●●●●원"
                  : `${performance.totalRealizedPnl >= 0 ? "+" : ""}${formatMaskedKrw(performance.totalRealizedPnl, false)}`}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <TrendingDown className="size-4" />
                <span className="text-xs">수익률</span>
              </div>
              <p className={`text-2xl font-bold ${pnlColorClass(performance.returnRate)}`}>
                {formatPercent(performance.returnRate * 100)}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* 부가 정보 */}
      {performance && (
        <div className="flex flex-wrap gap-4 text-sm">
          <div>
            <span className="text-muted-foreground mr-2">초기자금</span>
            <span className="font-medium">
              {formatMaskedKrw(performance.initialCapital, isMasked)}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground mr-2">현재가치</span>
            <span className="font-medium">
              {formatMaskedKrw(performance.currentValue, isMasked)}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground mr-2">미실현손익</span>
            <span className={`font-medium ${pnlColorClass(performance.totalUnrealizedPnl)}`}>
              {isMasked
                ? "●●●●●●원"
                : `${performance.totalUnrealizedPnl >= 0 ? "+" : ""}${formatMaskedKrw(performance.totalUnrealizedPnl, false)}`}
            </span>
          </div>
        </div>
      )}

      {/* 포지션 테이블 */}
      <section>
        <h3 className="text-sm font-medium text-muted-foreground mb-3">보유 포지션</h3>

        {positions.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">보유 포지션이 없습니다.</p>
        ) : (
          <>
            {/* 모바일: 카드 */}
            <div className="space-y-3 md:hidden">
              {positions.map((pos) => {
                const returnRate =
                  pos.currentPrice != null && pos.avgBuyPrice > 0
                    ? ((pos.currentPrice - pos.avgBuyPrice) / pos.avgBuyPrice) * 100
                    : null;
                return (
                  <Card key={pos.id}>
                    <CardContent className="pt-3 pb-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-medium text-sm">{pos.tickerName}</span>
                          <span className="text-xs text-muted-foreground ml-1 font-mono">
                            {pos.ticker}
                          </span>
                        </div>
                        {returnRate != null && (
                          <span className={`text-sm font-medium ${pnlColorClass(returnRate)}`}>
                            {formatPercent(returnRate)}
                          </span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-x-4 text-xs">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">수량</span>
                          <span>{formatQuantity(pos.quantity, isMasked)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">평균매입가</span>
                          <span>{formatMaskedKrw(pos.avgBuyPrice, isMasked)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">현재가</span>
                          <span>
                            {pos.currentPrice != null
                              ? formatMaskedKrw(pos.currentPrice, isMasked)
                              : "-"}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">평가손익</span>
                          <span
                            className={pnlColorClass(pos.unrealizedPnl ?? 0)}
                          >
                            {pos.unrealizedPnl != null
                              ? isMasked
                                ? "●●●●●●원"
                                : `${pos.unrealizedPnl >= 0 ? "+" : ""}${formatMaskedKrw(pos.unrealizedPnl, false)}`
                              : "-"}
                          </span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {/* 데스크톱: 테이블 */}
            <div className="hidden md:block rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>종목</TableHead>
                    <TableHead className="text-right">수량</TableHead>
                    <TableHead className="text-right">평균매입가</TableHead>
                    <TableHead className="text-right">현재가</TableHead>
                    <TableHead className="text-right">평가손익</TableHead>
                    <TableHead className="text-right">수익률</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positions.map((pos) => {
                    const returnRate =
                      pos.currentPrice != null && pos.avgBuyPrice > 0
                        ? ((pos.currentPrice - pos.avgBuyPrice) / pos.avgBuyPrice) * 100
                        : null;
                    return (
                      <TableRow key={pos.id}>
                        <TableCell>
                          <span className="font-medium text-sm">{pos.tickerName}</span>
                          <span className="text-xs text-muted-foreground ml-1 font-mono">
                            {pos.ticker}
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm">
                          {formatQuantity(pos.quantity, isMasked)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm">
                          {formatMaskedKrw(pos.avgBuyPrice, isMasked)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm">
                          {pos.currentPrice != null
                            ? formatMaskedKrw(pos.currentPrice, isMasked)
                            : "-"}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono text-sm ${pnlColorClass(pos.unrealizedPnl ?? 0)}`}
                        >
                          {pos.unrealizedPnl != null
                            ? isMasked
                              ? "●●●●●●원"
                              : `${pos.unrealizedPnl >= 0 ? "+" : ""}${formatMaskedKrw(pos.unrealizedPnl, false)}`
                            : "-"}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono text-sm ${returnRate != null ? pnlColorClass(returnRate) : ""}`}
                        >
                          {returnRate != null ? formatPercent(returnRate) : "-"}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
