"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
} from "lucide-react";
import type { AnalysisRun } from "@/types/advisory";
import { runStatusLabels } from "@/types/advisory";
import { cn } from "@/lib/utils";

type StepKey = "queued" | "analyzing" | "ready" | "executing" | "done";

interface Step {
  key: StepKey;
  label: string;
}

const STEPS: Step[] = [
  { key: "queued", label: "대기" },
  { key: "analyzing", label: "후보 분석" },
  { key: "ready", label: "결과 준비" },
  { key: "executing", label: "발주" },
  { key: "done", label: "완료" },
];

function statusToCurrentStep(status: AnalysisRun["status"]): StepKey {
  switch (status) {
    case "pending":
      return "queued";
    case "analyzing":
      return "analyzing";
    case "ready":
      return "ready";
    case "executing":
      return "executing";
    case "done":
      return "done";
    case "failed":
      // 실패는 별도 처리 — 호출자가 분기
      return "queued";
  }
}

function stepIndex(key: StepKey): number {
  return STEPS.findIndex((s) => s.key === key);
}

export interface RunProgressProps {
  run: AnalysisRun;
}

export function RunProgress({ run }: RunProgressProps) {
  const failed = run.status === "failed";
  const currentStep = statusToCurrentStep(run.status);
  const currentIdx = stepIndex(currentStep);
  const startedAt = new Date(run.startedAt);
  const elapsed = Math.max(
    0,
    Math.round((Date.now() - startedAt.getTime()) / 1000),
  );

  return (
    <Card>
      <CardContent className="pt-4 pb-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">진행 상태</span>
            <Badge
              variant={failed ? "destructive" : "secondary"}
              className={
                failed
                  ? ""
                  : run.status === "done"
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                    : "bg-sky-500/15 text-sky-300 border-sky-500/30"
              }
            >
              {runStatusLabels[run.status]}
            </Badge>
          </div>
          <span className="text-[11px] text-muted-foreground">
            경과 {elapsed}s · {startedAt.toLocaleString("ko-KR")}
          </span>
        </div>

        {failed ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive-foreground">
            <XCircle className="size-4 shrink-0" />
            <span>{run.errorMessage ?? "분석에 실패했습니다."}</span>
          </div>
        ) : (
          <ol className="flex items-center gap-2">
            {STEPS.map((step, idx) => {
              const isDone = idx < currentIdx || run.status === "done";
              const isActive =
                idx === currentIdx && run.status !== "done";
              return (
                <li key={step.key} className="flex items-center gap-2">
                  <div
                    className={cn(
                      "flex items-center gap-1.5 text-xs",
                      isDone
                        ? "text-emerald-400"
                        : isActive
                          ? "text-sky-300"
                          : "text-muted-foreground/60",
                    )}
                  >
                    {isDone ? (
                      <CheckCircle2 className="size-4" />
                    ) : isActive ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Circle className="size-4" />
                    )}
                    <span>{step.label}</span>
                  </div>
                  {idx < STEPS.length - 1 && (
                    <span
                      className={cn(
                        "h-px w-6",
                        idx < currentIdx
                          ? "bg-emerald-500/60"
                          : "bg-border",
                      )}
                    />
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
