"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { useTrading } from "@/hooks/useTrading";
import { StrategyFormDialog } from "@/components/trading/StrategyFormDialog";
import { RebalanceDialog } from "@/components/trading/RebalanceDialog";
import type {
  AccountRebalanceRequest,
  TradingStrategyCreateRequest,
  TradingStrategyUpdateRequest,
  TradingStrategy,
} from "@/types/trading";
import { tradingModeLabels, strategyTypeLabels } from "@/types/trading";
import Link from "next/link";
import { Bot, Pencil, Play, Plus, Scale, Square, Zap } from "lucide-react";

export default function TradingPage() {
  const trading = useTrading();
  const [strategyFormOpen, setStrategyFormOpen] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState<TradingStrategy | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rebalanceOpen, setRebalanceOpen] = useState(false);
  const [isRebalancing, setIsRebalancing] = useState(false);

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

  const handleToggleNetting = useCallback(
    async (accountId: string, enabled: boolean) => {
      try {
        await trading.updateAccount(accountId, { allow_netting: enabled });
        toast.success(
          enabled ? "주문 네팅을 활성화했습니다." : "주문 네팅을 비활성화했습니다.",
        );
      } catch {
        toast.error("네팅 설정 변경에 실패했습니다.");
      }
    },
    [trading],
  );

  const handleRebalance = useCallback(
    async (data: AccountRebalanceRequest) => {
      if (!trading.selectedAccountId) return;
      setIsRebalancing(true);
      try {
        await trading.rebalanceAccount(trading.selectedAccountId, data);
        toast.success("전략 자본을 재배분했습니다.");
        setRebalanceOpen(false);
      } catch {
        toast.error("재배분에 실패했습니다.");
      } finally {
        setIsRebalancing(false);
      }
    },
    [trading],
  );

  const selectedAccount = trading.accounts.find((a) => a.id === trading.selectedAccountId);
  const accountStrategies = trading.strategies.filter(
    (s) => s.accountId === trading.selectedAccountId,
  );

  return (
    <div className="space-y-6">
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
          {selectedAccount && accountStrategies.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setRebalanceOpen(true)}
            >
              <Scale className="size-3.5 mr-1" />
              재배분
            </Button>
          )}
          {selectedAccount && (
            <Button size="sm" onClick={handleAddStrategy}>
              <Plus className="size-3.5 mr-1" />
              전략 추가
            </Button>
          )}
        </div>
      </div>

      {/* 계좌 미등록 안내 */}
      {trading.accounts.length === 0 && !trading.loading.accounts && (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Bot className="size-10 mb-3 opacity-40" />
          <p className="text-sm font-medium mb-1">등록된 계좌가 없습니다</p>
          <p className="text-xs mb-4">
            자동매매를 시작하려면 먼저 내 자산 페이지에서 계좌를 등록해주세요.
          </p>
          <Link
            href="/assets"
            className="inline-flex items-center rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent transition-colors"
          >
            내 자산에서 계좌 등록하기
          </Link>
        </div>
      )}

      {/* 계좌 선택 안내 */}
      {trading.accounts.length > 0 && !selectedAccount && (
        <p className="text-sm text-muted-foreground text-center py-8">
          계좌를 선택해주세요.
        </p>
      )}

      {/* 계좌 설정 */}
      {selectedAccount && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              className="size-3.5 rounded border-border"
              checked={selectedAccount.allowNetting}
              onChange={(e) =>
                handleToggleNetting(selectedAccount.id, e.target.checked)
              }
            />
            <span>주문 네팅 (같은 종목 반대 방향 주문 스킵)</span>
          </label>
        </div>
      )}

      {/* 전략 카드 목록 */}
      {selectedAccount && (
        <>
          {accountStrategies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Bot className="size-10 mb-3 opacity-40" />
              <p className="text-sm font-medium mb-1">등록된 전략이 없습니다</p>
              <p className="text-xs mb-4">AI가 자동으로 매매합니다. 첫 전략을 만들어보세요.</p>
              <Button size="sm" onClick={handleAddStrategy}>
                <Plus className="size-3.5 mr-1" />
                전략 만들기
              </Button>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {accountStrategies.map((strategy) => (
                <Card key={strategy.id}>
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-start justify-between">
                      <div className="space-y-2 flex-1">
                        {/* 전략명 + 상태 */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium">{strategy.name}</span>
                          <Badge variant="outline">
                            {strategyTypeLabels[strategy.strategyType]}
                          </Badge>
                          <Badge
                            variant={strategy.isScheduled ? "default" : "secondary"}
                            className={
                              strategy.isScheduled
                                ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                : ""
                            }
                          >
                            {strategy.isScheduled ? "실행 중" : "중지"}
                          </Badge>
                        </div>

                        {/* 부가 정보 */}
                        <div className="flex items-center gap-4 text-xs text-muted-foreground">
                          <span>{strategy.intervalMinutes}분 간격</span>
                          {strategy.marketHoursOnly && <span>장중전용</span>}
                        </div>
                      </div>

                      {/* 액션 버튼 */}
                      <div className="flex items-center gap-1 ml-2">
                        {strategy.isScheduled ? (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-red-400 hover:text-red-300"
                            onClick={() => handleStopSchedule(strategy.id)}
                            title="중지"
                          >
                            <Square className="size-3.5" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-emerald-400 hover:text-emerald-300"
                            onClick={() => handleStartSchedule(strategy.id)}
                            title="시작"
                          >
                            <Play className="size-3.5" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8"
                          onClick={() => handleRunNow(strategy.id)}
                          title="즉시 실행"
                        >
                          <Zap className="size-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8"
                          onClick={() => handleEditStrategy(strategy)}
                          title="수정"
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      {/* 전략 다이얼로그 */}
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

      {/* 재배분 다이얼로그 */}
      {selectedAccount && (
        <RebalanceDialog
          open={rebalanceOpen}
          onOpenChange={setRebalanceOpen}
          account={selectedAccount}
          strategies={accountStrategies}
          onSubmit={handleRebalance}
          isSubmitting={isRebalancing}
        />
      )}
    </div>
  );
}
