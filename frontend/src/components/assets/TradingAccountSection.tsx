"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw } from "@/lib/format";
import { AccountFormDialog } from "@/components/trading/AccountFormDialog";
import type {
  TradingAccount,
  TradingAccountCreateRequest,
  KisBalance,
} from "@/types/trading";
import { tradingModeLabels } from "@/types/trading";
import { Loader2, Plus, RefreshCw, Trash2, Wallet } from "lucide-react";

interface TradingAccountSectionProps {
  accounts: TradingAccount[];
  accountBalances: Record<string, KisBalance>;
  loading: boolean;
  onCreateAccount: (data: TradingAccountCreateRequest) => Promise<void>;
  onDeactivateAccount: (id: string) => Promise<void>;
  onRefreshBalances: () => Promise<void>;
}

export function TradingAccountSection({
  accounts,
  accountBalances,
  loading,
  onCreateAccount,
  onDeactivateAccount,
  onRefreshBalances,
}: TradingAccountSectionProps) {
  const { isMasked } = useAppStore();
  const [accountFormOpen, setAccountFormOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleSubmit = async (data: TradingAccountCreateRequest) => {
    setIsSubmitting(true);
    try {
      await onCreateAccount(data);
      setAccountFormOpen(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await onRefreshBalances();
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">내 자산</h2>
        <div className="flex items-center gap-2">
          {accounts.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleRefresh}
              disabled={isRefreshing}
            >
              <RefreshCw className={`size-3.5 mr-1 ${isRefreshing ? "animate-spin" : ""}`} />
              잔고 새로고침
            </Button>
          )}
          <Button size="sm" onClick={() => setAccountFormOpen(true)}>
            <Plus className="size-3.5 mr-1" />
            계좌 연결
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground">
          <Loader2 className="size-5 animate-spin mr-2" />
          계좌 정보를 불러오는 중...
        </div>
      ) : accounts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 rounded-lg border border-dashed border-border text-muted-foreground">
          <Wallet className="size-10 mb-3 opacity-40" />
          <p className="text-sm font-medium mb-1">연결된 계좌가 없습니다</p>
          <p className="text-xs mb-4">한국투자증권 계좌를 연결하면 잔고와 보유종목을 자동으로 가져옵니다.</p>
          <Button size="sm" onClick={() => setAccountFormOpen(true)}>
            <Plus className="size-3.5 mr-1" />
            계좌 연결하기
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {accounts.map((account) => {
            const balance = accountBalances[account.id];
            const holdings = balance?.holdings ?? [];
            const cash = balance?.cash ?? account.cashBalance ?? 0;
            const totalEval = balance?.totalEval ?? 0;
            const totalPnl = balance?.totalPnl ?? 0;
            const totalValue = cash + totalEval;
            const hasBalance = !!balance;

            return (
              <Card key={account.id}>
                <CardContent className="pt-4 pb-4">
                  {/* 계좌 헤더 */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={account.mode === "live" ? "destructive" : "secondary"}
                      >
                        {tradingModeLabels[account.mode]}
                      </Badge>
                      <Badge variant={account.isActive ? "default" : "secondary"}>
                        {account.isActive ? "활성" : "비활성"}
                      </Badge>
                      {!hasBalance && (
                        <Badge variant="outline" className="text-xs text-muted-foreground">
                          조회 중...
                        </Badge>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 text-muted-foreground hover:text-destructive"
                      onClick={() => onDeactivateAccount(account.id)}
                      aria-label="계좌 비활성화"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>

                  {/* 잔고 요약 */}
                  <div className="space-y-1 mb-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">총 평가금액</span>
                      <span className="font-bold text-base">
                        {formatMaskedKrw(totalValue, isMasked)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">예수금</span>
                      <span className="font-medium">
                        {formatMaskedKrw(cash, isMasked)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">주식 평가</span>
                      <span className="font-medium">
                        {formatMaskedKrw(totalEval, isMasked)}
                      </span>
                    </div>
                    {hasBalance && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">평가손익</span>
                        <span className={`font-medium ${totalPnl > 0 ? "text-emerald-500" : totalPnl < 0 ? "text-red-500" : ""}`}>
                          {isMasked
                            ? "●●●●●●원"
                            : `${totalPnl >= 0 ? "+" : ""}${totalPnl.toLocaleString()}원`}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>한국투자증권</span>
                      <span>
                        {hasBalance ? "KIS 실시간 조회" : `등록일 ${new Date(account.createdAt).toLocaleDateString("ko-KR")}`}
                      </span>
                    </div>
                  </div>

                  {/* 보유 종목 (KIS 실시간) */}
                  {holdings.length > 0 && (
                    <div className="border-t pt-3">
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">
                        보유 종목 ({holdings.length})
                      </h4>
                      <div className="overflow-x-auto">
                        <Table>
                          <TableHeader>
                            <TableRow className="text-xs">
                              <TableHead className="h-8">종목</TableHead>
                              <TableHead className="h-8 text-right">수량</TableHead>
                              <TableHead className="h-8 text-right">평균매입</TableHead>
                              <TableHead className="h-8 text-right">현재가</TableHead>
                              <TableHead className="h-8 text-right">평가금액</TableHead>
                              <TableHead className="h-8 text-right">평가손익</TableHead>
                              <TableHead className="h-8 text-right">수익률</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {holdings.map((h) => {
                              const pnlColor =
                                h.pnl > 0
                                  ? "text-emerald-500"
                                  : h.pnl < 0
                                    ? "text-red-500"
                                    : "";
                              return (
                                <TableRow key={h.ticker} className="text-xs">
                                  <TableCell className="py-1.5">
                                    <div>
                                      <span className="font-medium">{h.name}</span>
                                      <span className="ml-1 text-muted-foreground font-mono">
                                        {h.ticker}
                                      </span>
                                    </div>
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right font-mono">
                                    {isMasked ? "***" : h.quantity.toLocaleString()}
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right">
                                    {formatMaskedKrw(h.avgPrice, isMasked)}
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right">
                                    {formatMaskedKrw(h.currentPrice, isMasked)}
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right">
                                    {formatMaskedKrw(h.evalAmount, isMasked)}
                                  </TableCell>
                                  <TableCell className={`py-1.5 text-right font-medium ${pnlColor}`}>
                                    {isMasked
                                      ? "●●●●●●원"
                                      : `${h.pnl >= 0 ? "+" : ""}${h.pnl.toLocaleString()}원`}
                                  </TableCell>
                                  <TableCell className={`py-1.5 text-right font-medium ${pnlColor}`}>
                                    {isMasked
                                      ? "●●%"
                                      : `${h.pnlRate >= 0 ? "+" : ""}${h.pnlRate.toFixed(2)}%`}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    </div>
                  )}

                  {hasBalance && holdings.length === 0 && (
                    <div className="border-t pt-3 text-center text-xs text-muted-foreground py-4">
                      보유 종목이 없습니다
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <AccountFormDialog
        open={accountFormOpen}
        onOpenChange={setAccountFormOpen}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
      />
    </section>
  );
}
