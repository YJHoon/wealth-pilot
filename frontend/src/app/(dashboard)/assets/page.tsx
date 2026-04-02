"use client";

import { useCallback } from "react";
import { toast } from "sonner";
import { TradingAccountSection } from "@/components/assets/TradingAccountSection";
import { useTrading } from "@/hooks/useTrading";
import type { TradingAccountCreateRequest } from "@/types/trading";
import { ApiError } from "@/lib/api";

export default function AssetsPage() {
  const trading = useTrading();

  // ── 계좌 핸들러 ──

  const handleCreateAccount = useCallback(
    async (data: TradingAccountCreateRequest) => {
      try {
        await trading.createAccount(data);
        toast.success("계좌가 등록되었습니다. 잔고를 조회합니다...");
      } catch (err) {
        toast.error(
          err instanceof ApiError ? err.message : "계좌 등록에 실패했습니다.",
        );
        throw err;
      }
    },
    [trading],
  );

  const handleDeactivateAccount = useCallback(
    async (id: string) => {
      try {
        await trading.deactivateAccount(id);
        toast.success("계좌가 비활성화되었습니다.");
      } catch {
        toast.error("계좌 비활성화에 실패했습니다.");
      }
    },
    [trading],
  );

  const handleRefreshBalances = useCallback(async () => {
    try {
      await trading.refreshAccountBalances();
      toast.success("잔고가 갱신되었습니다.");
    } catch {
      toast.error("잔고 조회에 실패했습니다.");
    }
  }, [trading]);

  return (
    <div className="space-y-8">
      <TradingAccountSection
        accounts={trading.accounts}
        accountBalances={trading.accountBalances}
        loading={trading.loading.accounts}
        onCreateAccount={handleCreateAccount}
        onDeactivateAccount={handleDeactivateAccount}
        onRefreshBalances={handleRefreshBalances}
      />
    </div>
  );
}
