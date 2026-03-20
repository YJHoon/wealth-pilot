import type { Currency, AssetType, AssetStatus } from "@/types";

const MASK = "●●●●●●";

const currencyConfig: Record<Currency, { symbol: string; locale: string }> = {
  KRW: { symbol: "원", locale: "ko-KR" },
  USD: { symbol: "$", locale: "en-US" },
  EUR: { symbol: "€", locale: "de-DE" },
  JPY: { symbol: "¥", locale: "ja-JP" },
  BTC: { symbol: "BTC", locale: "en-US" },
  ETH: { symbol: "ETH", locale: "en-US" },
};

/** 금액 포맷 (예: 195,000원, $150.00) */
export function formatAmount(
  value: number | null | undefined,
  currency: Currency,
  isMasked: boolean,
): string {
  if (isMasked) return `${MASK}원`;
  if (value == null) return "-";

  const config = currencyConfig[currency];

  if (currency === "KRW") {
    return `${value.toLocaleString("ko-KR")}원`;
  }
  if (currency === "BTC" || currency === "ETH") {
    return `${value.toLocaleString(config.locale, { minimumFractionDigits: 2, maximumFractionDigits: 8 })} ${config.symbol}`;
  }
  return `${config.symbol}${value.toLocaleString(config.locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 해외자산 원화 병기 (예: "$150.00 / 195,000원") */
export function formatDualCurrency(
  value: number | null | undefined,
  currency: Currency,
  krwValue: number | null | undefined,
  isMasked: boolean,
): string {
  if (isMasked) return `${MASK}원`;
  if (currency === "KRW") return formatAmount(value, currency, false);
  const foreign = formatAmount(value, currency, false);
  const krw = krwValue != null ? formatAmount(krwValue, "KRW", false) : "";
  return krw ? `${foreign} / ${krw}` : foreign;
}

/** 수량 포맷 */
export function formatQuantity(value: number | null | undefined, isMasked: boolean): string {
  if (isMasked) return MASK;
  if (value == null) return "-";
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 8 });
}

/** 수익률 포맷 (예: +12.34%, -5.67%) */
export function formatPnlRate(pnl: number, cost: number): string {
  if (cost === 0) return "-";
  const rate = (pnl / cost) * 100;
  const sign = rate >= 0 ? "+" : "";
  return `${sign}${rate.toFixed(2)}%`;
}

/** 수익/손실 금액 포맷 */
export function formatPnl(
  value: number | null | undefined,
  currency: Currency,
  isMasked: boolean,
): string {
  if (isMasked) return `${MASK}원`;
  if (value == null) return "-";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${formatAmount(value, currency, false)}`;
}

/** 자산 유형 한국어 라벨 */
export const assetTypeLabels: Record<AssetType, string> = {
  cash: "현금/예적금",
  domestic_stock: "국내주식",
  foreign_stock: "해외주식/ETF",
  crypto: "암호화폐",
  real_estate: "부동산",
};

/** 자산 상태 한국어 라벨 */
export const assetStatusLabels: Record<AssetStatus, string> = {
  active: "보유중",
  sold: "매도완료",
  delisted: "상장폐지",
};

/** 퍼센트 포맷 (예: "+12.34%") */
export function formatPercent(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

/** 변동 금액 포맷 (예: "+1,234,567원") */
export function formatChangeKrw(value: number, isMasked: boolean): string {
  if (isMasked) return `${MASK}원`;
  const sign = value >= 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString("ko-KR")}원`;
}

/** 수익률 색상 CSS 클래스 */
export function pnlColorClass(value: number): string {
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return "text-muted-foreground";
}

/** 마스킹 처리된 금액 (KRW) */
export function formatMaskedKrw(value: number, isMasked: boolean): string {
  if (isMasked) return `${MASK}원`;
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}
