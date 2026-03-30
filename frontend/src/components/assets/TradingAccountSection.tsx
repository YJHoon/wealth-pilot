"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw } from "@/lib/format";
import { AccountFormDialog } from "@/components/trading/AccountFormDialog";
import type { TradingAccount, TradingAccountCreateRequest } from "@/types/trading";
import { tradingModeLabels } from "@/types/trading";
import { Loader2, Plus, Trash2, Wallet } from "lucide-react";

interface TradingAccountSectionProps {
  accounts: TradingAccount[];
  loading: boolean;
  onCreateAccount: (data: TradingAccountCreateRequest) => Promise<void>;
  onDeactivateAccount: (id: string) => Promise<void>;
}

export function TradingAccountSection({
  accounts,
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
        <div className="grid gap-3 sm:grid-cols-2">
          {accounts.map((account) => (
            <Card key={account.id}>
              <CardContent className="pt-4 pb-4">
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
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">초기 자금</span>
                    <span className="font-bold text-base">
                      {formatMaskedKrw(account.initialCapital, isMasked)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>한국투자증권</span>
                    <span>
                      등록일 {new Date(account.createdAt).toLocaleDateString("ko-KR")}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
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
