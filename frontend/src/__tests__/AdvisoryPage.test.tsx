import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdvisoryPage from "@/app/(dashboard)/advisory/page";
import type { AnalysisRun, AnalysisRunItem } from "@/types/advisory";
import type { TradingAccount } from "@/types/trading";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("sonner", () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    warning: jest.fn(),
  },
}));

jest.mock("@/stores/appStore", () => ({
  useAppStore: (selector: (s: { isMasked: boolean }) => boolean) =>
    selector({ isMasked: false }),
}));

const mockTradingAccount: TradingAccount = {
  id: "acc-1",
  mode: "paper",
  initialCapital: 10_000_000,
  cashBalance: 5_000_000,
  isActive: true,
  allowNetting: false,
  tokenExpiresAt: null,
  createdAt: "2026-01-01",
  updatedAt: "2026-01-01",
};

const mockUseTrading = jest.fn();
jest.mock("@/hooks/useTrading", () => ({
  useTrading: () => mockUseTrading(),
}));

const mockUseAdvisory = jest.fn();
jest.mock("@/hooks/useAdvisory", () => ({
  useAdvisory: () => mockUseAdvisory(),
}));

function makeItem(over: Partial<AnalysisRunItem> = {}): AnalysisRunItem {
  return {
    id: "item-1",
    ticker: "005930",
    tickerName: "삼성전자",
    source: "holding",
    action: "buy",
    confidence: 80,
    reason: "good",
    refPrice: 70000,
    suggestedQty: 5,
    decision: "pending",
    blockedReason: null,
    orderId: null,
    ...over,
  };
}

function makeRun(over: Partial<AnalysisRun> = {}): AnalysisRun {
  return {
    id: "run-1",
    accountId: "acc-1",
    mode: "paper",
    status: "ready",
    budgetKrw: 1_000_000,
    candidatePoolOptions: {},
    startedAt: "2026-05-13T00:00:00Z",
    completedAt: "2026-05-13T00:00:30Z",
    expiresAt: "2026-05-13T00:05:00Z",
    summaryJson: null,
    errorMessage: null,
    items: [makeItem()],
    expired: false,
    ...over,
  };
}

function makeAdvisory(over: Partial<ReturnType<typeof baseAdvisory>> = {}) {
  return { ...baseAdvisory(), ...over };
}

function baseAdvisory() {
  return {
    run: null as AnalysisRun | null,
    history: null,
    loading: {
      run: false,
      history: false,
      creating: false,
      submittingDecisions: false,
      executing: false,
    },
    error: null,
    createRun: jest.fn(),
    loadRun: jest.fn(),
    setActiveRun: jest.fn(),
    submitDecisions: jest.fn().mockResolvedValue(undefined),
    executeRun: jest.fn().mockResolvedValue({
      runId: "run-1",
      executed: 1,
      failed: 0,
      results: [],
    }),
    refreshHistory: jest.fn().mockResolvedValue(undefined),
  };
}

function baseTrading() {
  return {
    accounts: [mockTradingAccount],
    loading: { accounts: false },
  };
}

describe("AdvisoryPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseTrading.mockReturnValue(baseTrading());
    mockUseAdvisory.mockReturnValue(makeAdvisory());
  });

  it("계좌가 없으면 등록 안내 카드를 보여준다", () => {
    mockUseTrading.mockReturnValue({
      accounts: [],
      loading: { accounts: false },
    });
    render(<AdvisoryPage />);
    expect(screen.getByText("등록된 계좌가 없습니다")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /내 자산에서 계좌 등록하기/ }),
    ).toBeInTheDocument();
  });

  it("run 이 없으면 RunControlPanel 만 표시된다", () => {
    render(<AdvisoryPage />);
    expect(screen.getByText("원클릭 분석 실행")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "분석 실행" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/선택 항목 발주/)).not.toBeInTheDocument();
  });

  it("run.status=analyzing 이면 진행 배지와 실행 버튼 비활성화", () => {
    mockUseAdvisory.mockReturnValue(
      makeAdvisory({ run: makeRun({ status: "analyzing" }) }),
    );
    render(<AdvisoryPage />);
    expect(screen.getByText(/분석 중 진행 중/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "분석 실행" })).toBeDisabled();
  });

  it("run.status=ready 이면 결과 카드와 발주 버튼이 노출된다", () => {
    mockUseAdvisory.mockReturnValue(makeAdvisory({ run: makeRun() }));
    render(<AdvisoryPage />);
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /선택 항목 발주/ }),
    ).toBeInTheDocument();
  });

  it("ready 상태에서 항목 미선택 시 발주 버튼이 비활성화된다", () => {
    mockUseAdvisory.mockReturnValue(makeAdvisory({ run: makeRun() }));
    render(<AdvisoryPage />);
    expect(
      screen.getByRole("button", { name: /선택 항목 발주/ }),
    ).toBeDisabled();
  });

  it("체크박스 선택 후 발주 버튼 클릭 → submitDecisions 호출 + ExecuteDialog 오픈", async () => {
    const user = userEvent.setup();
    const advisory = makeAdvisory({ run: makeRun() });
    mockUseAdvisory.mockReturnValue(advisory);
    render(<AdvisoryPage />);

    await user.click(screen.getByLabelText("삼성전자 선택"));
    await user.click(screen.getByRole("button", { name: /선택 항목 발주/ }));

    await waitFor(() => {
      expect(advisory.submitDecisions).toHaveBeenCalledWith("run-1", {
        decisions: [{ item_id: "item-1", decision: "approved" }],
      });
    });
    await waitFor(() => {
      expect(screen.getByText("발주 확인")).toBeInTheDocument();
    });
  });

  it("expired=true 면 만료 안내 + 재분석 버튼이 보이고 발주 버튼은 사라진다", () => {
    mockUseAdvisory.mockReturnValue(
      makeAdvisory({ run: makeRun({ expired: true }) }),
    );
    render(<AdvisoryPage />);
    expect(
      screen.getByText(/결과 유효기간이 만료되었습니다/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /재분석 준비/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /선택 항목 발주/ }),
    ).not.toBeInTheDocument();
  });

  it("run.status=done 이면 발주 완료 안내가 나온다", () => {
    mockUseAdvisory.mockReturnValue(
      makeAdvisory({ run: makeRun({ status: "done" }) }),
    );
    render(<AdvisoryPage />);
    expect(
      screen.getByText(/발주가 완료되었습니다/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /매매 내역/ }),
    ).toHaveAttribute("href", "/orders");
  });

  it("run.status=failed 면 에러 메시지를 표시한다", () => {
    mockUseAdvisory.mockReturnValue(
      makeAdvisory({
        run: makeRun({ status: "failed", errorMessage: "LLM 호출 실패" }),
      }),
    );
    render(<AdvisoryPage />);
    expect(screen.getByText(/분석에 실패했습니다.*LLM 호출 실패/)).toBeInTheDocument();
  });

  it("폴링 모킹: status 가 analyzing → ready 로 갱신되면 발주 UI 가 활성화된다", async () => {
    // 1차 렌더: analyzing — items 미적재
    mockUseAdvisory.mockReturnValue(
      makeAdvisory({ run: makeRun({ status: "analyzing", items: [] }) }),
    );
    const { rerender } = render(<AdvisoryPage />);
    expect(screen.getByText(/분석 중 진행 중/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /선택 항목 발주/ }),
    ).not.toBeInTheDocument();

    // 2차 렌더: ready (폴링 결과를 시뮬레이션) — items 적재
    mockUseAdvisory.mockReturnValue(
      makeAdvisory({ run: makeRun({ status: "ready" }) }),
    );
    rerender(<AdvisoryPage />);
    await waitFor(() => {
      expect(screen.getByText("삼성전자")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /선택 항목 발주/ }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/분석 중 진행 중/)).not.toBeInTheDocument();
  });
});
