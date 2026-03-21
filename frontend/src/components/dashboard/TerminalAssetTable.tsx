"use client";

import {
  TrendingUp,
  TrendingDown,
  Minus,
  Banknote,
  BarChart3,
  Globe,
  Bitcoin,
  Home,
} from "lucide-react";
import type { Asset, AssetType } from "@/types";
import { useAppStore } from "@/stores/appStore";
import {
  formatAmount,
  formatDualCurrency,
  formatQuantity,
  formatPercent,
  pnlColorClass,
} from "@/lib/format";
import { toKrwRate } from "@/hooks/useDashboardData";

const typeIcons: Record<AssetType, React.ReactNode> = {
  cash: <Banknote className="h-3.5 w-3.5 text-yellow-400" />,
  domestic_stock: <BarChart3 className="h-3.5 w-3.5 text-blue-400" />,
  foreign_stock: <Globe className="h-3.5 w-3.5 text-purple-400" />,
  crypto: <Bitcoin className="h-3.5 w-3.5 text-orange-400" />,
  real_estate: <Home className="h-3.5 w-3.5 text-teal-400" />,
};

function getChangePercent(asset: Asset): number {
  if (asset.currentPrice == null || asset.type === "cash") return 0;
  return ((asset.currentPrice - asset.purchasePrice) / asset.purchasePrice) * 100;
}

function getEvalKrw(asset: Asset): number {
  const price = asset.currentPrice ?? asset.purchasePrice;
  if (asset.type === "cash") return asset.purchasePrice * asset.quantity;
  const rate = toKrwRate(asset.currency);
  return price * asset.quantity * rate;
}

function getPnlKrw(asset: Asset): number {
  if (asset.type === "cash") return 0;
  const evalKrw = getEvalKrw(asset);
  const rate = toKrwRate(asset.currency);
  const costKrw = asset.purchasePrice * asset.quantity * rate;
  return evalKrw - costKrw;
}

interface Props {
  assets: Asset[];
}

export function TerminalAssetTable({ assets }: Props) {
  const { isMasked } = useAppStore();
  const active = assets.filter((a) => a.status === "active");

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          보유 자산
        </h3>
        <span className="text-xs text-muted-foreground">{active.length}종목</span>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-card">
            <tr className="text-muted-foreground border-b border-border">
              <th className="text-left py-1.5 px-3 font-medium">종목</th>
              <th className="text-right py-1.5 px-2 font-medium">현재가</th>
              <th className="text-right py-1.5 px-2 font-medium">변동</th>
              <th className="text-right py-1.5 px-2 font-medium">수량</th>
              <th className="text-right py-1.5 px-3 font-medium">평가액</th>
            </tr>
          </thead>
          <tbody className="font-[family-name:var(--font-geist-mono)]">
            {active.map((asset) => {
              const changePercent = getChangePercent(asset);
              const evalKrw = getEvalKrw(asset);
              const colorClass = pnlColorClass(changePercent);

              return (
                <tr
                  key={asset.id}
                  className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                >
                  {/* 종목명 */}
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-1.5">
                      {typeIcons[asset.type]}
                      <div>
                        <div className="font-medium text-foreground truncate max-w-[100px]">
                          {asset.name}
                        </div>
                        {asset.ticker && (
                          <div className="text-[10px] text-muted-foreground">
                            {asset.ticker}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>

                  {/* 현재가 */}
                  <td className="py-2 px-2 text-right text-foreground">
                    {asset.type === "cash"
                      ? "-"
                      : formatAmount(asset.currentPrice, asset.currency, isMasked)}
                  </td>

                  {/* 변동률 */}
                  <td className={`py-2 px-2 text-right ${colorClass}`}>
                    <div className="flex items-center justify-end gap-0.5">
                      {changePercent > 0 ? (
                        <TrendingUp className="h-3 w-3" />
                      ) : changePercent < 0 ? (
                        <TrendingDown className="h-3 w-3" />
                      ) : (
                        <Minus className="h-3 w-3" />
                      )}
                      {asset.type === "cash" ? "-" : formatPercent(changePercent)}
                    </div>
                  </td>

                  {/* 수량 */}
                  <td className="py-2 px-2 text-right text-foreground">
                    {asset.type === "cash"
                      ? "-"
                      : formatQuantity(asset.quantity, isMasked)}
                  </td>

                  {/* 평가액 */}
                  <td className="py-2 px-3 text-right">
                    <div className="text-foreground">
                      {isMasked
                        ? "●●●●●●원"
                        : asset.currency !== "KRW" && asset.type !== "cash"
                          ? formatDualCurrency(
                              (asset.currentPrice ?? asset.purchasePrice) * asset.quantity,
                              asset.currency,
                              evalKrw,
                              isMasked,
                            )
                          : formatAmount(evalKrw, "KRW", isMasked)}
                    </div>
                    {!isMasked && asset.type !== "cash" && (
                      <div className={`text-[10px] ${pnlColorClass(getPnlKrw(asset))}`}>
                        {getPnlKrw(asset) >= 0 ? "+" : ""}
                        {Math.round(getPnlKrw(asset)).toLocaleString("ko-KR")}원
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
