"use client";

import { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw, formatQuantity } from "@/lib/format";
import type { TradingOrder, OrderSide, OrderStatus } from "@/types/trading";
import { orderSideLabels, orderStatusLabels } from "@/types/trading";
import type { OrderFilters } from "@/hooks/useTrading";
import { ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 50;

const statusColors: Record<OrderStatus, string> = {
  pending: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  submitted: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  filled: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  partial: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  cancelled: "bg-red-500/20 text-red-400 border-red-500/30",
  rejected: "bg-red-500/20 text-red-400 border-red-500/30",
};

interface OrdersTabProps {
  orders: TradingOrder[];
  loading: boolean;
  onRefetch: (filters?: OrderFilters) => Promise<void>;
}

export function OrdersTab({ orders, loading, onRefetch }: OrdersTabProps) {
  const { isMasked } = useAppStore();
  const [sideFilter, setSideFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [offset, setOffset] = useState(0);

  const handleFilterChange = (side: string, status: string, newOffset: number) => {
    const filters: OrderFilters = { limit: PAGE_SIZE, offset: newOffset };
    if (side !== "all") filters.side = side as OrderSide;
    if (status !== "all") filters.status = status as OrderStatus;
    onRefetch(filters);
  };

  const handleSideChange = (val: string | null) => {
    const v = val ?? "all";
    setSideFilter(v);
    setOffset(0);
    handleFilterChange(v, statusFilter, 0);
  };

  const handleStatusChange = (val: string | null) => {
    const v = val ?? "all";
    setStatusFilter(v);
    setOffset(0);
    handleFilterChange(sideFilter, v, 0);
  };

  const handlePrev = () => {
    const newOffset = Math.max(0, offset - PAGE_SIZE);
    setOffset(newOffset);
    handleFilterChange(sideFilter, statusFilter, newOffset);
  };

  const handleNext = () => {
    const newOffset = offset + PAGE_SIZE;
    setOffset(newOffset);
    handleFilterChange(sideFilter, statusFilter, newOffset);
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  };

  return (
    <div className="space-y-4">
      {/* 필터 */}
      <div className="flex items-center gap-3">
        <Select value={sideFilter} onValueChange={handleSideChange}>
          <SelectTrigger className="w-28">
            <span>{sideFilter === "all" ? "전체" : orderSideLabels[sideFilter as OrderSide]}</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체</SelectItem>
            <SelectItem value="buy">매수</SelectItem>
            <SelectItem value="sell">매도</SelectItem>
          </SelectContent>
        </Select>

        <Select value={statusFilter} onValueChange={handleStatusChange}>
          <SelectTrigger className="w-28">
            <span>
              {statusFilter === "all" ? "전체 상태" : orderStatusLabels[statusFilter as OrderStatus]}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 상태</SelectItem>
            {Object.entries(orderStatusLabels).map(([val, label]) => (
              <SelectItem key={val} value={val}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground py-8 text-center">불러오는 중...</p>
      ) : orders.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">주문내역이 없습니다.</p>
      ) : (
        <>
          {/* 모바일: 카드 */}
          <div className="space-y-3 md:hidden">
            {orders.map((order) => (
              <Card key={order.id}>
                <CardContent className="pt-3 pb-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={
                          order.side === "buy"
                            ? "text-red-400 border-red-500/30"
                            : "text-blue-400 border-blue-500/30"
                        }
                      >
                        {orderSideLabels[order.side]}
                      </Badge>
                      <span className="font-medium text-sm">{order.tickerName}</span>
                      <span className="text-xs text-muted-foreground font-mono">
                        {order.ticker}
                      </span>
                    </div>
                    <Badge variant="outline" className={statusColors[order.status]}>
                      {orderStatusLabels[order.status]}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 text-xs">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">수량</span>
                      <span>{formatQuantity(order.quantity, isMasked)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">주문가</span>
                      <span>{formatMaskedKrw(order.price, isMasked)}</span>
                    </div>
                    {order.filledPrice != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">체결가</span>
                        <span>{formatMaskedKrw(order.filledPrice, isMasked)}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">일시</span>
                      <span>{formatDate(order.createdAt)}</span>
                    </div>
                  </div>
                  {order.reason && (
                    <p className="text-xs text-muted-foreground truncate">{order.reason}</p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          {/* 데스크톱: 테이블 */}
          <div className="hidden md:block rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">일시</TableHead>
                  <TableHead>종목</TableHead>
                  <TableHead className="w-16">구분</TableHead>
                  <TableHead className="text-right">수량</TableHead>
                  <TableHead className="text-right">주문가</TableHead>
                  <TableHead className="text-right">체결가</TableHead>
                  <TableHead className="w-20">상태</TableHead>
                  <TableHead>사유</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id}>
                    <TableCell className="text-xs whitespace-nowrap">
                      {formatDate(order.createdAt)}
                    </TableCell>
                    <TableCell>
                      <span className="font-medium text-sm">{order.tickerName}</span>
                      <span className="text-xs text-muted-foreground ml-1 font-mono">
                        {order.ticker}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          order.side === "buy"
                            ? "text-red-400 border-red-500/30"
                            : "text-blue-400 border-blue-500/30"
                        }
                      >
                        {orderSideLabels[order.side]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatQuantity(order.quantity, isMasked)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatMaskedKrw(order.price, isMasked)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {order.filledPrice != null
                        ? formatMaskedKrw(order.filledPrice, isMasked)
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={statusColors[order.status]}>
                        {orderStatusLabels[order.status]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                      {order.reason ?? "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* 페이지네이션 */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {offset + 1}~{offset + orders.length}건 표시
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={handlePrev}
                disabled={offset === 0}
              >
                <ChevronLeft className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={handleNext}
                disabled={orders.length < PAGE_SIZE}
              >
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
