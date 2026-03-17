"use client";

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { AssetList } from "@/components/assets/AssetList";
import { AssetForm, type AssetFormValues } from "@/components/assets/AssetForm";
import { SellDialog } from "@/components/assets/SellDialog";
import { useAssets } from "@/hooks/useAssets";
import { useGroups } from "@/hooks/useGroups";
import type { Asset, AssetCreateRequest, AssetUpdateRequest } from "@/types";
import { ApiError } from "@/lib/api";

export default function AssetsPage() {
  const { assets, loading, refetch, createAsset, updateAsset, deleteAsset, sellAsset } =
    useAssets();
  const { groups } = useGroups();

  // 폼 다이얼로그 상태
  const [formOpen, setFormOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<Asset | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 매도 다이얼로그 상태
  const [sellOpen, setSellOpen] = useState(false);
  const [sellingAsset, setSellingAsset] = useState<Asset | null>(null);

  // 시세 갱신
  const [refreshing, setRefreshing] = useState(false);

  // ── 핸들러 ──

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

  const handleDeleteClick = useCallback(
    async (asset: Asset) => {
      if (!window.confirm(`"${asset.name}" 자산을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) {
        return;
      }
      try {
        await deleteAsset(asset.id);
        toast.success("자산이 삭제되었습니다.");
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "자산 삭제에 실패했습니다.");
      }
    },
    [deleteAsset],
  );

  const handleFormSubmit = useCallback(
    async (values: AssetFormValues) => {
      setIsSubmitting(true);
      try {
        // 메타데이터 구성
        const metadata: Record<string, unknown> = {};
        if (values.type === "cash") {
          if (values.bank_name) metadata.bank_name = values.bank_name;
          if (values.interest_rate != null) {
            metadata.interest_rate = Number(values.interest_rate);
          }
        }

        if (editingAsset) {
          const updateData: AssetUpdateRequest = {
            name: values.name,
            ticker: values.ticker || null,
            currency: values.currency,
            quantity: values.type === "cash" ? values.quantity : values.quantity,
            purchase_price:
              values.type === "cash" ? values.quantity : values.purchase_price,
            current_price: values.current_price ?? null,
            group_id: values.group_id || null,
            metadata_json: Object.keys(metadata).length > 0 ? metadata : null,
          };
          await updateAsset(editingAsset.id, updateData);
          toast.success("자산이 수정되었습니다.");
        } else {
          const createData: AssetCreateRequest = {
            type: values.type,
            name: values.name,
            ticker: values.ticker || null,
            currency: values.currency,
            quantity: values.type === "cash" ? values.quantity : values.quantity,
            purchase_price:
              values.type === "cash" ? values.quantity : values.purchase_price,
            current_price: values.current_price ?? null,
            group_id: values.group_id || null,
            metadata_json: Object.keys(metadata).length > 0 ? metadata : null,
          };
          await createAsset(createData);
          toast.success("자산이 등록되었습니다.");
        }
        setFormOpen(false);
        setEditingAsset(null);
      } catch (err) {
        toast.error(
          err instanceof ApiError
            ? err.message
            : editingAsset
              ? "자산 수정에 실패했습니다."
              : "자산 등록에 실패했습니다.",
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [editingAsset, createAsset, updateAsset],
  );

  const handleSellSubmit = useCallback(
    async (assetId: string, soldPrice: number) => {
      try {
        await sellAsset(assetId, { sold_price: soldPrice });
        toast.success("매도가 완료되었습니다.");
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "매도 처리에 실패했습니다.");
        throw err;
      }
    },
    [sellAsset],
  );

  const handleRefreshClick = useCallback(async () => {
    setRefreshing(true);
    try {
      await refetch();
      toast.success("시세가 갱신되었습니다.");
    } catch {
      toast.error("시세 갱신에 실패했습니다.");
    } finally {
      setRefreshing(false);
    }
  }, [refetch]);

  return (
    <>
      <AssetList
        assets={assets}
        groups={groups}
        loading={loading}
        onAddClick={handleAddClick}
        onEditClick={handleEditClick}
        onSellClick={handleSellClick}
        onDeleteClick={handleDeleteClick}
        onRefreshClick={handleRefreshClick}
        refreshing={refreshing}
      />

      <AssetForm
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingAsset(null);
        }}
        editingAsset={editingAsset}
        groups={groups}
        onSubmit={handleFormSubmit}
        isSubmitting={isSubmitting}
      />

      <SellDialog
        open={sellOpen}
        onOpenChange={(open) => {
          setSellOpen(open);
          if (!open) setSellingAsset(null);
        }}
        asset={sellingAsset}
        onSubmit={handleSellSubmit}
      />
    </>
  );
}
