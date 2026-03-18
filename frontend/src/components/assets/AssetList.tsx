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
} from "lucide-react";
import type { Asset, AssetType, AssetStatus, PortfolioGroup } from "@/types";
import { useAppStore } from "@/stores/appStore";
import {
  formatAmount,
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

interface AssetListProps {
  assets: Asset[];
  groups: PortfolioGroup[];
  loading: boolean;
  onAddClick: () => void;
  onEditClick: (asset: Asset) => void;
  onSellClick: (asset: Asset) => void;
  onDeleteClick: (asset: Asset) => void;
  onRefreshClick: () => void;
  refreshing?: boolean;
}

type TypeFilter = "all" | AssetType;
type StatusFilter = "all" | AssetStatus;

export function AssetList({
  assets,
  groups,
  loading,
  onAddClick,
  onEditClick,
  onSellClick,
  onDeleteClick,
  onRefreshClick,
  refreshing,
}: AssetListProps) {
  const isMasked = useAppStore((s) => s.isMasked);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [groupFilter, setGroupFilter] = useState<string>("all");

  const groupMap = useMemo(
    () => new Map(groups.map((g) => [g.id, g.name])),
    [groups],
  );

  const filtered = useMemo(() => {
    return assets.filter((a) => {
      if (typeFilter !== "all" && a.type !== typeFilter) return false;
      if (statusFilter !== "all" && a.status !== statusFilter) return false;
      if (groupFilter !== "all") {
        if (groupFilter === "__none__" && a.groupId !== null) return false;
        if (groupFilter !== "__none__" && a.groupId !== groupFilter) return false;
      }
      return true;
    });
  }, [assets, typeFilter, statusFilter, groupFilter]);

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
        <h1 className="text-lg font-semibold">자산 관리</h1>
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

        {/* 그룹 필터 */}
        <Select value={groupFilter} onValueChange={(val) => setGroupFilter(val ?? "all")}>
          <SelectTrigger size="sm" className="w-auto min-w-[120px]">
            <SelectValue placeholder="그룹 필터" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">모든 그룹</SelectItem>
            <SelectItem value="__none__">그룹 없음</SelectItem>
            {groups.map((g) => (
              <SelectItem key={g.id} value={g.id}>
                {g.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

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

      {/* 테이블 */}
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
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>유형</TableHead>
              <TableHead>자산명</TableHead>
              <TableHead>그룹</TableHead>
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

              return (
                <TableRow key={asset.id} className={isSold ? "opacity-60" : ""}>
                  {/* 유형 */}
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      {typeIcons[asset.type]}
                      <span className="text-xs text-muted-foreground hidden sm:inline">
                        {assetTypeLabels[asset.type]}
                      </span>
                    </div>
                  </TableCell>

                  {/* 자산명 */}
                  <TableCell>
                    <div>
                      <span className="font-medium">{asset.name}</span>
                      {asset.ticker && (
                        <span className="ml-1 text-xs text-muted-foreground">
                          ({asset.ticker})
                        </span>
                      )}
                    </div>
                  </TableCell>

                  {/* 그룹 */}
                  <TableCell>
                    {asset.groupId ? (
                      <Badge variant="secondary">
                        {groupMap.get(asset.groupId) ?? "알 수 없음"}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>

                  {/* 수량 */}
                  <TableCell className="text-right font-mono">
                    {formatQuantity(asset.quantity, isMasked)}
                  </TableCell>

                  {/* 매입가 */}
                  <TableCell className="text-right font-mono">
                    {formatAmount(asset.purchasePrice, asset.currency, isMasked)}
                  </TableCell>

                  {/* 현재가 */}
                  <TableCell className="text-right font-mono">
                    {isSold
                      ? formatAmount(asset.soldPrice, asset.currency, isMasked)
                      : asset.currentPrice != null
                        ? formatAmount(asset.currentPrice, asset.currency, isMasked)
                        : <span className="text-muted-foreground text-xs">데이터 없음</span>}
                  </TableCell>

                  {/* 평가손익 */}
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

                  {/* 수익률 */}
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

                  {/* 상태 */}
                  <TableCell className="text-right">
                    <Badge variant={isSold ? "outline" : "default"}>
                      {assetStatusLabels[asset.status]}
                    </Badge>
                  </TableCell>

                  {/* 액션 */}
                  <TableCell>
                    {!isSold && (
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={
                            <Button variant="ghost" size="icon-xs" />
                          }
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
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {/* 하단 카운트 */}
      {!loading && filtered.length > 0 && (
        <p className="text-xs text-muted-foreground">
          총 {filtered.length}개 자산 표시 중
          {filtered.length !== assets.length && ` (전체 ${assets.length}개)`}
        </p>
      )}
    </div>
  );
}
