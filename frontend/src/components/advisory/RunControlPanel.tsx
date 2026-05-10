"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import type { TradingAccount, TradingMode } from "@/types/trading";
import { tradingModeLabels } from "@/types/trading";
import type { CandidatePoolOptions } from "@/types/advisory";
import { Sparkles } from "lucide-react";

const DEFAULT_TOP_N = 10;
const DEFAULT_MIN_VOLUME_VALUE = 10_000_000_000; // 100억
const DEFAULT_BUDGET = 1_000_000;

export interface RunControlPanelProps {
  accounts: TradingAccount[];
  disabled: boolean;
  isCreating: boolean;
  inFlightStatusLabel: string | null;
  onSubmit: (data: {
    accountId: string;
    mode: TradingMode;
    budgetKrw: number;
    options: CandidatePoolOptions;
  }) => void;
}

export function RunControlPanel({
  accounts,
  disabled,
  isCreating,
  inFlightStatusLabel,
  onSubmit,
}: RunControlPanelProps) {
  const liveAccount = accounts.find((a) => a.mode === "live" && a.isActive);
  const paperAccount = accounts.find((a) => a.mode === "paper" && a.isActive);
  const initialAccount =
    liveAccount ?? paperAccount ?? accounts.find((a) => a.isActive) ?? accounts[0] ?? null;

  const [accountId, setAccountId] = useState<string>(initialAccount?.id ?? "");
  const [mode, setMode] = useState<TradingMode>(initialAccount?.mode ?? "paper");
  const [budget, setBudget] = useState<string>(String(DEFAULT_BUDGET));
  const [topN, setTopN] = useState<string>(String(DEFAULT_TOP_N));
  const [market, setMarket] = useState<"KOSPI" | "KOSDAQ" | "ALL">("ALL");
  const [minVolume, setMinVolume] = useState<string>(String(DEFAULT_MIN_VOLUME_VALUE));
  const [blacklistText, setBlacklistText] = useState<string>("");

  const handleSelectAccount = (id: string | null) => {
    if (!id) return;
    setAccountId(id);
    const next = accounts.find((a) => a.id === id);
    if (next) setMode(next.mode);
  };

  const budgetNum = Number(budget);
  const topNNum = Number(topN);
  const minVolumeNum = Number(minVolume);
  const isValid =
    !!accountId &&
    Number.isFinite(budgetNum) &&
    budgetNum > 0 &&
    Number.isFinite(topNNum) &&
    topNNum >= 1 &&
    topNNum <= 20 &&
    Number.isFinite(minVolumeNum) &&
    minVolumeNum >= 0;

  const handleSubmit = () => {
    if (!isValid) return;
    const blacklist = blacklistText
      .split(/[,\s]+/)
      .map((t) => t.trim())
      .filter(Boolean);
    onSubmit({
      accountId,
      mode,
      budgetKrw: budgetNum,
      options: {
        top_n: topNNum,
        market,
        min_volume_value: minVolumeNum,
        blacklist,
      },
    });
  };

  return (
    <Card>
      <CardContent className="pt-4 pb-4 space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-sky-400" />
          <span className="text-sm font-semibold">원클릭 분석 실행</span>
          {inFlightStatusLabel && (
            <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/30">
              {inFlightStatusLabel}
            </Badge>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          {/* 계좌 */}
          <div className="space-y-1.5">
            <Label className="text-xs">계좌</Label>
            <Select value={accountId} onValueChange={handleSelectAccount}>
              <SelectTrigger className="w-full">
                <span>
                  {accountId
                    ? tradingModeLabels[
                        accounts.find((a) => a.id === accountId)?.mode ?? "paper"
                      ]
                    : "계좌 선택"}
                </span>
              </SelectTrigger>
              <SelectContent>
                {accounts.length === 0 ? (
                  <SelectItem value="" disabled>
                    등록된 계좌 없음
                  </SelectItem>
                ) : (
                  accounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {tradingModeLabels[a.mode]}
                      {!a.isActive ? " (비활성)" : ""}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">
              실거래(live)는 발주 시 2FA 코드가 필요합니다.
            </p>
          </div>

          {/* 예산 */}
          <div className="space-y-1.5">
            <Label className="text-xs">1회 예산 (KRW)</Label>
            <Input
              type="number"
              inputMode="numeric"
              min={1}
              step={10000}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">
              승인된 매수 항목의 합이 이 예산을 넘지 않도록 분석 단계에서 컷됩니다.
            </p>
          </div>

          {/* 후보풀 — 종목 수 */}
          <div className="space-y-1.5">
            <Label className="text-xs">후보 종목 수 (N, 1~20)</Label>
            <Input
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              step={1}
              value={topN}
              onChange={(e) => setTopN(e.target.value)}
            />
          </div>

          {/* 후보풀 — 시장 */}
          <div className="space-y-1.5">
            <Label className="text-xs">시장</Label>
            <Select
              value={market}
              onValueChange={(v) => setMarket(v as typeof market)}
            >
              <SelectTrigger className="w-full">
                <span>{market}</span>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">ALL (코스피+코스닥)</SelectItem>
                <SelectItem value="KOSPI">KOSPI</SelectItem>
                <SelectItem value="KOSDAQ">KOSDAQ</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* 후보풀 — 거래대금 하한 */}
          <div className="space-y-1.5">
            <Label className="text-xs">거래대금 하한 (원)</Label>
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              step={1000000000}
              value={minVolume}
              onChange={(e) => setMinVolume(e.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">
              일평균 거래대금이 이 값 미만인 종목은 자동선정에서 제외됩니다.
            </p>
          </div>

          {/* 후보풀 — 블랙리스트 */}
          <div className="space-y-1.5">
            <Label className="text-xs">블랙리스트 (쉼표/공백 구분)</Label>
            <Input
              type="text"
              placeholder="예: 005930, 000660"
              value={blacklistText}
              onChange={(e) => setBlacklistText(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={disabled || !isValid || isCreating}
          >
            {isCreating ? "분석 시작 중..." : "분석 실행"}
          </Button>
          {disabled && !isCreating && (
            <span className="text-xs text-muted-foreground">
              진행 중인 분석이 끝나면 다시 실행할 수 있습니다.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
