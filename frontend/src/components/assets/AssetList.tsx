"use client";

import { useState, useMemo, useCallback } from "react";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Banknote,
  TrendingUp,
  Globe,
  Bitcoin,
  Building2,
  Plus,
  MoreHorizontal,
  Pencil,
  Trash2,
  ArrowDownToLine,
  RefreshCw,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type {
  Asset,
  AssetType,
  AssetStatus,
  DataFreshness,
  HoldingBreakdown,
  HoldingBreakdownItem,
} from "@/types";
import { useAppStore } from "@/stores/appStore";
import {
  formatAmount,
  formatDualCurrency,
  formatQuantity,
  formatPnl,
  assetTypeLabels,
  assetStatusLabels,
} from "@/lib/format";

// ── 아이콘 매핑 ──

const typeIcons: Record<AssetType, React.ReactNode> = {
  cash: <Banknote className="size-4 text-emerald-500" />,
  domestic_stock: <TrendingUp className="size-4 text-blue-500" />,
  foreign_stock: <Globe className="size-4 text-violet-500" />,
  crypto: <Bitcoin className="size-4 text-amber-500" />,
  real_estate: <Building2 className="size-4 text-rose-500" />,
};

// ── Props ──

// ── 신뢰도 인디케이터 ──

const freshnessConfig: Record<DataFreshness, { icon: string; label: string }> = {
  realtime: { icon: "\uD83D\uDFE2", label: "실시간" },
  delayed: { icon: "\uD83D\uDFE1", label: "15분 지연" },
  batch: { icon: "\uD83D\uDFE0", label: "1일 배치" },
  estimated: { icon: "\uD83D\uDD34", label: "추정치" },
};

interface AssetListProps {
  assets: Asset[];
  loading: boolean;
  breakdown?: HoldingBreakdown;
  onAddClick: () => void;
  onEditClick: (asset: Asset) => void;
  onSellClick: (asset: Asset) => void;
  onDeleteClick: (asset: Asset) => void;
  onRefreshClick: () => void;
  refreshing?: boolean;
  lastRefreshedAt?: string | null;
  priceMode?: DataFreshness | null;
  toKrw?: (amount: number, currency: string) => number | null;
}

type TypeFilter = "all" | AssetType;
type StatusFilter = "all" | AssetStatus;

function AssetActionMenu({
  asset,
  onEditClick,
  onSellClick,
  onDeleteClick,
}: {
  asset: Asset;
  onEditClick: (asset: Asset) => void;
  onSellClick: (asset: Asset) => void;
  onDeleteClick: (asset: Asset) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(buttonVariants({ variant: "ghost", size: "icon-xs" }))}
        aria-label={`${asset.name} 액션 메뉴`}
      >
        <MoreHorizontal className="size-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => onEditClick(asset)}>
          <Pencil className="size-3.5" />
          수정
        </DropdownMenuItem>
        {asset.type !== "cash" && (
          <DropdownMenuItem onClick={() => onSellClick(asset)}>
            <ArrowDownToLine className="size-3.5" />
            매도
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onClick={() => onDeleteClick(asset)}
        >
          <Trash2 className="size-3.5" />
          삭제
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function BreakdownBreakdownCell({
  asset,
  item,
  isMasked,
  onMismatchClick,
}: {
  asset: Asset;
  item: HoldingBreakdownItem | undefined;
  isMasked: boolean;
  onMismatchClick: (item: HoldingBreakdownItem) => void;
}) {
  if (!item || (item.strategyQty === 0 && item.advisoryQty === 0)) {
    return null;
  }
  const quantityLabel = (qty: number) =>
    isMasked ? "●●●●" : qty.toLocaleString("ko-KR", { maximumFractionDigits: 8 });
  return (
    <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
      <span className="font-mono">
        {`전략 ${quantityLabel(item.strategyQty)}주`}
      </span>
      <span>+</span>
      <span className="font-mono">
        {`수동 ${quantityLabel(item.advisoryQty)}주`}
      </span>
      {item.hasMismatch && (
        <button
          type="button"
          onClick={() => onMismatchClick(item)}
          className="ml-1 inline-flex items-center gap-0.5 rounded bg-amber-500/15 px-1 py-0.5 text-[10px] text-amber-600 hover:bg-amber-500/25 dark:text-amber-400"
          aria-label={`${asset.name} 보유량 불일치 상세 보기`}
        >
          <AlertTriangle className="size-3" />
          불일치
        </button>
      )}
    </div>
  );
}

function MismatchDialog({
  item,
  open,
  onOpenChange,
  isMasked,
  assetName,
}: {
  item: HoldingBreakdownItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isMasked: boolean;
  assetName: string;
}) {
  if (!item) return null;
  const quantityLabel = (qty: number | null) => {
    if (qty == null) return "-";
    if (isMasked) return "●●●●";
    return qty.toLocaleString("ko-KR", { maximumFractionDigits: 8 });
  };
  const internalSum = item.strategyQty + item.advisoryQty;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-amber-500" />
            보유량 정합성 불일치
          </DialogTitle>
          <DialogDescription>
            {assetName} ({item.ticker}) — 내부 합계와 KIS 실잔고가 일치하지 않습니다.
            동기화 또는 외부 거래 영향일 수 있습니다.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 rounded-lg border border-border p-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">전략 보유</span>
            <span className="font-mono">{quantityLabel(item.strategyQty)}주</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">수동 보유</span>
            <span className="font-mono">{quantityLabel(item.advisoryQty)}주</span>
          </div>
          <div className="flex justify-between border-t pt-2 text-muted-foreground">
            <span>내부 합계</span>
            <span className="font-mono">{quantityLabel(internalSum)}주</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">KIS 실잔고</span>
            <span className="font-mono">{quantityLabel(item.kisQty)}주</span>
          </div>
          <div className="flex justify-between border-t pt-2 font-medium text-amber-600 dark:text-amber-400">
            <span>차이 (내부 − KIS)</span>
            <span className="font-mono">{quantityLabel(item.mismatchQty)}주</span>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            닫기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AssetList({
  assets,
  loading,
  breakdown,
  onAddClick,
  onEditClick,
  onSellClick,
  onDeleteClick,
  onRefreshClick,
  refreshing,
  lastRefreshedAt,
  priceMode,
  toKrw,
}: AssetListProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [mismatchItem, setMismatchItem] = useState<HoldingBreakdownItem | null>(null);

  const breakdownByTicker = useMemo(() => {
    const map = new Map<string, HoldingBreakdownItem>();
    for (const item of breakdown?.items ?? []) {
      // 같은 ticker가 여러 계좌에 있으면 mismatch 있는 쪽을 우선 표시.
      const existing = map.get(item.ticker);
      if (!existing || (!existing.hasMismatch && item.hasMismatch)) {
        map.set(item.ticker, item);
      }
    }
    return map;
  }, [breakdown]);
  const mismatchCount = breakdown?.items.filter((i) => i.hasMismatch).length ?? 0;

  const filtered = useMemo(() => {
    return assets.filter((a) => {
      if (typeFilter !== "all" && a.type !== typeFilter) return false;
      if (statusFilter !== "all" && a.status !== statusFilter) return false;
      return true;
    });
  }, [assets, typeFilter, statusFilter]);

  const computePnl = useCallback((asset: Asset) => {
    if (asset.status === "sold" && asset.realizedPnl != null) {
      return asset.realizedPnl;
    }
    if (asset.currentPrice == null) return null;
    return (asset.currentPrice - asset.purchasePrice) * asset.quantity;
  }, []);

  const computePnlRate = useCallback((asset: Asset) => {
    const pnl = computePnl(asset);
    if (pnl == null) return null;
    const cost = asset.purchasePrice * asset.quantity;
    if (cost === 0) return null;
    return (pnl / cost) * 100;
  }, [computePnl]);

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">자산 관리</h1>
          {priceMode && (
            <span className="text-xs text-muted-foreground">
              {freshnessConfig[priceMode].icon} {freshnessConfig[priceMode].label}
            </span>
          )}
          {lastRefreshedAt && (
            <span className="text-xs text-muted-foreground">
              마지막 갱신: {new Date(lastRefreshedAt).toLocaleString("ko-KR", {
                year: "numeric", month: "2-digit", day: "2-digit",
                hour: "2-digit", minute: "2-digit",
              })}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onRefreshClick} disabled={refreshing}>
            {refreshing ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            시세 갱신
          </Button>
          <Button size="sm" onClick={onAddClick}>
            <Plus className="size-3.5" />
            자산 추가
          </Button>
        </div>
      </div>

      {mismatchCount > 0 && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">
              {mismatchCount}개 종목의 내부 보유량이 KIS 실잔고와 일치하지 않습니다.
            </p>
            <p className="text-amber-700/80 dark:text-amber-300/80">
              종목별 &quot;불일치&quot; 배지를 클릭해 상세 차이를 확인하세요. 잔고를 다시 동기화하거나 수동 매매가 있었는지 점검해 주세요.
            </p>
          </div>
        </div>
      )}

      {/* 필터 */}
      <div className="flex flex-wrap items-center gap-3">
        {/* 유형 탭 */}
        <Tabs
          value={typeFilter}
          onValueChange={(val) => { if (val != null) setTypeFilter(val as TypeFilter); }}
        >
          <TabsList variant="line">
            <TabsTrigger value="all">전체</TabsTrigger>
            {Object.entries(assetTypeLabels).map(([key, label]) => (
              <TabsTrigger key={key} value={key}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* 상태 필터 */}
        <Select value={statusFilter} onValueChange={(val) => setStatusFilter((val ?? "all") as StatusFilter)}>
          <SelectTrigger size="sm" className="w-auto min-w-[100px]">
            <SelectValue placeholder="상태" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 상태</SelectItem>
            {Object.entries(assetStatusLabels).map(([key, label]) => (
              <SelectItem key={key} value={key}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 자산 목록 */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="size-5 animate-spin mr-2" />
          자산 목록을 불러오는 중...
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <p>등록된 자산이 없습니다.</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={onAddClick}>
            <Plus className="size-3.5" />
            첫 자산 등록하기
          </Button>
        </div>
      ) : (
        <>
          {/* 모바일: 카드 레이아웃 */}
          <div className="space-y-3 md:hidden">
            {filtered.map((asset) => {
              const pnl = computePnl(asset);
              const rate = computePnlRate(asset);
              const isSold = asset.status === "sold";

              const isKis = asset.source === "kis";
              return (
                <div
                  key={asset.id}
                  className={`rounded-lg border border-border bg-card p-3 ${isSold ? "opacity-60" : ""}`}
                >
                  {/* 카드 상단: 유형 아이콘 + 자산명 + 액션 */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {typeIcons[asset.type]}
                      <div>
                        <span className="text-sm font-medium">{asset.name}</span>
                        {asset.ticker && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            ({asset.ticker})
                          </span>
                        )}
                        {isKis && (
                          <Badge variant="outline" className="ml-1.5 text-[10px] px-1 py-0 h-4">
                            KIS
                          </Badge>
                        )}
                        {asset.ticker && (
                          <BreakdownBreakdownCell
                            asset={asset}
                            item={breakdownByTicker.get(asset.ticker)}
                            isMasked={isMasked}
                            onMismatchClick={setMismatchItem}
                          />
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge variant={isSold ? "outline" : "default"}>
                        {assetStatusLabels[asset.status]}
                      </Badge>
                      {!isSold && !isKis && (
                        <AssetActionMenu
                          asset={asset}
                          onEditClick={onEditClick}
                          onSellClick={onSellClick}
                          onDeleteClick={onDeleteClick}
                        />
                      )}
                    </div>
                  </div>

                  {/* 카드 하단: 주요 수치 */}
                  <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div className="text-muted-foreground">수량</div>
                    <div className="text-right font-mono">
                      {formatQuantity(asset.quantity, isMasked)}
                    </div>
                    <div className="text-muted-foreground">현재가</div>
                    <div className="text-right font-mono">
                      {isSold
                        ? formatAmount(asset.soldPrice, asset.currency, isMasked)
                        : asset.currentPrice != null
                          ? asset.currency !== "KRW" && toKrw
                            ? formatDualCurrency(
                                asset.currentPrice,
                                asset.currency,
                                toKrw(asset.currentPrice, asset.currency),
                                isMasked,
                              )
                            : formatAmount(asset.currentPrice, asset.currency, isMasked)
                          : <span className="text-muted-foreground text-xs">데이터를 가져올 수 없습니다</span>}
                    </div>
                    <div className="text-muted-foreground">손익</div>
                    <div className="text-right font-mono">
                      {isMasked ? (
                        "●●●●●●원"
                      ) : pnl != null ? (
                        <span className={pnl >= 0 ? "text-emerald-500" : "text-red-500"}>
                          {formatPnl(pnl, asset.currency, false)}
                        </span>
                      ) : (
                        "-"
                      )}
                    </div>
                    <div className="text-muted-foreground">수익률</div>
                    <div className="text-right font-mono">
                      {isMasked ? (
                        "●●●●%"
                      ) : rate != null ? (
                        <span className={rate >= 0 ? "text-emerald-500" : "text-red-500"}>
                          {rate >= 0 ? "+" : ""}{rate.toFixed(2)}%
                        </span>
                      ) : (
                        "-"
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 데스크톱: 테이블 레이아웃 */}
          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>유형</TableHead>
                  <TableHead>자산명</TableHead>
                  <TableHead className="text-right">수량</TableHead>
                  <TableHead className="text-right">매입가</TableHead>
                  <TableHead className="text-right">현재가</TableHead>
                  <TableHead className="text-right">평가손익</TableHead>
                  <TableHead className="text-right">수익률</TableHead>
                  <TableHead className="text-right">상태</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((asset) => {
                  const pnl = computePnl(asset);
                  const rate = computePnlRate(asset);
                  const isSold = asset.status === "sold";
                  const isKis = asset.source === "kis";

                  return (
                    <TableRow key={asset.id} className={isSold ? "opacity-60" : ""}>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          {typeIcons[asset.type]}
                          <span className="text-xs text-muted-foreground">
                            {assetTypeLabels[asset.type]}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium">{asset.name}</span>
                          {asset.ticker && (
                            <span className="text-xs text-muted-foreground">
                              ({asset.ticker})
                            </span>
                          )}
                          {isKis && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0 h-4">
                              KIS
                            </Badge>
                          )}
                        </div>
                        {asset.ticker && (
                          <BreakdownBreakdownCell
                            asset={asset}
                            item={breakdownByTicker.get(asset.ticker)}
                            isMasked={isMasked}
                            onMismatchClick={setMismatchItem}
                          />
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatQuantity(asset.quantity, isMasked)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {asset.currency !== "KRW" && toKrw
                          ? formatDualCurrency(
                              asset.purchasePrice,
                              asset.currency,
                              toKrw(asset.purchasePrice, asset.currency),
                              isMasked,
                            )
                          : formatAmount(asset.purchasePrice, asset.currency, isMasked)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {isSold
                          ? formatAmount(asset.soldPrice, asset.currency, isMasked)
                          : asset.currentPrice != null
                            ? asset.currency !== "KRW" && toKrw
                              ? formatDualCurrency(
                                  asset.currentPrice,
                                  asset.currency,
                                  toKrw(asset.currentPrice, asset.currency),
                                  isMasked,
                                )
                              : formatAmount(asset.currentPrice, asset.currency, isMasked)
                            : <span className="text-muted-foreground text-xs">데이터를 가져올 수 없습니다</span>}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {isMasked ? (
                          "●●●●●●원"
                        ) : pnl != null ? (
                          <span className={pnl >= 0 ? "text-emerald-500" : "text-red-500"}>
                            {formatPnl(pnl, asset.currency, false)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {isMasked ? (
                          "●●●●%"
                        ) : rate != null ? (
                          <span className={rate >= 0 ? "text-emerald-500" : "text-red-500"}>
                            {rate >= 0 ? "+" : ""}{rate.toFixed(2)}%
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge variant={isSold ? "outline" : "default"}>
                          {assetStatusLabels[asset.status]}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {!isSold && !isKis && (
                          <AssetActionMenu
                            asset={asset}
                            onEditClick={onEditClick}
                            onSellClick={onSellClick}
                            onDeleteClick={onDeleteClick}
                          />
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </>
      )}

      {/* 하단 카운트 */}
      {!loading && filtered.length > 0 && (
        <p className="text-xs text-muted-foreground">
          총 {filtered.length}개 자산 표시 중
          {filtered.length !== assets.length && ` (전체 ${assets.length}개)`}
        </p>
      )}

      <MismatchDialog
        open={!!mismatchItem}
        onOpenChange={(open) => {
          if (!open) setMismatchItem(null);
        }}
        item={mismatchItem}
        isMasked={isMasked}
        assetName={
          mismatchItem
            ? assets.find((a) => a.ticker === mismatchItem.ticker)?.name ??
              mismatchItem.tickerName ??
              mismatchItem.ticker
            : ""
        }
      />
    </div>
  );
}
