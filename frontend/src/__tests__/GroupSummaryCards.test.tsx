import { render, screen } from "@testing-library/react";
import { GroupSummaryCards } from "@/components/dashboard/GroupSummaryCards";
import type { DashboardSummary } from "@/types";

let mockMasked = false;
jest.mock("@/stores/appStore", () => ({
  useAppStore: (selector: (s: { isMasked: boolean }) => boolean) =>
    selector({ isMasked: mockMasked }),
}));

const baseSummary: DashboardSummary = {
  totalValueKrw: 100_000_000,
  byType: {
    cash: { valueKrw: 0, ratio: 0 },
    domestic_stock: { valueKrw: 0, ratio: 0 },
    foreign_stock: { valueKrw: 0, ratio: 0 },
    crypto: { valueKrw: 0, ratio: 0 },
    real_estate: { valueKrw: 0, ratio: 0 },
  },
  byGroup: {
    g1: { name: "장기투자", valueKrw: 60_000_000, ratio: 60 },
    g2: { name: "단기투자", valueKrw: 40_000_000, ratio: 40 },
  },
  pnl: { total: 0, realized: 0, unrealized: 0, totalRatio: 0 },
  previousDayChange: { amount: 0, ratio: 0 },
  updatedAt: "2026-03-19T12:00:00Z",
};

describe("GroupSummaryCards", () => {
  beforeEach(() => {
    mockMasked = false;
  });

  it("그룹 카드가 그룹 수만큼 렌더링된다", () => {
    render(<GroupSummaryCards summary={baseSummary} />);
    expect(screen.getByText("장기투자")).toBeInTheDocument();
    expect(screen.getByText("단기투자")).toBeInTheDocument();
  });

  it("금액과 비중이 표시된다", () => {
    render(<GroupSummaryCards summary={baseSummary} />);
    expect(screen.getByTestId("group-value-g1")).toHaveTextContent("60,000,000원");
    expect(screen.getByText("60.0%")).toBeInTheDocument();
  });

  it("마스킹 모드에서 금액이 숨겨진다", () => {
    mockMasked = true;
    render(<GroupSummaryCards summary={baseSummary} />);
    expect(screen.getByTestId("group-value-g1")).toHaveTextContent("●●●●●●원");
    expect(screen.getAllByText("●●%").length).toBe(2);
  });

  it("그룹이 없으면 아무것도 렌더링하지 않는다", () => {
    const empty = { ...baseSummary, byGroup: {} };
    const { container } = render(<GroupSummaryCards summary={empty} />);
    expect(container.firstChild).toBeNull();
  });
});
