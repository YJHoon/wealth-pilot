import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SellDialog } from "@/components/assets/SellDialog";
import type { Asset } from "@/types";

jest.mock("next-auth/react", () => ({
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
  useSession: () => ({ data: null, status: "unauthenticated" }),
}));

const mockAsset: Asset = {
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
  createdAt: "2026-01-01",
  updatedAt: "2026-01-01",
};

const mockOnSubmit = jest.fn().mockResolvedValue(undefined);
const mockOnOpenChange = jest.fn();

function renderDialog(props: Partial<React.ComponentProps<typeof SellDialog>> = {}) {
  return render(
    <SellDialog
      open={true}
      onOpenChange={mockOnOpenChange}
      asset={mockAsset}
      onSubmit={mockOnSubmit}
      {...props}
    />,
  );
}

describe("SellDialog", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("다이얼로그 제목이 '매도 처리'로 렌더링된다", () => {
    renderDialog();
    expect(screen.getByText("매도 처리")).toBeInTheDocument();
  });

  it("자산명이 표시된다", () => {
    renderDialog();
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
  });

  it("매입가와 보유 수량이 표시된다", () => {
    renderDialog();
    expect(screen.getByText("70,000원")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
  });

  it("취소 버튼 클릭 시 onOpenChange(false) 호출", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole("button", { name: "취소" }));
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it("매도가 입력 필드와 제출 버튼이 존재한다", () => {
    renderDialog();
    expect(screen.getByPlaceholderText("매도 단가를 입력하세요")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "매도 확정" })).toBeInTheDocument();
  });

  it("매도가 미입력 시 유효성 에러 표시", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole("button", { name: "매도 확정" }));
    await waitFor(() => {
      expect(screen.getByText("매도가를 입력해주세요")).toBeInTheDocument();
    });
    expect(mockOnSubmit).not.toHaveBeenCalled();
  });

  it("asset이 null이면 아무것도 렌더링하지 않는다", () => {
    const { container } = renderDialog({ asset: null });
    expect(container.innerHTML).toBe("");
  });
});
