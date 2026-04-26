"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { useTrading } from "@/hooks/useTrading";
import { StrategyFormDialog } from "@/components/trading/StrategyFormDialog";
import { RebalanceDialog } from "@/components/trading/RebalanceDialog";
import { DepositDialog } from "@/components/trading/DepositDialog";
import type {
  AccountDepositRequest,
  AccountRebalanceRequest,
  TradingStrategyCreateRequest,
  TradingStrategyUpdateRequest,
  TradingStrategy,
} from "@/types/trading";
import { tradingModeLabels, strategyTypeLabels } from "@/types/trading";
import Link from "next/link";
import {
  Banknote,
  Bot,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Scale,
  Sparkles,
  Square,
  Trash2,
  Zap,
} from "lucide-react";

// 백엔드 ApiError의 detail 메시지를 fallback과 함께 토스트에 노출.
function toastError(fallback: string, err: unknown) {
  const detail = err instanceof ApiError ? err.message : null;
  toast.error(detail ? `${fallback}: ${detail}` : fallback);
}

function formatTimestamp(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ko-KR");
}

export default function TradingPage() {
  const trading = useTrading();
  const [strategyFormOpen, setStrategyFormOpen] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState<TradingStrategy | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rebalanceOpen, setRebalanceOpen] = useState(false);
  const [isRebalancing, setIsRebalancing] = useState(false);
  const [depositOpen, setDepositOpen] = useState(false);
  const [isDepositing, setIsDepositing] = useState(false);
  const [nettingUpdating, setNettingUpdating] = useState(false);
  const [refreshingAutoIds, setRefreshingAutoIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [pendingDelete, setPendingDelete] = useState<TradingStrategy | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // ── Strategy handlers ──

  const handleCreateStrategy = useCallback(
    async (data: TradingStrategyCreateRequest) => {
      setIsSubmitting(true);
      try {
        await trading.createStrategy(data);
        toast.success("전략이 생성되었습니다.");
        setStrategyFormOpen(false);
      } catch (e) {
        toastError("전략 생성에 실패했습니다.", e);
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
      } catch (e) {
        toastError("전략 수정에 실패했습니다.", e);
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

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDelete || isDeleting) return;
    setIsDeleting(true);
    try {
      await trading.deleteStrategy(pendingDelete.id);
      toast.success("전략이 삭제되었습니다.");
      setPendingDelete(null);
    } catch (e) {
      toastError("전략 삭제에 실패했습니다.", e);
    } finally {
      setIsDeleting(false);
    }
  }, [pendingDelete, isDeleting, trading]);

  // ── Schedule handlers ──

  const handleStartSchedule = useCallback(
    async (strategyId: string) => {
      try {
        await trading.startSchedule(strategyId);
        toast.success("자동매매가 시작되었습니다.");
      } catch (e) {
        toastError("자동매매 시작에 실패했습니다.", e);
      }
    },
    [trading],
  );

  const handleStopSchedule = useCallback(
    async (strategyId: string) => {
      try {
        await trading.stopSchedule(strategyId);
        toast.success("자동매매가 중지되었습니다.");
      } catch (e) {
        toastError("자동매매 중지에 실패했습니다.", e);
      }
    },
    [trading],
  );

  const handleRefreshAuto = useCallback(
    async (strategyId: string) => {
      let started = false;
      setRefreshingAutoIds((prev) => {
        if (prev.has(strategyId)) return prev;
        started = true;
        const next = new Set(prev);
        next.add(strategyId);
        return next;
      });
      if (!started) return;
      try {
        await trading.refreshAutoTickers(strategyId);
        toast.success("자동 선정 종목을 갱신했습니다.");
      } catch (e) {
        toastError("자동 선정 갱신에 실패했습니다.", e);
      } finally {
        setRefreshingAutoIds((prev) => {
          if (!prev.has(strategyId)) return prev;
          const next = new Set(prev);
          next.delete(strategyId);
          return next;
        });
      }
    },
    [trading],
  );

  const handleRunNow = useCallback(
    async (strategyId: string) => {
      try {
        await trading.runNow(strategyId);
        toast.success("즉시 실행을 요청했습니다.");
      } catch (e) {
        toastError("즉시 실행에 실패했습니다.", e);
      }
    },
    [trading],
  );

  const handleToggleNetting = useCallback(
    async (accountId: string, enabled: boolean) => {
      if (nettingUpdating) return;
      setNettingUpdating(true);
      try {
        await trading.updateAccount(accountId, { allow_netting: enabled });
        toast.success(
          enabled ? "주문 네팅을 활성화했습니다." : "주문 네팅을 비활성화했습니다.",
        );
      } catch (e) {
        toastError("네팅 설정 변경에 실패했습니다.", e);
      } finally {
        setNettingUpdating(false);
      }
    },
    [trading, nettingUpdating],
  );

  const handleRebalance = useCallback(
    async (data: AccountRebalanceRequest) => {
      if (!trading.selectedAccountId) return;
      setIsRebalancing(true);
      try {
        await trading.rebalanceAccount(trading.selectedAccountId, data);
        toast.success("전략 자본을 재배분했습니다.");
        setRebalanceOpen(false);
      } catch (e) {
        toastError("재배분에 실패했습니다.", e);
      } finally {
        setIsRebalancing(false);
      }
    },
    [trading],
  );

  const handleDeposit = useCallback(
    async (data: AccountDepositRequest) => {
      if (!trading.selectedAccountId) return;
      setIsDepositing(true);
      try {
        await trading.depositToAccount(trading.selectedAccountId, data);
        toast.success("입금을 반영했습니다.");
        setDepositOpen(false);
      } catch (e) {
        toastError("입금 반영에 실패했습니다.", e);
      } finally {
        setIsDepositing(false);
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
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold">자동매매</h1>
          {selectedAccount && (
            <Badge
              variant={selectedAccount.mode === "live" ? "default" : "secondary"}
              className={
                selectedAccount.mode === "live"
                  ? "bg-red-500/20 text-red-300 border-red-500/40"
                  : "bg-amber-500/15 text-amber-300 border-amber-500/30"
              }
            >
              {tradingModeLabels[selectedAccount.mode]}
            </Badge>
          )}
        </div>
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
          {selectedAccount && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDepositOpen(true)}
            >
              <Banknote className="size-3.5 mr-1" />
              입금 반영
            </Button>
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
              disabled={nettingUpdating}
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
              {accountStrategies.map((strategy) => {
                const auto = strategy.autoSelectConfig;
                const autoSelected = strategy.autoSelectedTickers;
                const isRefreshingAuto = refreshingAutoIds.has(strategy.id);
                return (
                  <Card key={strategy.id}>
                    <CardContent className="pt-4 pb-4">
                      <div className="flex items-start justify-between">
                        <div className="space-y-2 flex-1 min-w-0">
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
                            {auto.enabled && (
                              <Badge className="bg-sky-500/20 text-sky-300 border-sky-500/30">
                                <Sparkles className="size-3 mr-1" />
                                자동선정 ON · 상위 {auto.topN}
                              </Badge>
                            )}
                          </div>

                          {/* 부가 정보 */}
                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            <span>{strategy.intervalMinutes}분 간격</span>
                            {strategy.marketHoursOnly && <span>장중전용</span>}
                            <span>수동 {strategy.targetTickers.length}종목</span>
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
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-destructive"
                            onClick={() => setPendingDelete(strategy)}
                            title="삭제"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      </div>

                      {/* 자동 선정 결과 (활성화 시) */}
                      {auto.enabled && (
                        <div className="mt-3 rounded-md border border-border/60 bg-muted/30 p-2.5">
                          <div className="flex items-center justify-between gap-2 mb-1.5">
                            <span className="text-xs font-medium text-muted-foreground">
                              자동 선정 종목{" "}
                              {autoSelected ? `(${autoSelected.tickers.length}개)` : "(미생성)"}
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-[11px]"
                              onClick={() => handleRefreshAuto(strategy.id)}
                              disabled={isRefreshingAuto}
                              title="지금 자동 선정 실행"
                            >
                              <RefreshCw
                                className={`size-3 mr-1 ${isRefreshingAuto ? "animate-spin" : ""}`}
                              />
                              {isRefreshingAuto ? "갱신 중..." : "지금 갱신"}
                            </Button>
                          </div>
                          {autoSelected && autoSelected.tickers.length > 0 ? (
                            <>
                              <div className="flex flex-wrap gap-1">
                                {autoSelected.tickers.map((t) => (
                                  <span
                                    key={t}
                                    className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-background border border-border/50"
                                  >
                                    {t}
                                  </span>
                                ))}
                              </div>
                              <p className="mt-1.5 text-[10px] text-muted-foreground">
                                마지막 갱신 {formatTimestamp(autoSelected.generatedAt)} ·{" "}
                                {autoSelected.ruleVersion}
                              </p>
                            </>
                          ) : (
                            <p className="text-[11px] text-muted-foreground">
                              아직 자동 선정 결과가 없습니다. 매일 08:30에 자동 갱신되며, 지금
                              갱신을 눌러 즉시 실행할 수 있습니다.
                            </p>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
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
          onPreviewAuto={trading.previewAutoTickers}
          onRefreshAuto={trading.refreshAutoTickers}
          onLoadAutoHistory={trading.fetchAutoTickerHistory}
          onLoadCapitalSummary={trading.fetchAccountCapitalSummary}
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

      {/* 입금 다이얼로그 */}
      {selectedAccount && (
        <DepositDialog
          open={depositOpen}
          onOpenChange={setDepositOpen}
          account={selectedAccount}
          strategies={accountStrategies}
          onSubmit={handleDeposit}
          isSubmitting={isDepositing}
        />
      )}

      {/* 전략 삭제 확인 */}
      <AlertDialog
        open={!!pendingDelete}
        onOpenChange={(open) => {
          if (!open && !isDeleting) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>전략 삭제</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete
                ? `'${pendingDelete.name}' 전략을 삭제하시겠습니까? 보유 포지션이나 미체결 주문이 있으면 삭제할 수 없으며, 먼저 청산 후 체결이 완료되어야 합니다. 스케줄 이력과 의사결정 로그는 함께 삭제됩니다.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>취소</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleConfirmDelete()}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "삭제 중..." : "삭제"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
