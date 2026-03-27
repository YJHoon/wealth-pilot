"use client";

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useWatchlist } from "@/hooks/useWatchlist";
import { WatchlistTable } from "@/components/watchlist/WatchlistTable";
import {
  WatchlistAddDialog,
  type WatchlistFormValues,
} from "@/components/watchlist/WatchlistAddDialog";
import { DCASimulator } from "@/components/watchlist/DCASimulator";
import { PortfolioSimulator } from "@/components/watchlist/PortfolioSimulator";
import { ScenarioCalculator } from "@/components/watchlist/ScenarioCalculator";
import { InvestmentDisclaimer } from "@/components/analysis/InvestmentDisclaimer";
import type { WatchlistItem } from "@/types";
import { ApiError } from "@/lib/api";
import { Plus } from "lucide-react";

export default function WatchlistPage() {
  const { items, loading, addItem, updateItem, removeItem } = useWatchlist();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<WatchlistItem | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingDeleteItem, setPendingDeleteItem] = useState<WatchlistItem | null>(null);

  const handleAddClick = useCallback(() => {
    setEditingItem(null);
    setDialogOpen(true);
  }, []);

  const handleEditClick = useCallback((item: WatchlistItem) => {
    setEditingItem(item);
    setDialogOpen(true);
  }, []);

  const handleDeleteClick = useCallback((item: WatchlistItem) => {
    setPendingDeleteItem(item);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!pendingDeleteItem) return;
    try {
      await removeItem(pendingDeleteItem.id);
      toast.success("관심종목이 삭제되었습니다.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "삭제에 실패했습니다.");
    } finally {
      setPendingDeleteItem(null);
    }
  }, [pendingDeleteItem, removeItem]);

  const handleSubmit = useCallback(
    async (values: WatchlistFormValues) => {
      setIsSubmitting(true);
      try {
        if (editingItem) {
          await updateItem(editingItem.id, {
            targetBuyPrice: values.targetBuyPrice ?? null,
            targetSellPrice: values.targetSellPrice ?? null,
            alertThresholdPct: values.alertThresholdPct ?? null,
            notes: values.notes ?? null,
          });
          toast.success("관심종목이 수정되었습니다.");
        } else {
          await addItem({
            ticker: values.ticker,
            market: values.market,
            targetBuyPrice: values.targetBuyPrice ?? null,
            targetSellPrice: values.targetSellPrice ?? null,
            alertThresholdPct: values.alertThresholdPct ?? null,
            notes: values.notes ?? null,
          });
          toast.success("관심종목이 추가되었습니다.");
        }
        setDialogOpen(false);
        setEditingItem(null);
      } catch (err) {
        toast.error(
          err instanceof ApiError
            ? err.message
            : editingItem
              ? "수정에 실패했습니다."
              : "추가에 실패했습니다.",
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [editingItem, addItem, updateItem],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">관심종목</h1>
        <Button size="sm" onClick={handleAddClick}>
          <Plus className="mr-1 size-3.5" />
          종목 추가
        </Button>
      </div>

      <InvestmentDisclaimer />

      <Tabs defaultValue="watchlist">
        <TabsList>
          <TabsTrigger value="watchlist">관심종목</TabsTrigger>
          <TabsTrigger value="dca">DCA 시뮬레이터</TabsTrigger>
          <TabsTrigger value="portfolio">포트폴리오</TabsTrigger>
          <TabsTrigger value="scenario">시나리오</TabsTrigger>
        </TabsList>

        <TabsContent value="watchlist" className="mt-4">
          <WatchlistTable
            items={items}
            loading={loading}
            onEdit={handleEditClick}
            onDelete={handleDeleteClick}
          />
        </TabsContent>

        <TabsContent value="dca" className="mt-4">
          <DCASimulator />
        </TabsContent>

        <TabsContent value="portfolio" className="mt-4">
          <PortfolioSimulator />
        </TabsContent>

        <TabsContent value="scenario" className="mt-4">
          <ScenarioCalculator />
        </TabsContent>
      </Tabs>

      <WatchlistAddDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) setEditingItem(null);
        }}
        editingItem={editingItem}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
      />

      <AlertDialog
        open={!!pendingDeleteItem}
        onOpenChange={(open) => { if (!open) setPendingDeleteItem(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>관심종목 삭제</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{pendingDeleteItem?.ticker}&rdquo; 종목을 관심목록에서 삭제하시겠습니까?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleDeleteConfirm()}>
              삭제
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
