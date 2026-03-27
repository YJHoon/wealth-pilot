"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Search, Loader2 } from "lucide-react";
import { MARKETS, type MarketType } from "@/types";

interface TickerSearchProps {
  onSearch?: (ticker: string, market: MarketType) => void;
}

const POPULAR_TICKERS = [
  { ticker: "005930", name: "삼성전자", market: "KRX" as MarketType },
  { ticker: "000660", name: "SK하이닉스", market: "KRX" as MarketType },
  { ticker: "AAPL", name: "Apple", market: "NASDAQ" as MarketType },
  { ticker: "TSLA", name: "Tesla", market: "NASDAQ" as MarketType },
  { ticker: "NVDA", name: "NVIDIA", market: "NASDAQ" as MarketType },
];

export function TickerSearch({ onSearch }: TickerSearchProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [market, setMarket] = useState<MarketType>(MARKETS[0]);
  const [searching, setSearching] = useState(false);

  const handleSubmit = useCallback(
    async (ticker?: string, mkt?: MarketType) => {
      const t = (ticker ?? query).trim().toUpperCase();
      const m = mkt ?? market;
      if (!t) return;

      setSearching(true);
      try {
        if (onSearch) {
          onSearch(t, m);
        } else {
          await router.push(`/analysis/${encodeURIComponent(t)}?market=${m}`);
        }
      } finally {
        setSearching(false);
      }
    },
    [query, market, onSearch, router],
  );

  return (
    <div className="space-y-4">
      {/* 검색 바 */}
      <div className="flex gap-2">
        <Select value={market} onValueChange={(v) => setMarket(v as MarketType)}>
          <SelectTrigger className="w-28">
            <span>{market}</span>
          </SelectTrigger>
          <SelectContent>
            {MARKETS.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void handleSubmit(); }}
            placeholder="종목코드 또는 티커 입력 (예: 005930, AAPL)"
            className="pl-9"
          />
        </div>
        <Button onClick={() => void handleSubmit()} disabled={!query.trim() || searching}>
          {searching ? <Loader2 className="size-4 animate-spin" /> : "검색"}
        </Button>
      </div>

      {/* 인기 종목 */}
      <div className="flex flex-wrap gap-2">
        <span className="self-center text-xs text-muted-foreground">인기 종목:</span>
        {POPULAR_TICKERS.map((item) => (
          <Badge
            key={item.ticker}
            variant="outline"
            className="cursor-pointer hover:bg-accent"
            onClick={() => void handleSubmit(item.ticker, item.market)}
          >
            {item.name} ({item.ticker})
          </Badge>
        ))}
      </div>
    </div>
  );
}
