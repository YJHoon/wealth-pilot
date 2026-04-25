import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetForm } from "@/components/assets/AssetForm";
import type { PortfolioGroup } from "@/types";

// next-auth mock
jest.mock("next-auth/react", () => ({
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
  useSession: () => ({ data: null, status: "unauthenticated" }),
}));

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

const mockOnSubmit = jest.fn().mockResolvedValue(undefined);
const mockOnOpenChange = jest.fn();

function renderForm(props: Partial<React.ComponentProps<typeof AssetForm>> = {}) {
  return render(
    <AssetForm
      open={true}
      onOpenChange={mockOnOpenChange}
      groups={mockGroups}
      onSubmit={mockOnSubmit}
      isSubmitting={false}
      {...props}
    />,
  );
}

describe("AssetForm", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("다이얼로그 제목이 '자산 추가'로 렌더링된다", () => {
    renderForm();
    expect(screen.getByText("자산 추가")).toBeInTheDocument();
  });

  it("편집 모드일 때 제목이 '자산 수정'으로 렌더링된다", () => {
    renderForm({
      editingAsset: {
        id: "a1",
        groupId: null,
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
    });
    expect(screen.getByText("자산 수정")).toBeInTheDocument();
  });

  it("자산명 필드가 존재한다", () => {
    renderForm();
    expect(screen.getByPlaceholderText("예: 삼성전자")).toBeInTheDocument();
  });

  it("수량, 매입가 필드가 존재한다", () => {
    renderForm();
    expect(screen.getByLabelText("수량")).toBeInTheDocument();
    expect(screen.getByLabelText("매입가")).toBeInTheDocument();
  });

  it("추가/취소 버튼이 존재한다", () => {
    renderForm();
    expect(screen.getByRole("button", { name: "추가" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "취소" })).toBeInTheDocument();
  });

  it("처리 중일 때 버튼이 비활성화된다", () => {
    renderForm({ isSubmitting: true });
    expect(screen.getByRole("button", { name: "처리 중..." })).toBeDisabled();
  });

  it("취소 버튼 클릭 시 onOpenChange(false) 호출", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole("button", { name: "취소" }));
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it("빈 폼 제출 시 유효성 검증 에러가 표시된다", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole("button", { name: "추가" }));
    await waitFor(() => {
      expect(screen.getByText("자산명을 입력해주세요")).toBeInTheDocument();
    });
    expect(mockOnSubmit).not.toHaveBeenCalled();
  });
});
