"use client";

import { useEffect } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import type { Asset, AssetType, Currency, PortfolioGroup } from "@/types";
import { assetTypeLabels } from "@/lib/format";
import { toNumber as toNum } from "@/lib/form-utils";

// ── 폼 값 타입 (Zod 스키마와 별도 정의하여 타입 안정성 확보) ──

interface AssetFormValues {
  type: AssetType;
  name: string;
  ticker?: string;
  currency: Currency;
  quantity: number;
  purchase_price: number;
  current_price?: number;
  group_id?: string;
  bank_name?: string;
  interest_rate?: number;
}

// ── Zod 검증 스키마 ──

const assetFormSchema = z.object({
  type: z.enum(["cash", "domestic_stock", "foreign_stock", "crypto", "real_estate"]),
  name: z.string().min(1, "자산명을 입력해주세요").max(200),
  ticker: z.string().max(20).optional(),
  currency: z.enum(["KRW", "USD", "EUR", "JPY", "BTC", "ETH"]),
  quantity: z.preprocess(toNum, z.number({ message: "숫자를 입력해주세요" }).positive("수량은 0보다 커야 합니다")),
  purchase_price: z.preprocess(toNum, z.number({ message: "숫자를 입력해주세요" }).min(0, "매입가는 0 이상이어야 합니다").optional()),
  current_price: z.preprocess(toNum, z.number().min(0).optional()),
  group_id: z.string().optional(),
  bank_name: z.string().optional(),
  interest_rate: z.preprocess(toNum, z.number().min(0).optional()),
}).superRefine((data, ctx) => {
  if (data.type !== "cash" && (data.purchase_price == null || data.purchase_price === undefined)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "매입가를 입력해주세요",
      path: ["purchase_price"],
    });
  }
});

// ── 유형별 기본 통화 ──

const defaultCurrencyByType: Record<AssetType, Currency> = {
  cash: "KRW",
  domestic_stock: "KRW",
  foreign_stock: "USD",
  crypto: "USD",
  real_estate: "KRW",
};

// ── Props ──

interface AssetFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingAsset?: Asset | null;
  groups: PortfolioGroup[];
  onSubmit: (data: AssetFormValues) => Promise<void>;
  isSubmitting: boolean;
}

export function AssetForm({
  open,
  onOpenChange,
  editingAsset,
  groups,
  onSubmit,
  isSubmitting,
}: AssetFormProps) {
  const isEditing = !!editingAsset;

  const form = useForm<AssetFormValues>({
    resolver: zodResolver(assetFormSchema) as Resolver<AssetFormValues>,
    defaultValues: {
      type: "domestic_stock",
      name: "",
      ticker: "",
      currency: "KRW",
      quantity: undefined as unknown as number,
      purchase_price: undefined as unknown as number,
      current_price: undefined,
      group_id: "",
      bank_name: "",
      interest_rate: undefined,
    },
  });

  const watchType = form.watch("type");

  // 편집 모드일 때 기존 값 세팅
  useEffect(() => {
    if (editingAsset) {
      form.reset({
        type: editingAsset.type,
        name: editingAsset.name,
        ticker: editingAsset.ticker ?? "",
        currency: editingAsset.currency,
        quantity: editingAsset.quantity,
        purchase_price: editingAsset.purchasePrice,
        current_price: editingAsset.currentPrice ?? undefined,
        group_id: editingAsset.groupId ?? undefined,
        bank_name: (editingAsset.metadata?.bank_name as string) ?? "",
        interest_rate: (editingAsset.metadata?.interest_rate as number) ?? undefined,
      });
    } else {
      form.reset({
        type: "domestic_stock",
        name: "",
        ticker: "",
        currency: "KRW",
        quantity: undefined as unknown as number,
        purchase_price: undefined as unknown as number,
        current_price: undefined,
        group_id: "",
        bank_name: "",
        interest_rate: undefined,
      });
    }
  }, [editingAsset, form]);

  // 유형 변경 시 기본 통화 설정
  useEffect(() => {
    if (!isEditing) {
      form.setValue("currency", defaultCurrencyByType[watchType] ?? "KRW");
    }
  }, [watchType, form, isEditing]);

  const handleSubmit = form.handleSubmit(async (values) => {
    await onSubmit(values);
  });

  const showTicker = ["domestic_stock", "foreign_stock", "crypto"].includes(watchType);
  const showCurrencySelect = ["foreign_stock", "crypto"].includes(watchType);
  const showCashFields = watchType === "cash";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? "자산 수정" : "자산 추가"}</DialogTitle>
          <DialogDescription>
            {isEditing ? "자산 정보를 수정합니다." : "새로운 자산을 등록합니다."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid gap-3">
          {/* 자산 유형 */}
          <div className="grid gap-1.5">
            <Label htmlFor="type">자산 유형</Label>
            <Select
              value={watchType}
              onValueChange={(val) => { if (val) form.setValue("type", val as AssetType); }}
              disabled={isEditing}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="유형 선택" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(assetTypeLabels).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 자산명 */}
          <div className="grid gap-1.5">
            <Label htmlFor="name">
              {showCashFields ? "은행/계좌명" : "자산명"}
            </Label>
            <Input
              id="name"
              placeholder={showCashFields ? "예: 카카오뱅크 정기예금" : "예: 삼성전자"}
              {...form.register("name")}
            />
            {form.formState.errors.name && (
              <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
            )}
          </div>

          {/* 종목코드/티커 */}
          {showTicker && (
            <div className="grid gap-1.5">
              <Label htmlFor="ticker">
                {watchType === "domestic_stock" ? "종목코드" : watchType === "crypto" ? "심볼" : "티커"}
              </Label>
              <Input
                id="ticker"
                placeholder={
                  watchType === "domestic_stock"
                    ? "예: 005930"
                    : watchType === "crypto"
                      ? "예: BTC"
                      : "예: AAPL"
                }
                {...form.register("ticker")}
              />
            </div>
          )}

          {/* 통화 */}
          {showCurrencySelect && (
            <div className="grid gap-1.5">
              <Label>통화</Label>
              <Select
                value={form.watch("currency")}
                onValueChange={(val) => { if (val) form.setValue("currency", val as Currency); }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="USD">USD ($)</SelectItem>
                  <SelectItem value="EUR">EUR (€)</SelectItem>
                  <SelectItem value="JPY">JPY (¥)</SelectItem>
                  <SelectItem value="KRW">KRW (₩)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* 수량/금액 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="quantity">
                {showCashFields ? "금액" : "수량"}
              </Label>
              <Input
                id="quantity"
                type="number"
                step="any"
                placeholder={showCashFields ? "10,000,000" : "10"}
                {...form.register("quantity")}
              />
              {form.formState.errors.quantity && (
                <p className="text-xs text-destructive">{form.formState.errors.quantity.message}</p>
              )}
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="purchase_price">
                {showCashFields ? "이율 (%)" : "매입가"}
              </Label>
              {showCashFields ? (
                <Input
                  id="interest_rate"
                  type="number"
                  step="0.01"
                  placeholder="3.50"
                  {...form.register("interest_rate")}
                />
              ) : (
                <>
                  <Input
                    id="purchase_price"
                    type="number"
                    step="any"
                    placeholder="70,000"
                    {...form.register("purchase_price")}
                  />
                  {form.formState.errors.purchase_price && (
                    <p className="text-xs text-destructive">
                      {form.formState.errors.purchase_price.message}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* 현재가 (현금 제외) */}
          {!showCashFields && (
            <div className="grid gap-1.5">
              <Label htmlFor="current_price">현재가 (선택)</Label>
              <Input
                id="current_price"
                type="number"
                step="any"
                placeholder="시세 갱신 시 자동 업데이트됩니다"
                {...form.register("current_price")}
              />
            </div>
          )}

          {/* 현금 유형 추가 필드 */}
          {showCashFields && (
            <div className="grid gap-1.5">
              <Label htmlFor="bank_name">은행명 (선택)</Label>
              <Input
                id="bank_name"
                placeholder="예: 카카오뱅크"
                {...form.register("bank_name")}
              />
            </div>
          )}

          {/* 그룹 선택 */}
          <div className="grid gap-1.5">
            <Label>포트폴리오 그룹 (선택)</Label>
            <Select
              value={form.watch("group_id") || "__none__"}
              onValueChange={(val) => form.setValue("group_id", !val || val === "__none__" ? "" : val)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="그룹 선택" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">그룹 없음</SelectItem>
                {groups.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    {g.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              취소
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "처리 중..." : isEditing ? "수정" : "추가"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export type { AssetFormValues };
