import type { AssetType } from "@/types";

/** 자산 유형별 차트 색상 — AssetList typeIcons 색상과 통일 */
export const ASSET_TYPE_COLORS: Record<AssetType, string> = {
  cash: "#10b981",           // emerald-500
  domestic_stock: "#3b82f6", // blue-500
  foreign_stock: "#8b5cf6",  // violet-500
  crypto: "#f59e0b",         // amber-500
  real_estate: "#f43f5e",    // rose-500
};

/** 기간 선택 옵션 */
export const PERIOD_OPTIONS = [
  { label: "1M", value: "1M" },
  { label: "3M", value: "3M" },
  { label: "6M", value: "6M" },
  { label: "1Y", value: "1Y" },
] as const;

/** PnL 탭 */
export const PNL_TABS = [
  { label: "합산", value: "total" },
  { label: "실현", value: "realized" },
  { label: "미실현", value: "unrealized" },
] as const;
