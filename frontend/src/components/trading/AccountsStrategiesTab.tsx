"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw } from "@/lib/format";
import {
  type TradingAccount,
  type TradingStrategy,
  tradingModeLabels,
  strategyTypeLabels,
} from "@/types/trading";
import { Play, Square, Zap, Pencil, Trash2, Plus } from "lucide-react";

interface AccountsStrategiesTabProps {
  accounts: TradingAccount[];
  strategies: TradingStrategy[];
  selectedAccountId: string | null;
  onDeactivateAccount: (id: string) => void;
  onToggleNetting?: (accountId: string, enabled: boolean) => void;
  onStartSchedule: (strategyId: string) => void;
  onStopSchedule: (strategyId: string) => void;
  onRunNow: (strategyId: string) => void;
  onEditStrategy: (strategy: TradingStrategy) => void;
  onAddStrategy: () => void;
}

export function AccountsStrategiesTab({
  accounts,
  strategies,
  selectedAccountId,
  onDeactivateAccount,
  onToggleNetting,
  onStartSchedule,
  onStopSchedule,
  onRunNow,
  onEditStrategy,
  onAddStrategy,
}: AccountsStrategiesTabProps) {
  const { isMasked } = useAppStore();

  const selectedAccount = accounts.find((a) => a.id === selectedAccountId);
  const accountStrategies = strategies.filter((s) => s.accountId === selectedAccountId);

  return (
    <div className="space-y-6">
      {/* 계좌 정보 */}
      <section>
        <h3 className="text-sm font-medium text-muted-foreground mb-3">등록된 계좌</h3>
        {accounts.length === 0 ? (
          <p className="text-sm text-muted-foreground">등록된 계좌가 없습니다. 계좌를 등록해주세요.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {accounts.map((account) => (
              <Card
                key={account.id}
                className={account.id === selectedAccountId ? "border-primary" : ""}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={account.mode === "live" ? "destructive" : "secondary"}
                      >
                        {tradingModeLabels[account.mode]}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {formatMaskedKrw(account.initialCapital, isMasked)}
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 text-muted-foreground hover:text-destructive"
                      onClick={() => onDeactivateAccount(account.id)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">초기자금</span>
                    <span className="font-medium">
                      {formatMaskedKrw(account.initialCapital, isMasked)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm mt-1">
                    <span className="text-muted-foreground">상태</span>
                    <Badge variant={account.isActive ? "default" : "secondary"}>
                      {account.isActive ? "활성" : "비활성"}
                    </Badge>
                  </div>
                  {onToggleNetting && (
                    <div className="flex items-center justify-between text-sm mt-1">
                      <span className="text-muted-foreground">주문 네팅</span>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          className="size-3.5 rounded border-border"
                          checked={account.allowNetting}
                          onChange={(e) =>
                            onToggleNetting(account.id, e.target.checked)
                          }
                        />
                        <span className="text-xs text-muted-foreground">
                          {account.allowNetting ? "ON" : "OFF"}
                        </span>
                      </label>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* 전략 목록 */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-muted-foreground">전략 목록</h3>
          {selectedAccount && (
            <Button variant="outline" size="sm" onClick={onAddStrategy}>
              <Plus className="size-3.5 mr-1" />
              전략 추가
            </Button>
          )}
        </div>

        {!selectedAccount ? (
          <p className="text-sm text-muted-foreground">계좌를 선택해주세요.</p>
        ) : accountStrategies.length === 0 ? (
          <p className="text-sm text-muted-foreground">등록된 전략이 없습니다.</p>
        ) : (
          <div className="grid gap-3">
            {accountStrategies.map((strategy) => (
              <Card key={strategy.id}>
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between">
                    <div className="space-y-2 flex-1">
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

                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <span>{strategy.intervalMinutes}분 간격</span>
                        {strategy.marketHoursOnly && <span>장중전용</span>}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 ml-2">
                      {strategy.isScheduled ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 text-red-400 hover:text-red-300"
                          onClick={() => onStopSchedule(strategy.id)}
                          title="중지"
                        >
                          <Square className="size-3.5" />
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 text-emerald-400 hover:text-emerald-300"
                          onClick={() => onStartSchedule(strategy.id)}
                          title="시작"
                        >
                          <Play className="size-3.5" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={() => onRunNow(strategy.id)}
                        title="즉시 실행"
                      >
                        <Zap className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={() => onEditStrategy(strategy)}
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
      </section>
    </div>
  );
}
