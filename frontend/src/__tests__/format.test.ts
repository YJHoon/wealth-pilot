import { formatAmount, formatQuantity, formatPnl, formatPnlRate, assetTypeLabels } from "@/lib/format";

describe("formatAmount", () => {
  it("KRW 포맷", () => {
    expect(formatAmount(1000000, "KRW", false)).toBe("1,000,000원");
  });

  it("USD 포맷", () => {
    expect(formatAmount(150.5, "USD", false)).toBe("$150.50");
  });

  it("마스킹", () => {
    expect(formatAmount(1000000, "KRW", true)).toBe("●●●●●●원");
    expect(formatAmount(150, "USD", true)).toBe("●●●●●●");
  });

  it("null 값은 - 반환", () => {
    expect(formatAmount(null, "KRW", false)).toBe("-");
    expect(formatAmount(undefined, "KRW", false)).toBe("-");
  });

  it("BTC 포맷", () => {
    const result = formatAmount(0.5, "BTC", false);
    expect(result).toContain("BTC");
    expect(result).toContain("0.5");
  });
});

describe("formatQuantity", () => {
  it("일반 수량 포맷", () => {
    expect(formatQuantity(100, false)).toBe("100");
  });

  it("마스킹", () => {
    expect(formatQuantity(100, true)).toBe("●●●●●●");
  });

  it("null은 - 반환", () => {
    expect(formatQuantity(null, false)).toBe("-");
  });
});

describe("formatPnl", () => {
  it("양수 손익은 +부호 포함", () => {
    expect(formatPnl(50000, "KRW", false)).toBe("+50,000원");
  });

  it("음수 손익", () => {
    expect(formatPnl(-30000, "KRW", false)).toBe("-30,000원");
  });

  it("마스킹", () => {
    expect(formatPnl(50000, "KRW", true)).toBe("●●●●●●");
  });
});

describe("formatPnlRate", () => {
  it("양수 수익률", () => {
    expect(formatPnlRate(10000, 100000)).toBe("+10.00%");
  });

  it("음수 수익률", () => {
    expect(formatPnlRate(-5000, 100000)).toBe("-5.00%");
  });

  it("비용 0이면 -", () => {
    expect(formatPnlRate(100, 0)).toBe("-");
  });
});

describe("assetTypeLabels", () => {
  it("모든 유형에 한국어 라벨이 있음", () => {
    expect(assetTypeLabels.cash).toBe("현금/예적금");
    expect(assetTypeLabels.domestic_stock).toBe("국내주식");
    expect(assetTypeLabels.foreign_stock).toBe("해외주식/ETF");
    expect(assetTypeLabels.crypto).toBe("암호화폐");
    expect(assetTypeLabels.real_estate).toBe("부동산");
  });
});
