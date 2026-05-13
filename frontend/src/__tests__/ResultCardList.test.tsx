import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResultCardList } from "@/components/advisory/ResultCardList";
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
    reason: "실적 호조 지속",
    refPrice: 70000,
    suggestedQty: 5,
    decision: "pending",
    blockedReason: null,
    orderId: null,
    ...over,
  };
}

describe("ResultCardList", () => {
  beforeEach(() => {
    isMasked = false;
  });

  it("아이템이 비어있으면 빈 상태 메시지를 표시한다", () => {
    render(
      <ResultCardList
        items={[]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByText("분석 결과가 비어있습니다.")).toBeInTheDocument();
  });

  it("티커명/액션/소스/신뢰도/이유가 표시된다", () => {
    render(
      <ResultCardList
        items={[makeItem()]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("005930")).toBeInTheDocument();
    expect(screen.getByText("매수")).toBeInTheDocument();
    expect(screen.getByText("보유")).toBeInTheDocument();
    expect(screen.getByText("신뢰도 80")).toBeInTheDocument();
    expect(screen.getByText("실적 호조 지속")).toBeInTheDocument();
  });

  it("마스킹 OFF 시 참조가/제안수량/예상금액이 노출된다", () => {
    isMasked = false;
    render(
      <ResultCardList
        items={[makeItem({ refPrice: 70000, suggestedQty: 5 })]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByText("70,000원")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("350,000원")).toBeInTheDocument();
  });

  it("마스킹 ON 시 금액/수량이 ● 로 마스킹된다", () => {
    isMasked = true;
    render(
      <ResultCardList
        items={[makeItem({ refPrice: 70000, suggestedQty: 5 })]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.queryByText("70,000원")).not.toBeInTheDocument();
    expect(screen.getAllByText(/●●●●●●/).length).toBeGreaterThan(0);
  });

  it("pending + buy 항목의 체크박스 클릭 시 onToggle 이 호출된다", async () => {
    const onToggle = jest.fn();
    const user = userEvent.setup();
    render(
      <ResultCardList
        items={[makeItem()]}
        selectedIds={new Set()}
        onToggle={onToggle}
        readOnly={false}
      />,
    );
    const cb = screen.getByLabelText("삼성전자 선택");
    expect(cb).not.toBeDisabled();
    await user.click(cb);
    expect(onToggle).toHaveBeenCalledWith("item-1", true);
  });

  it("hold 액션은 체크박스가 비활성화된다", () => {
    render(
      <ResultCardList
        items={[makeItem({ action: "hold" })]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByLabelText("삼성전자 선택")).toBeDisabled();
  });

  it("skipped decision 은 체크박스가 비활성화되고 스킵 배지가 표시된다", () => {
    render(
      <ResultCardList
        items={[makeItem({ decision: "skipped" })]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByLabelText("삼성전자 선택")).toBeDisabled();
    expect(screen.getByText("스킵")).toBeInTheDocument();
  });

  it("readOnly 시 pending + buy 라도 체크박스가 비활성화된다", () => {
    render(
      <ResultCardList
        items={[makeItem()]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={true}
      />,
    );
    expect(screen.getByLabelText("삼성전자 선택")).toBeDisabled();
  });

  it("selectedIds 에 포함된 항목은 checked 로 표시된다", () => {
    render(
      <ResultCardList
        items={[makeItem()]}
        selectedIds={new Set(["item-1"])}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByLabelText("삼성전자 선택")).toBeChecked();
  });

  it("blocked_reason 이 있으면 차단 사유가 표시된다", () => {
    render(
      <ResultCardList
        items={[
          makeItem({
            decision: "skipped",
            blockedReason: "활성 전략 보유 중",
          }),
        ]}
        selectedIds={new Set()}
        onToggle={jest.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByText(/차단 사유: 활성 전략 보유 중/)).toBeInTheDocument();
  });
});
