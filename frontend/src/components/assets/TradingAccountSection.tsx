"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

/**
 * KIS 계좌 액션바 + 잔고 요약 카드.
 *
 * 보유 종목 테이블은 통합 AssetList(소스 'kis' 행)에서 표시한다.
 * 이 섹션은 KIS 계좌 연결/비활성화/잔고 새로고침 액션과
 * 계좌별 총평가/예수금 요약만 담당한다.
 */
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
        <div>
          <h2 className="text-lg font-semibold">한국투자증권 계좌</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            연결된 계좌의 보유 종목과 예수금은 아래 자산 목록에 자동 동기화됩니다.
          </p>
        </div>
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
        <div className="flex flex-col items-center justify-center py-10 rounded-lg border border-dashed border-border text-muted-foreground">
          <Wallet className="size-8 mb-2 opacity-40" />
          <p className="text-sm font-medium mb-1">연결된 계좌가 없습니다</p>
          <p className="text-xs mb-3">한국투자증권 계좌를 연결하면 잔고와 보유 종목이 자동으로 자산에 추가됩니다.</p>
          <Button size="sm" onClick={() => setAccountFormOpen(true)}>
            <Plus className="size-3.5 mr-1" />
            계좌 연결하기
          </Button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {accounts.map((account) => {
            const balance = accountBalances[account.id];
            const hasBalance = !!balance;
            const cash = balance?.cash ?? 0;
            const totalEval = balance?.totalEval ?? 0;
            const totalPnl = balance?.totalPnl ?? 0;
            const totalValue = hasBalance ? cash + totalEval : 0;

            return (
              <Card key={account.id}>
                <CardContent className="pt-3 pb-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5">
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
                      className="size-6 text-muted-foreground hover:text-destructive"
                      onClick={() => onDeactivateAccount(account.id)}
                      aria-label="계좌 비활성화"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>

                  <div className="flex items-baseline justify-between">
                    <span className="text-xs text-muted-foreground">총 평가금액</span>
                    <span className="font-bold text-base">
                      {formatMaskedKrw(totalValue, isMasked)}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between text-xs mt-0.5">
                    <span className="text-muted-foreground">예수금</span>
                    <span className="font-medium">{formatMaskedKrw(cash, isMasked)}</span>
                  </div>
                  <div className="flex items-baseline justify-between text-xs mt-0.5">
                    <span className="text-muted-foreground">주식 평가</span>
                    <span className="font-medium">{formatMaskedKrw(totalEval, isMasked)}</span>
                  </div>
                  {hasBalance && (
                    <div className="flex items-baseline justify-between text-xs mt-0.5">
                      <span className="text-muted-foreground">평가손익</span>
                      <span
                        className={`font-medium ${totalPnl > 0 ? "text-emerald-500" : totalPnl < 0 ? "text-red-500" : ""}`}
                      >
                        {isMasked
                          ? "●●●●●●원"
                          : `${totalPnl >= 0 ? "+" : ""}${totalPnl.toLocaleString()}원`}
                      </span>
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
