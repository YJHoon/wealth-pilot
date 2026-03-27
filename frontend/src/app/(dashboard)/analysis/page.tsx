"use client";

import { TickerSearch } from "@/components/analysis/TickerSearch";
import { InvestmentDisclaimer } from "@/components/analysis/InvestmentDisclaimer";

export default function AnalysisPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">종목 분석</h1>

      <InvestmentDisclaimer />

      <TickerSearch />
    </div>
  );
}
