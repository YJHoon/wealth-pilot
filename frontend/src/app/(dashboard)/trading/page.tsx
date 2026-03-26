"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { useTrading } from "@/hooks/useTrading";
import { AccountFormDialog } from "@/components/trading/AccountFormDialog";
import { StrategyFormDialog } from "@/components/trading/StrategyFormDialog";
import { AccountsStrategiesTab } from "@/components/trading/AccountsStrategiesTab";
import { OrdersTab } from "@/components/trading/OrdersTab";
import { PositionsPerformanceTab } from "@/components/trading/PositionsPerformanceTab";
import type {
  TradingAccountCreateRequest,
  TradingStrategyCreateRequest,
  TradingStrategyUpdateRequest,
  TradingStrategy,
} from "@/types/trading";
import { tradingModeLabels } from "@/types/trading";
import { Plus } from "lucide-react";

export default function TradingPage() {
  const trading = useTrading();
  const [accountFormOpen, setAccountFormOpen] = useState(false);
  const [strategyFormOpen, setStrategyFormOpen] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState<TradingStrategy | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // ── Account handlers ──

  const handleCreateAccount = useCallback(
    async (data: TradingAccountCreateRequest) => {
      setIsSubmitting(true);
      try {
        await trading.createAccount(data);
        toast.success("계좌가 등록되었습니다.");
        setAccountFormOpen(false);
      } catch {
        toast.error("계좌 등록에 실패했습니다.");
      } finally {
        setIsSubmitting(false);
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

  // ── Strategy handlers ──

  const handleCreateStrategy = useCallback(
    async (data: TradingStrategyCreateRequest) => {
      setIsSubmitting(true);
      try {
        await trading.createStrategy(data);
        toast.success("전략이 생성되었습니다.");
        setStrategyFormOpen(false);
      } catch {
        toast.error("전략 생성에 실패했습니다.");
      } finally {
        setIsSubmitting(false);
      }
    },
    [trading],
  );

  const handleUpdateStrategy = useCallback(
    async (id: string, data: TradingStrategyUpdateRequest) => {
      setIsSubmitting(true);
      try {
        await trading.updateStrategy(id, data);
        toast.success("전략이 수정되었습니다.");
        setStrategyFormOpen(false);
        setEditingStrategy(null);
      } catch {
        toast.error("전략 수정에 실패했습니다.");
      } finally {
        setIsSubmitting(false);
      }
    },
    [trading],
  );

  const handleEditStrategy = useCallback((strategy: TradingStrategy) => {
    setEditingStrategy(strategy);
    setStrategyFormOpen(true);
  }, []);

  const handleAddStrategy = useCallback(() => {
    setEditingStrategy(null);
    setStrategyFormOpen(true);
  }, []);

  // ── Schedule handlers ──

  const handleStartSchedule = useCallback(
    async (strategyId: string) => {
      try {
        await trading.startSchedule(strategyId);
        toast.success("자동매매가 시작되었습니다.");
      } catch {
        toast.error("자동매매 시작에 실패했습니다.");
      }
    },
    [trading],
  );

  const handleStopSchedule = useCallback(
    async (strategyId: string) => {
      try {
        await trading.stopSchedule(strategyId);
        toast.success("자동매매가 중지되었습니다.");
      } catch {
        toast.error("자동매매 중지에 실패했습니다.");
      }
    },
    [trading],
  );

  const handleRunNow = useCallback(
    async (strategyId: string) => {
      try {
        await trading.runNow(strategyId);
        toast.success("즉시 실행을 요청했습니다.");
      } catch {
        toast.error("즉시 실행에 실패했습니다.");
      }
    },
    [trading],
  );

  const selectedAccount = trading.accounts.find((a) => a.id === trading.selectedAccountId);

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-bold">자동매매</h1>
        <div className="flex items-center gap-2">
          {trading.accounts.length > 0 && (
            <Select
              value={trading.selectedAccountId ?? ""}
              onValueChange={(val) => trading.setSelectedAccountId(val || null)}
            >
              <SelectTrigger className="w-48">
                <span>
                  {selectedAccount
                    ? tradingModeLabels[selectedAccount.mode]
                    : "계좌 선택"}
                </span>
              </SelectTrigger>
              <SelectContent>
                {trading.accounts.map((account) => (
                  <SelectItem key={account.id} value={account.id}>
                    {tradingModeLabels[account.mode]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button size="sm" onClick={() => setAccountFormOpen(true)}>
            <Plus className="size-3.5 mr-1" />
            계좌 등록
          </Button>
        </div>
      </div>

      {/* 탭 */}
      <Tabs defaultValue="accounts">
        <TabsList>
          <TabsTrigger value="accounts">계좌/전략</TabsTrigger>
          <TabsTrigger value="orders">주문내역</TabsTrigger>
          <TabsTrigger value="positions">포지션/성과</TabsTrigger>
        </TabsList>

        <TabsContent value="accounts" className="mt-4">
          <AccountsStrategiesTab
            accounts={trading.accounts}
            strategies={trading.strategies}
            selectedAccountId={trading.selectedAccountId}
            onDeactivateAccount={handleDeactivateAccount}
            onStartSchedule={handleStartSchedule}
            onStopSchedule={handleStopSchedule}
            onRunNow={handleRunNow}
            onEditStrategy={handleEditStrategy}
            onAddStrategy={handleAddStrategy}
          />
        </TabsContent>

        <TabsContent value="orders" className="mt-4">
          <OrdersTab
            orders={trading.orders}
            loading={trading.loading.orders}
            onRefetch={trading.refetchOrders}
          />
        </TabsContent>

        <TabsContent value="positions" className="mt-4">
          <PositionsPerformanceTab
            positions={trading.positions}
            performance={trading.performance}
            loading={trading.loading.positions || trading.loading.performance}
          />
        </TabsContent>
      </Tabs>

      {/* 다이얼로그 */}
      <AccountFormDialog
        open={accountFormOpen}
        onOpenChange={setAccountFormOpen}
        onSubmit={handleCreateAccount}
        isSubmitting={isSubmitting}
      />

      {trading.selectedAccountId && (
        <StrategyFormDialog
          open={strategyFormOpen}
          onOpenChange={(open) => {
            setStrategyFormOpen(open);
            if (!open) setEditingStrategy(null);
          }}
          accountId={trading.selectedAccountId}
          editingStrategy={editingStrategy}
          onSubmitCreate={handleCreateStrategy}
          onSubmitUpdate={handleUpdateStrategy}
          isSubmitting={isSubmitting}
        />
      )}
    </div>
  );
}
