"use client";

import { AlertTriangle } from "lucide-react";

interface InvestmentDisclaimerProps {
  text?: string;
}

export function InvestmentDisclaimer({ text }: InvestmentDisclaimerProps) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-400" />
      <p>
        {text ||
          "본 분석 정보는 투자 참고용이며, 투자 판단의 최종 책임은 투자자 본인에게 있습니다. 과거 수익률이 미래 수익을 보장하지 않습니다."}
      </p>
    </div>
  );
}
