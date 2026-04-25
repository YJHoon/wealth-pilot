import { render, screen } from "@testing-library/react";
import { MinimalDashboard } from "@/components/dashboard/MinimalDashboard";
import type { DashboardSummary } from "@/types";

// Mock Zustand
jest.mock("@/stores/appStore", () => ({
  useAppStore: (selector: (s: { isMasked: boolean }) => boolean) =>
    selector({ isMasked: false }),
}));

// Recharts ResizeObserver
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

const mockSummary: DashboardSummary = {
  totalValueKrw: 100_000_000,
  byType: {
    cash: { valueKrw: 50_000_000, ratio: 50 },
    domestic_stock: { valueKrw: 30_000_000, ratio: 30 },
    foreign_stock: { valueKrw: 20_000_000, ratio: 20 },
    crypto: { valueKrw: 0, ratio: 0 },
    real_estate: { valueKrw: 0, ratio: 0 },
  },
  byGroup: {},
  pnl: { total: 5_000_000, realized: 2_000_000, unrealized: 3_000_000, totalRatio: 5.26 },
  previousDayChange: { amount: 300_000, ratio: 0.3 },
  updatedAt: "2026-03-19T12:00:00Z",
};

// Mock hooks
const mockUseDashboardSummary = jest.fn();
jest.mock("@/hooks/useDashboardSummary", () => ({
  useDashboardSummary: () => mockUseDashboardSummary(),
}));

const mockUseDashboardHistory = jest.fn();
jest.mock("@/hooks/useDashboardHistory", () => ({
  useDashboardHistory: () => mockUseDashboardHistory(),
}));

describe("MinimalDashboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseDashboardHistory.mockReturnValue({
      history: [],
      loading: false,
      error: null,
    });
  });

  it("로딩 중일 때 스켈레톤을 표시한다", () => {
    mockUseDashboardSummary.mockReturnValue({
      summary: null,
      loading: true,
      error: null,
    });
    const { container } = render(<MinimalDashboard />);
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("에러 시 에러 메시지를 표시한다", () => {
    mockUseDashboardSummary.mockReturnValue({
      summary: null,
      loading: false,
      error: "서버 오류",
    });
    render(<MinimalDashboard />);
    expect(screen.getByText("서버 오류")).toBeInTheDocument();
  });

  it("데이터 로드 후 모든 섹션이 렌더링된다", () => {
    mockUseDashboardSummary.mockReturnValue({
      summary: mockSummary,
      loading: false,
      error: null,
    });
    render(<MinimalDashboard />);

    // 총 자산
    expect(screen.getByTestId("total-value")).toHaveTextContent("100,000,000원");
    // 전일대비
    expect(screen.getByTestId("daily-change")).toBeInTheDocument();
    // 도넛 차트 범례
    expect(screen.getByText("현금/예적금")).toBeInTheDocument();
    // 면책 문구
    expect(screen.getByText(/투자 판단의 근거로 사용할 수 없습니다/)).toBeInTheDocument();
    // 신뢰도 인디케이터
    expect(screen.getByTestId("freshness")).toBeInTheDocument();
  });

  it("summary가 null이면 에러 메시지를 표시한다", () => {
    mockUseDashboardSummary.mockReturnValue({
      summary: null,
      loading: false,
      error: null,
    });
    render(<MinimalDashboard />);
    expect(screen.getByText("대시보드 데이터를 불러올 수 없습니다.")).toBeInTheDocument();
  });
});
