import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TotalAssetCard } from "@/components/dashboard/TotalAssetCard";
import type { DashboardSummary } from "@/types";

let mockMasked = false;
jest.mock("@/stores/appStore", () => ({
  useAppStore: (selector: (s: { isMasked: boolean }) => boolean) =>
    selector({ isMasked: mockMasked }),
}));

const baseSummary: DashboardSummary = {
  totalValueKrw: 150_000_000,
  byType: {
    cash: { valueKrw: 50_000_000, ratio: 33.3 },
    domestic_stock: { valueKrw: 40_000_000, ratio: 26.7 },
    foreign_stock: { valueKrw: 30_000_000, ratio: 20.0 },
    crypto: { valueKrw: 20_000_000, ratio: 13.3 },
    real_estate: { valueKrw: 10_000_000, ratio: 6.7 },
  },
  pnl: { total: 5_000_000, realized: 2_000_000, unrealized: 3_000_000, totalRatio: 3.45 },
  previousDayChange: { amount: 1_200_000, ratio: 0.81 },
  updatedAt: "2026-03-19T12:00:00Z",
};

describe("TotalAssetCard", () => {
  beforeEach(() => {
    mockMasked = false;
  });

  it("총자산 금액이 표시된다", () => {
    render(<TotalAssetCard summary={baseSummary} />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("150,000,000원");
  });

  it("전일대비 변동이 + 색상으로 표시된다", () => {
    render(<TotalAssetCard summary={baseSummary} />);
    expect(screen.getByTestId("daily-change")).toHaveTextContent("+0.81%");
  });

  it("전일대비 음수일 때 - 표시", () => {
    const neg = {
      ...baseSummary,
      previousDayChange: { amount: -500_000, ratio: -0.33 },
    };
    render(<TotalAssetCard summary={neg} />);
    expect(screen.getByTestId("daily-change")).toHaveTextContent("-0.33%");
  });

  it("PnL 탭 전환이 동작한다", async () => {
    const user = userEvent.setup();
    render(<TotalAssetCard summary={baseSummary} />);

    // 기본: 합산 (total)
    expect(screen.getByTestId("pnl-value")).toHaveTextContent("+5,000,000원");

    // 실현 탭 클릭
    await user.click(screen.getByText("실현"));
    expect(screen.getByTestId("pnl-value")).toHaveTextContent("+2,000,000원");

    // 미실현 탭 클릭
    await user.click(screen.getByText("미실현"));
    expect(screen.getByTestId("pnl-value")).toHaveTextContent("+3,000,000원");
  });

  it("마스킹 모드에서 금액이 숨겨진다", () => {
    mockMasked = true;
    render(<TotalAssetCard summary={baseSummary} />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("●●●●●●원");
    expect(screen.getByTestId("daily-change")).toHaveTextContent("●●●●");
  });
});
