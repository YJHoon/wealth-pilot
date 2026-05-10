"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { useTrading } from "@/hooks/useTrading";
import { useAdvisory } from "@/hooks/useAdvisory";
import { RunControlPanel } from "@/components/advisory/RunControlPanel";
import { RunProgress } from "@/components/advisory/RunProgress";
import { ResultCardList } from "@/components/advisory/ResultCardList";
import { ExecuteDialog } from "@/components/advisory/ExecuteDialog";
import { RunHistoryList } from "@/components/advisory/RunHistoryList";
import { InvestmentDisclaimer } from "@/components/analysis/InvestmentDisclaimer";
import {
  isRunInProgress,
  runStatusLabels,
  type AnalysisItemDecision,
} from "@/types/advisory";
import { Bot, Hourglass, RotateCcw, Sparkles } from "lucide-react";

function toastError(fallback: string, err: unknown) {
  const detail = err instanceof ApiError ? err.message : null;
  toast.error(detail ? `${fallback}: ${detail}` : fallback);
}

export default function AdvisoryPage() {
  const trading = useTrading();
  const advisory = useAdvisory();

  const [tab, setTab] = useState<"runner" | "history">("runner");
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());
  const [executeOpen, setExecuteOpen] = useState(false);

  const run = advisory.run;
  const inProgress = !!run && isRunInProgress(run.status);
  const isReady = !!run && run.status === "ready" && !run.expired;
  const isExpired = !!run && run.expired;

  // run 이 바뀌면 선택 초기화
  useEffect(() => {
    setSelectedItemIds(new Set());
  }, [run?.id]);

  const handleToggleItem = useCallback(
    (itemId: string, checked: boolean) => {
      setSelectedItemIds((prev) => {
        const next = new Set(prev);
        if (checked) next.add(itemId);
        else next.delete(itemId);
        return next;
      });
    },
    [],
  );

  const handleCreateRun = useCallback(
    async (data: {
      accountId: string;
      mode: "paper" | "live";
      budgetKrw: number;
      options: Parameters<typeof advisory.createRun>[0]["candidate_pool_options"];
    }) => {
      try {
        await advisory.createRun({
          account_id: data.accountId,
          mode: data.mode,
          budget_krw: data.budgetKrw,
          candidate_pool_options: data.options,
        });
        toast.success("분석을 시작했습니다.");
        await advisory.refreshHistory();
      } catch (e) {
        toastError("분석 시작에 실패했습니다.", e);
      }
    },
    [advisory],
  );

  const handleSubmitAndExecute = useCallback(async () => {
    if (!run) return;
    if (selectedItemIds.size === 0) {
      toast.error("발주할 종목을 1개 이상 선택하세요.");
      return;
    }
    // 1) 선택 항목 → APPROVED, 미선택(pending) → REJECTED 일괄 저장
    const decisions = run.items
      .filter((item) => item.decision === "pending")
      .filter(
        (item) => item.action === "buy" || item.action === "sell",
      )
      .map((item) => ({
        item_id: item.id,
        decision: (selectedItemIds.has(item.id)
          ? "approved"
          : "rejected") as Exclude<AnalysisItemDecision, "pending" | "skipped">,
      }));
    if (decisions.length === 0) {
      toast.error("결정 가능한 항목이 없습니다.");
      return;
    }
    try {
      await advisory.submitDecisions(run.id, { decisions });
      setExecuteOpen(true);
    } catch (e) {
      toastError("결정 저장에 실패했습니다.", e);
    }
  }, [run, selectedItemIds, advisory]);

  const handleExecuteConfirm = useCallback(
    async (totpCode?: string) => {
      if (!run) return;
      try {
        const res = await advisory.executeRun(run.id, { totp_code: totpCode });
        setExecuteOpen(false);
        if (res.failed === 0) {
          toast.success(`발주 완료: ${res.executed}건`);
        } else {
          toast.warning(`발주 ${res.executed}건 성공 / ${res.failed}건 실패`);
        }
        await advisory.refreshHistory();
      } catch (e) {
        toastError("발주에 실패했습니다.", e);
      }
    },
    [run, advisory],
  );

  const handleSelectHistory = useCallback(
    async (runId: string) => {
      setTab("runner");
      try {
        await advisory.loadRun(runId);
      } catch (e) {
        toastError("선택한 분석을 불러오지 못했습니다.", e);
      }
    },
    [advisory],
  );

  const handleResetForNewRun = useCallback(() => {
    advisory.setActiveRun(null);
    setSelectedItemIds(new Set());
  }, [advisory]);

  const approvedItems = useMemo(() => {
    if (!run) return [];
    return run.items.filter(
      (item) =>
        selectedItemIds.has(item.id) &&
        item.decision === "pending" &&
        (item.action === "buy" || item.action === "sell"),
    );
  }, [run, selectedItemIds]);

  const inFlightLabel = inProgress
    ? `${runStatusLabels[run!.status]} 진행 중`
    : null;

  // 결과 카드의 readonly: 발주 후 상태이거나 만료된 경우
  const resultReadOnly =
    !run ||
    run.status !== "ready" ||
    run.expired === true;

  // 실행 패널 disabled: 진행 중 OR 결과 검토 중(READY) — 결과 처리 후 다시 실행
  const submitDisabled = inProgress || isReady;

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Sparkles className="size-5 text-sky-400" />
          <h1 className="text-xl font-bold">원클릭 분석·매매</h1>
        </div>
        <p className="text-xs text-muted-foreground">
          버튼 한 번으로 보유 종목과 자동선정 후보를 LLM 분석 → 종목별 승인 후 발주.
          자동매매 전략과 포지션이 분리되어 사고 반경이 격리됩니다.
        </p>
      </div>

      <InvestmentDisclaimer />

      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          <TabsTrigger value="runner">실행</TabsTrigger>
          <TabsTrigger value="history">이력</TabsTrigger>
        </TabsList>

        <TabsContent value="runner" className="space-y-4">
          {/* 계좌 미등록 안내 */}
          {trading.accounts.length === 0 && !trading.loading.accounts ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Bot className="size-10 mb-3 opacity-40" />
              <p className="text-sm font-medium mb-1">등록된 계좌가 없습니다</p>
              <p className="text-xs mb-4">
                원클릭 분석을 시작하려면 먼저 내 자산 페이지에서 KIS 계좌를 등록해주세요.
              </p>
              <Link
                href="/assets"
                className="inline-flex items-center rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent transition-colors"
              >
                내 자산에서 계좌 등록하기
              </Link>
            </div>
          ) : (
            <>
              <RunControlPanel
                accounts={trading.accounts}
                disabled={submitDisabled}
                isCreating={advisory.loading.creating}
                inFlightStatusLabel={inFlightLabel}
                onSubmit={handleCreateRun}
              />

              {run && (
                <>
                  <RunProgress run={run} />

                  {/* 만료/실패 안내 */}
                  {(isExpired || run.status === "failed") && (
                    <Card>
                      <CardContent className="pt-4 pb-4 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 text-sm">
                          <Hourglass className="size-4 text-amber-400" />
                          {isExpired
                            ? "결과 유효기간이 만료되었습니다. 재분석이 필요합니다."
                            : `분석에 실패했습니다${run.errorMessage ? `: ${run.errorMessage}` : "."}`}
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={handleResetForNewRun}
                        >
                          <RotateCcw className="size-3.5 mr-1" />
                          재분석 준비
                        </Button>
                      </CardContent>
                    </Card>
                  )}

                  {run.items.length > 0 && (
                    <ResultCardList
                      items={run.items}
                      selectedIds={selectedItemIds}
                      onToggle={handleToggleItem}
                      readOnly={resultReadOnly}
                    />
                  )}

                  {/* 결과 발주 버튼 — READY + 미만료일 때만 활성 */}
                  {isReady && (
                    <Card>
                      <CardContent className="pt-3 pb-3 flex items-center justify-between gap-3">
                        <div className="text-xs text-muted-foreground">
                          선택한 {selectedItemIds.size}개 항목을 발주합니다. TTL{" "}
                          {run.expiresAt
                            ? new Date(run.expiresAt).toLocaleTimeString("ko-KR")
                            : "-"}{" "}
                          까지.
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleResetForNewRun}
                          >
                            새 분석
                          </Button>
                          <Button
                            size="sm"
                            onClick={handleSubmitAndExecute}
                            disabled={
                              selectedItemIds.size === 0 ||
                              advisory.loading.submittingDecisions ||
                              advisory.loading.executing
                            }
                          >
                            {advisory.loading.submittingDecisions
                              ? "결정 저장 중..."
                              : "선택 항목 발주"}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {run.status === "done" && (
                    <Card>
                      <CardContent className="pt-3 pb-3 flex items-center justify-between gap-3">
                        <span className="text-xs text-muted-foreground">
                          발주가 완료되었습니다. 매매 내역에서 체결 상태를 확인하세요.
                        </span>
                        <div className="flex items-center gap-2">
                          <Link
                            href="/orders"
                            className="text-xs underline-offset-2 hover:underline"
                          >
                            매매 내역 →
                          </Link>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleResetForNewRun}
                          >
                            <RotateCcw className="size-3.5 mr-1" />
                            새 분석
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="history" className="space-y-3">
          <RunHistoryList
            items={advisory.history?.items ?? null}
            loading={advisory.loading.history}
            activeRunId={run?.id ?? null}
            onSelect={handleSelectHistory}
            onRefresh={() => {
              advisory.refreshHistory().catch(() => {});
            }}
          />
        </TabsContent>
      </Tabs>

      {/* 발주 확인 다이얼로그 */}
      {run && (
        <ExecuteDialog
          open={executeOpen}
          onOpenChange={(open) => {
            if (!advisory.loading.executing) setExecuteOpen(open);
          }}
          mode={run.mode}
          approvedItems={approvedItems}
          isExecuting={advisory.loading.executing}
          onConfirm={handleExecuteConfirm}
        />
      )}
    </div>
  );
}
