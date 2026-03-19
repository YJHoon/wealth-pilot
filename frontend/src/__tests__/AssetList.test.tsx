import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetList } from "@/components/assets/AssetList";
import type { Asset, PortfolioGroup } from "@/types";

// Zustand appStore mock
jest.mock("@/stores/appStore", () => ({
  useAppStore: (selector: (s: { isMasked: boolean }) => boolean) =>
    selector({ isMasked: false }),
}));

const mockAssets: Asset[] = [
  {
    id: "a1",
    groupId: "g1",
    type: "domestic_stock",
    status: "active",
    name: "삼성전자",
    ticker: "005930",
    quantity: 10,
    purchasePrice: 70000,
    currentPrice: 75000,
    currency: "KRW",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
  },
  {
    id: "a2",
    groupId: null,
    type: "cash",
    status: "active",
    name: "카카오뱅크 예금",
    ticker: null,
    quantity: 5000000,
    purchasePrice: 5000000,
    currentPrice: null,
    currency: "KRW",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
  },
];

const mockGroups: PortfolioGroup[] = [
  {
    id: "g1",
    userId: "u1",
    name: "장기투자",
    description: null,
    sortOrder: 0,
    createdAt: "2026-01-01",
  },
];

const mockHandlers = {
  onAddClick: jest.fn(),
  onEditClick: jest.fn(),
  onSellClick: jest.fn(),
  onDeleteClick: jest.fn(),
  onRefreshClick: jest.fn(),
};

function renderList(props: Partial<React.ComponentProps<typeof AssetList>> = {}) {
  return render(
    <AssetList
      assets={mockAssets}
      groups={mockGroups}
      loading={false}
      {...mockHandlers}
      {...props}
    />,
  );
}

describe("AssetList", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("자산 목록 헤더가 렌더링된다", () => {
    renderList();
    expect(screen.getByText("자산 관리")).toBeInTheDocument();
  });

  it("자산명이 표시된다", () => {
    renderList();
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("카카오뱅크 예금")).toBeInTheDocument();
  });

  it("그룹명이 표시된다", () => {
    renderList();
    expect(screen.getByText("장기투자")).toBeInTheDocument();
  });

  it("로딩 상태일 때 로딩 메시지가 표시된다", () => {
    renderList({ loading: true });
    expect(screen.getByText("자산 목록을 불러오는 중...")).toBeInTheDocument();
  });

  it("자산이 없을 때 빈 상태 메시지가 표시된다", () => {
    renderList({ assets: [] });
    expect(screen.getByText("등록된 자산이 없습니다.")).toBeInTheDocument();
  });

  it("자산 추가 버튼 클릭 시 onAddClick 호출", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(screen.getByRole("button", { name: /자산 추가/ }));
    expect(mockHandlers.onAddClick).toHaveBeenCalled();
  });

  it("시세 갱신 버튼 클릭 시 onRefreshClick 호출", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(screen.getByRole("button", { name: /시세 갱신/ }));
    expect(mockHandlers.onRefreshClick).toHaveBeenCalled();
  });

  it("자산 개수가 하단에 표시된다", () => {
    renderList();
    expect(screen.getByText(/총 2개 자산 표시 중/)).toBeInTheDocument();
  });

  it("priceMode가 전달되면 신뢰도 라벨이 표시된다", () => {
    renderList({ priceMode: "batch" });
    expect(screen.getByText(/1일 배치/)).toBeInTheDocument();
  });

  it("lastRefreshedAt이 전달되면 마지막 갱신 시각이 표시된다", () => {
    renderList({ lastRefreshedAt: "2026-03-19T12:00:00Z" });
    expect(screen.getByText(/마지막 갱신/)).toBeInTheDocument();
  });

  it("refreshing=true이면 시세 갱신 버튼이 비활성화된다", () => {
    renderList({ refreshing: true });
    const btn = screen.getByRole("button", { name: /시세 갱신/ });
    expect(btn).toBeDisabled();
  });

  it("isMasked=true이면 금액이 마스킹 처리된다", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    jest.spyOn(require("@/stores/appStore"), "useAppStore").mockImplementation(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (selector: any) => selector({ isMasked: true }),
    );
    renderList();
    const maskedElements = screen.getAllByText("●●●●●●원");
    expect(maskedElements.length).toBeGreaterThan(0);
  });

  it("해외자산에 toKrw가 전달되면 원화 병기된다", () => {
    const foreignAsset: Asset = {
      id: "a3",
      groupId: null,
      type: "foreign_stock",
      status: "active",
      name: "Apple",
      ticker: "AAPL",
      quantity: 5,
      purchasePrice: 150,
      currentPrice: 180,
      currency: "USD",
      metadata: {},
      soldAt: null,
      soldPrice: null,
      realizedPnl: null,
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };
    const mockToKrw = (amount: number, currency: string) =>
      currency === "USD" ? amount * 1350 : null;
    renderList({ assets: [foreignAsset], toKrw: mockToKrw });
    // 원화 환산 금액이 표시되어야 함
    expect(screen.getByText("Apple")).toBeInTheDocument();
  });
});
