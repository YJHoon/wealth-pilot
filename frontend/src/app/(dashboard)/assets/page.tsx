"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { TradingAccountSection } from "@/components/assets/TradingAccountSection";
import { AssetList } from "@/components/assets/AssetList";
import { AssetForm, type AssetFormValues } from "@/components/assets/AssetForm";
import { SellDialog } from "@/components/assets/SellDialog";
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
import { useTrading } from "@/hooks/useTrading";
import { useAssets } from "@/hooks/useAssets";
import { usePrices } from "@/hooks/usePrices";
import type { TradingAccountCreateRequest } from "@/types/trading";
import type { Asset, AssetCreateRequest, AssetUpdateRequest } from "@/types";
import { ApiError } from "@/lib/api";

export default function AssetsPage() {
  const trading = useTrading();
  const assetsHook = useAssets();
  const { lastRefreshedAt, priceMode, toKrw, refreshPrices } = usePrices();

  const [formOpen, setFormOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<Asset | null>(null);
  const [isSubmittingForm, setIsSubmittingForm] = useState(false);

  const [sellOpen, setSellOpen] = useState(false);
  const [sellingAsset, setSellingAsset] = useState<Asset | null>(null);

  const [pendingDelete, setPendingDelete] = useState<Asset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const [refreshingPrices, setRefreshingPrices] = useState(false);

  // ── KIS 계좌 핸들러 ──

  const handleCreateAccount = useCallback(
    async (data: TradingAccountCreateRequest) => {
      try {
        await trading.createAccount(data);
        toast.success("계좌가 등록되었습니다. 잔고를 조회합니다...");
      } catch (err) {
        toast.error(
          err instanceof ApiError ? err.message : "계좌 등록에 실패했습니다.",
        );
        throw err;
      }
    },
    [trading],
  );

  const handleDeactivateAccount = useCallback(
    async (id: string) => {
      try {
        await trading.deactivateAccount(id);
        await assetsHook.refetch();
        toast.success("계좌가 비활성화되었습니다.");
      } catch {
        toast.error("계좌 비활성화에 실패했습니다.");
      }
    },
    [trading, assetsHook],
  );

  const handleRefreshBalances = useCallback(async () => {
    try {
      const result = await trading.refreshAccountBalances();
      await assetsHook.refetch();
      if (result.total === 0) {
        toast.info("갱신할 활성 계좌가 없습니다.");
      } else if (result.failed === 0) {
        toast.success("잔고가 갱신되어 자산에 동기화되었습니다.");
      } else if (result.succeeded === 0) {
        toast.error("잔고 조회에 실패했습니다.");
      } else {
        toast.warning(
          `일부 계좌 갱신 실패 (${result.succeeded}/${result.total} 성공)` +
            (result.errors.length ? `: ${result.errors.join(", ")}` : ""),
        );
      }
    } catch {
      toast.error("잔고 조회에 실패했습니다.");
    }
  }, [trading, assetsHook]);

  // ── 자산 CRUD 핸들러 ──

  const handleAddClick = useCallback(() => {
    setEditingAsset(null);
    setFormOpen(true);
  }, []);

  const handleEditClick = useCallback((asset: Asset) => {
    setEditingAsset(asset);
    setFormOpen(true);
  }, []);

  const handleSellClick = useCallback((asset: Asset) => {
    setSellingAsset(asset);
    setSellOpen(true);
  }, []);

  const handleDeleteClick = useCallback((asset: Asset) => {
    setPendingDelete(asset);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!pendingDelete || isDeleting) return;
    setIsDeleting(true);
    try {
      await assetsHook.deleteAsset(pendingDelete.id);
      toast.success("자산이 삭제되었습니다.");
      setPendingDelete(null);
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "자산 삭제에 실패했습니다.",
      );
    } finally {
      setIsDeleting(false);
    }
  }, [assetsHook, pendingDelete, isDeleting]);

  const handleFormSubmit = useCallback(
    async (values: AssetFormValues) => {
      setIsSubmittingForm(true);
      try {
        const metadata: Record<string, unknown> = {};
        if (values.bank_name) metadata.bank_name = values.bank_name;
        if (values.interest_rate != null) metadata.interest_rate = values.interest_rate;

        const payload: AssetCreateRequest = {
          type: values.type,
          name: values.name,
          ticker: values.ticker || null,
          currency: values.currency,
          quantity: values.quantity!,
          purchase_price: values.purchase_price ?? values.quantity!,
          current_price: values.current_price ?? null,
          metadata_json: Object.keys(metadata).length > 0 ? metadata : null,
        };

        if (editingAsset) {
          const updatePayload: AssetUpdateRequest = {
            name: payload.name,
            ticker: payload.ticker,
            currency: payload.currency,
            quantity: payload.quantity,
            purchase_price: payload.purchase_price,
            current_price: payload.current_price,
            metadata_json: payload.metadata_json,
          };
          await assetsHook.updateAsset(editingAsset.id, updatePayload);
          toast.success("자산이 수정되었습니다.");
        } else {
          await assetsHook.createAsset(payload);
          toast.success("자산이 등록되었습니다.");
        }
        setFormOpen(false);
        setEditingAsset(null);
      } catch (err) {
        toast.error(
          err instanceof ApiError ? err.message : "자산 저장에 실패했습니다.",
        );
        throw err;
      } finally {
        setIsSubmittingForm(false);
      }
    },
    [assetsHook, editingAsset],
  );

  const handleSellSubmit = useCallback(
    async (assetId: string, soldPrice: number) => {
      try {
        await assetsHook.sellAsset(assetId, { sold_price: soldPrice });
        toast.success("매도가 처리되었습니다.");
      } catch (err) {
        toast.error(
          err instanceof ApiError ? err.message : "매도 처리에 실패했습니다.",
        );
        throw err;
      }
    },
    [assetsHook],
  );

  const handleRefreshPrices = useCallback(async () => {
    setRefreshingPrices(true);
    try {
      await refreshPrices();
      await assetsHook.refetch();
      toast.success("시세가 갱신되었습니다.");
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "시세 갱신에 실패했습니다.",
      );
    } finally {
      setRefreshingPrices(false);
    }
  }, [refreshPrices, assetsHook]);

  return (
    <div className="space-y-8">
      <TradingAccountSection
        accounts={trading.accounts}
        accountBalances={trading.accountBalances}
        loading={trading.loading.accounts}
        onCreateAccount={handleCreateAccount}
        onDeactivateAccount={handleDeactivateAccount}
        onRefreshBalances={handleRefreshBalances}
      />

      <AssetList
        assets={assetsHook.assets}
        loading={assetsHook.loading}
        breakdown={assetsHook.breakdown}
        onAddClick={handleAddClick}
        onEditClick={handleEditClick}
        onSellClick={handleSellClick}
        onDeleteClick={handleDeleteClick}
        onRefreshClick={handleRefreshPrices}
        refreshing={refreshingPrices}
        lastRefreshedAt={lastRefreshedAt}
        priceMode={priceMode}
        toKrw={toKrw}
      />

      <AssetForm
        open={formOpen}
        onOpenChange={setFormOpen}
        editingAsset={editingAsset}
        onSubmit={handleFormSubmit}
        isSubmitting={isSubmittingForm}
      />

      <SellDialog
        open={sellOpen}
        onOpenChange={setSellOpen}
        asset={sellingAsset}
        onSubmit={handleSellSubmit}
      />

      <AlertDialog
        open={!!pendingDelete}
        onOpenChange={(open) => {
          if (!open && !isDeleting) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>자산 삭제</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete
                ? `'${pendingDelete.name}'을(를) 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>취소</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleDeleteConfirm()}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "삭제 중..." : "삭제"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
