import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExecuteDialog } from "@/components/advisory/ExecuteDialog";
import type { AnalysisRunItem } from "@/types/advisory";

let isMasked = false;
jest.mock("@/stores/appStore", () => ({
  useAppStore: (selector: (s: { isMasked: boolean }) => boolean) =>
    selector({ isMasked }),
}));

function makeItem(over: Partial<AnalysisRunItem> = {}): AnalysisRunItem {
  return {
    id: "item-1",
    ticker: "005930",
    tickerName: "삼성전자",
    source: "holding",
    action: "buy",
    confidence: 80,
    reason: "",
    refPrice: 70000,
    suggestedQty: 5,
    decision: "approved",
    blockedReason: null,
    orderId: null,
    ...over,
  };
}

function renderDialog(
  over: Partial<React.ComponentProps<typeof ExecuteDialog>> = {},
) {
  const props: React.ComponentProps<typeof ExecuteDialog> = {
    open: true,
    onOpenChange: jest.fn(),
    mode: "paper",
    approvedItems: [makeItem()],
    isExecuting: false,
    onConfirm: jest.fn(),
    ...over,
  };
  render(<ExecuteDialog {...props} />);
  return props;
}

describe("ExecuteDialog", () => {
  beforeEach(() => {
    isMasked = false;
  });

  it("paper 모드에서는 TOTP 입력이 없고 확정 버튼이 활성화된다", () => {
    renderDialog({ mode: "paper" });
    expect(screen.getByText(/모의\(paper\)/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/TOTP/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1건 발주/ })).not.toBeDisabled();
  });

  it("paper 모드 확정 시 onConfirm(undefined) 호출", async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    renderDialog({ mode: "paper", onConfirm });
    await user.click(screen.getByRole("button", { name: /1건 발주/ }));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("live 모드는 TOTP 입력 필드가 노출되고 6자리 입력 전엔 발주 버튼이 비활성화된다", async () => {
    const user = userEvent.setup();
    renderDialog({ mode: "live" });
    expect(screen.getByText(/실거래\(live\)/)).toBeInTheDocument();
    const totp = screen.getByLabelText(/TOTP/);
    expect(totp).toBeInTheDocument();
    const confirmBtn = screen.getByRole("button", { name: /1건 발주/ });
    expect(confirmBtn).toBeDisabled();
    await user.type(totp, "123");
    expect(confirmBtn).toBeDisabled();
  });

  it("live 모드에서 6자리 TOTP 입력 시 onConfirm 으로 코드가 전달된다", async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    renderDialog({ mode: "live", onConfirm });
    await user.type(screen.getByLabelText(/TOTP/), "654321");
    const confirmBtn = screen.getByRole("button", { name: /1건 발주/ });
    expect(confirmBtn).not.toBeDisabled();
    await user.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledWith("654321");
  });

  it("TOTP 입력은 숫자만 받고 6자리로 제한된다", async () => {
    const user = userEvent.setup();
    renderDialog({ mode: "live" });
    const totp = screen.getByLabelText(/TOTP/) as HTMLInputElement;
    await user.type(totp, "ab12cd3456789");
    expect(totp.value).toBe("123456");
  });

  it("매수/매도 카운트와 매수 예상 합계를 표시한다", () => {
    renderDialog({
      approvedItems: [
        makeItem({ id: "a", action: "buy", refPrice: 1000, suggestedQty: 3 }),
        makeItem({ id: "b", action: "buy", refPrice: 2000, suggestedQty: 1 }),
        makeItem({ id: "c", action: "sell", refPrice: 5000, suggestedQty: 2 }),
      ],
    });
    expect(screen.getByText("매수 2")).toBeInTheDocument();
    expect(screen.getByText("매도 1")).toBeInTheDocument();
    // 매수 합계: 1000*3 + 2000*1 = 5,000
    expect(screen.getByText("5,000원")).toBeInTheDocument();
  });

  it("isMasked 면 금액·수량이 마스킹된다", () => {
    isMasked = true;
    renderDialog({
      approvedItems: [makeItem({ refPrice: 1000, suggestedQty: 3 })],
    });
    expect(screen.queryByText(/3,000원/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/●●●●●●/).length).toBeGreaterThan(0);
  });

  it("승인 항목이 0건이면 빈 안내 + 발주 버튼 비활성화", () => {
    renderDialog({ approvedItems: [], mode: "paper" });
    expect(screen.getByText("승인된 항목이 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /0건 발주/ })).toBeDisabled();
  });

  it("isExecuting 시 발주 중 라벨 + 버튼 비활성화", () => {
    renderDialog({ isExecuting: true });
    expect(screen.getByRole("button", { name: "발주 중..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
  });
});
