import { render, screen } from "@testing-library/react";
import { AssetDonutChart } from "@/components/dashboard/AssetDonutChart";
import type { DashboardSummary } from "@/types";

jest.mock("@/stores/appStore", () => ({
  useAppStore: (selector: (s: { isMasked: boolean }) => boolean) =>
    selector({ isMasked: false }),
}));

// Recharts uses ResizeObserver
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

const baseSummary: DashboardSummary = {
  totalValueKrw: 100_000_000,
  byType: {
    cash: { valueKrw: 50_000_000, ratio: 50 },
    domestic_stock: { valueKrw: 30_000_000, ratio: 30 },
    foreign_stock: { valueKrw: 20_000_000, ratio: 20 },
    crypto: { valueKrw: 0, ratio: 0 },
    real_estate: { valueKrw: 0, ratio: 0 },
  },
  pnl: { total: 0, realized: 0, unrealized: 0, totalRatio: 0 },
  previousDayChange: { amount: 0, ratio: 0 },
  updatedAt: "2026-03-19T12:00:00Z",
};

describe("AssetDonutChart", () => {
  it("유형별 범례가 렌더링된다", () => {
    render(<AssetDonutChart summary={baseSummary} />);
    expect(screen.getByText("현금/예적금")).toBeInTheDocument();
    expect(screen.getByText("국내주식")).toBeInTheDocument();
    expect(screen.getByText("해외주식/ETF")).toBeInTheDocument();
    // 0인 유형은 제외
    expect(screen.queryByText("암호화폐")).not.toBeInTheDocument();
  });

  it("데이터가 없으면 빈 메시지를 표시한다", () => {
    const empty: DashboardSummary = {
      ...baseSummary,
      byType: {
        cash: { valueKrw: 0, ratio: 0 },
        domestic_stock: { valueKrw: 0, ratio: 0 },
        foreign_stock: { valueKrw: 0, ratio: 0 },
        crypto: { valueKrw: 0, ratio: 0 },
        real_estate: { valueKrw: 0, ratio: 0 },
      },
    };
    render(<AssetDonutChart summary={empty} />);
    expect(screen.getByText("자산 데이터가 없습니다")).toBeInTheDocument();
  });
});
