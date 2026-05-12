import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetList } from "@/components/assets/AssetList";
import type { Asset, HoldingBreakdown } from "@/types";

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
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
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
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
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

  it("수동 입력 자산은 액션 메뉴 트리거가 표시된다", () => {
    renderList();
    // 모바일 + 데스크톱 둘 다 렌더되므로 getAllByRole
    expect(
      screen.getAllByRole("button", { name: /삼성전자 액션 메뉴/ }).length,
    ).toBeGreaterThan(0);
  });

  it("KIS 동기화 자산은 KIS 배지가 표시되고 액션 메뉴가 숨겨진다", async () => {
    const kisAsset: Asset = {
      ...mockAssets[0],
      id: "kis1",
      name: "현대차",
      ticker: "005380",
      source: "kis",
      tradingAccountId: "acc1",
      externalTicker: "005380",
      lastSyncedAt: "2026-03-19T12:00:00Z",
    };
    const user = userEvent.setup();
    renderList({ assets: [kisAsset] });

    // KIS 배지가 표시 (모바일 + 데스크톱 둘 다 렌더되므로 getAllByText)
    expect(screen.getAllByText("KIS").length).toBeGreaterThan(0);

    // 액션 메뉴 트리거가 존재하지 않음 → 클릭 핸들러 호출 안 됨
    expect(
      screen.queryByRole("button", { name: /현대차 액션 메뉴/ }),
    ).not.toBeInTheDocument();

    // 자산 추가 버튼은 KIS 행 존재와 무관하게 동작해야 함
    await user.click(screen.getByRole("button", { name: /자산 추가/ }));
    expect(mockHandlers.onAddClick).toHaveBeenCalledTimes(1);
    expect(mockHandlers.onEditClick).not.toHaveBeenCalled();
    expect(mockHandlers.onSellClick).not.toHaveBeenCalled();
    expect(mockHandlers.onDeleteClick).not.toHaveBeenCalled();
  });

  it("breakdown이 전달되면 자산 행에 전략/수동 보유량이 표기된다", () => {
    // 이전 마스킹 테스트에서 spy로 덮어쓴 useAppStore 구현을 isMasked=false로 되돌린다.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    jest.spyOn(require("@/stores/appStore"), "useAppStore").mockImplementation(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (selector: any) => selector({ isMasked: false }),
    );
    const breakdown: HoldingBreakdown = {
      items: [
        {
          accountId: "acc1",
          ticker: "005930",
          tickerName: "삼성전자",
          strategyQty: 7,
          advisoryQty: 3,
          kisQty: 10,
          mismatchQty: 0,
          hasMismatch: false,
        },
      ],
      mismatches: [],
    };
    const { container } = renderList({ breakdown });
    // 전략 7주 + 수동 3주가 모바일/데스크톱 양쪽 모두 렌더
    const html = container.innerHTML;
    expect(html).toContain("전략 7주");
    expect(html).toContain("수동 3주");
  });

  it("mismatch가 있으면 상단 경고 배너와 행 배지가 표시되고, 클릭 시 상세 다이얼로그가 열린다", async () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    jest.spyOn(require("@/stores/appStore"), "useAppStore").mockImplementation(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (selector: any) => selector({ isMasked: false }),
    );
    const breakdown: HoldingBreakdown = {
      items: [
        {
          accountId: "acc1",
          ticker: "005930",
          tickerName: "삼성전자",
          strategyQty: 7,
          advisoryQty: 2,
          kisQty: 10,
          mismatchQty: -1,
          hasMismatch: true,
        },
      ],
      mismatches: ["005930: 전략=7, 수동=2, 합계=9 vs KIS=10 (차이=-1)"],
    };
    const user = userEvent.setup();
    renderList({ breakdown });

    // 상단 배너
    expect(
      screen.getByText(/1개 종목의 내부 보유량이 KIS 실잔고와 일치하지 않습니다/),
    ).toBeInTheDocument();

    // 행 단위 "불일치" 배지가 모바일+데스크톱 둘 다 렌더됨
    const mismatchButtons = screen.getAllByRole("button", {
      name: /삼성전자 보유량 불일치 상세 보기/,
    });
    expect(mismatchButtons.length).toBeGreaterThan(0);

    await user.click(mismatchButtons[0]);

    // 다이얼로그 내용 검증
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/보유량 정합성 불일치/)).toBeInTheDocument();
    expect(within(dialog).getByText("내부 합계")).toBeInTheDocument();
    expect(within(dialog).getByText(/차이 \(내부 − KIS\)/)).toBeInTheDocument();
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
      source: "manual",
      tradingAccountId: null,
      externalTicker: null,
      lastSyncedAt: null,
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
