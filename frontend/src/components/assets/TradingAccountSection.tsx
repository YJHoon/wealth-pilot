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
  TradingPosition,
} from "@/types/trading";
import { tradingModeLabels } from "@/types/trading";
import { Loader2, Plus, Trash2, Wallet } from "lucide-react";

interface TradingAccountSectionProps {
  accounts: TradingAccount[];
  positions: TradingPosition[];
  loading: boolean;
  onCreateAccount: (data: TradingAccountCreateRequest) => Promise<void>;
  onDeactivateAccount: (id: string) => Promise<void>;
}

export function TradingAccountSection({
  accounts,
  positions,
  loading,
  onCreateAccount,
  onDeactivateAccount,
}: TradingAccountSectionProps) {
  const { isMasked } = useAppStore();
  const [accountFormOpen, setAccountFormOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (data: TradingAccountCreateRequest) => {
    setIsSubmitting(true);
    try {
      await onCreateAccount(data);
      setAccountFormOpen(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">연결 계좌</h2>
        <Button size="sm" onClick={() => setAccountFormOpen(true)}>
          <Plus className="size-3.5 mr-1" />
          계좌 연결
        </Button>
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
            const accountPositions = positions.filter(
              (p) => p.accountId === account.id,
            );
            const positionsValue = accountPositions.reduce((sum, p) => {
              const value = p.quantity * (p.currentPrice ?? p.avgBuyPrice);
              return sum + value;
            }, 0);
            const totalValue = (account.cashBalance ?? 0) + positionsValue;

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
                      <span className="text-muted-foreground">현금 잔고</span>
                      <span className="font-medium">
                        {formatMaskedKrw(account.cashBalance ?? 0, isMasked)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">주식 평가</span>
                      <span className="font-medium">
                        {formatMaskedKrw(positionsValue, isMasked)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>한국투자증권</span>
                      <span>
                        등록일 {new Date(account.createdAt).toLocaleDateString("ko-KR")}
                      </span>
                    </div>
                  </div>

                  {/* 보유 종목 */}
                  {accountPositions.length > 0 && (
                    <div className="border-t pt-3">
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">
                        보유 종목 ({accountPositions.length})
                      </h4>
                      <div className="overflow-x-auto">
                        <Table>
                          <TableHeader>
                            <TableRow className="text-xs">
                              <TableHead className="h-8">종목</TableHead>
                              <TableHead className="h-8 text-right">수량</TableHead>
                              <TableHead className="h-8 text-right">평균매입</TableHead>
                              <TableHead className="h-8 text-right">현재가</TableHead>
                              <TableHead className="h-8 text-right">평가손익</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {accountPositions.map((pos) => {
                              const pnl = pos.unrealizedPnl ?? 0;
                              const pnlColor =
                                pnl > 0
                                  ? "text-emerald-500"
                                  : pnl < 0
                                    ? "text-red-500"
                                    : "";
                              return (
                                <TableRow key={pos.id} className="text-xs">
                                  <TableCell className="py-1.5">
                                    <div>
                                      <span className="font-medium">{pos.tickerName}</span>
                                      <span className="ml-1 text-muted-foreground font-mono">
                                        {pos.ticker}
                                      </span>
                                    </div>
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right font-mono">
                                    {isMasked ? "***" : pos.quantity.toLocaleString()}
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right">
                                    {formatMaskedKrw(pos.avgBuyPrice, isMasked)}
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right">
                                    {formatMaskedKrw(pos.currentPrice ?? 0, isMasked)}
                                  </TableCell>
                                  <TableCell className={`py-1.5 text-right font-medium ${pnlColor}`}>
                                    {isMasked
                                      ? "●●●●●●원"
                                      : `${pnl >= 0 ? "+" : ""}${pnl.toLocaleString()}원`}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
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
