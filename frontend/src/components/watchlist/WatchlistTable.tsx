"use client";

import { useAppStore } from "@/stores/appStore";
import { formatMaskedKrw } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pencil, Trash2, ExternalLink, Loader2 } from "lucide-react";
import type { WatchlistItem } from "@/types";
import Link from "next/link";

interface WatchlistTableProps {
  items: WatchlistItem[];
  loading: boolean;
  onEdit: (item: WatchlistItem) => void;
  onDelete: (item: WatchlistItem) => void;
}

export function WatchlistTable({ items, loading, onEdit, onDelete }: WatchlistTableProps) {
  const isMasked = useAppStore((s) => s.isMasked);

  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        관심종목이 없습니다. 종목을 추가해보세요.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>종목</TableHead>
            <TableHead>시장</TableHead>
            <TableHead className="text-right">목표 매수가</TableHead>
            <TableHead className="text-right">목표 매도가</TableHead>
            <TableHead className="text-right">알림 기준(%)</TableHead>
            <TableHead>메모</TableHead>
            <TableHead className="text-right">액션</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <Link
                  href={`/analysis/${encodeURIComponent(item.ticker)}?market=${item.market}`}
                  className="flex items-center gap-1 font-medium hover:underline"
                >
                  {item.ticker}
                  <ExternalLink className="size-3 text-muted-foreground" />
                </Link>
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="text-xs">
                  {item.market}
                </Badge>
              </TableCell>
              <TableCell className="text-right">
                {item.targetBuyPrice != null
                  ? formatMaskedKrw(item.targetBuyPrice, isMasked)
                  : "-"}
              </TableCell>
              <TableCell className="text-right">
                {item.targetSellPrice != null
                  ? formatMaskedKrw(item.targetSellPrice, isMasked)
                  : "-"}
              </TableCell>
              <TableCell className="text-right">
                {item.alertThresholdPct != null ? `${item.alertThresholdPct}%` : "-"}
              </TableCell>
              <TableCell className="max-w-[200px] truncate text-sm text-muted-foreground">
                {item.notes || "-"}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1">
                  <Button variant="ghost" size="sm" aria-label={`${item.ticker} 수정`} onClick={() => onEdit(item)}>
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button variant="ghost" size="sm" aria-label={`${item.ticker} 삭제`} onClick={() => onDelete(item)}>
                    <Trash2 className="size-3.5 text-destructive" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
