import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TickerSearch } from "@/components/analysis/TickerSearch";

// next/navigation mock
const mockPush = jest.fn().mockResolvedValue(undefined);
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe("TickerSearch", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("검색 입력 필드와 검색 버튼이 렌더링된다", () => {
    render(<TickerSearch />);
    expect(
      screen.getByPlaceholderText(/종목코드 또는 티커 입력/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "검색" })).toBeInTheDocument();
  });

  it("인기 종목 뱃지가 렌더링된다", () => {
    render(<TickerSearch />);
    expect(screen.getByText(/삼성전자/)).toBeInTheDocument();
    expect(screen.getByText(/Apple/)).toBeInTheDocument();
    expect(screen.getByText(/NVIDIA/)).toBeInTheDocument();
  });

  it("빈 입력 시 검색 버튼이 비활성화된다", () => {
    render(<TickerSearch />);
    expect(screen.getByRole("button", { name: "검색" })).toBeDisabled();
  });

  it("입력 후 검색 시 router.push가 호출된다", async () => {
    const user = userEvent.setup();
    render(<TickerSearch />);

    const input = screen.getByPlaceholderText(/종목코드 또는 티커 입력/);
    await user.type(input, "AAPL");
    await user.click(screen.getByRole("button", { name: "검색" }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/analysis/AAPL?market=KRX");
    });
  });

  it("Enter 키로 검색할 수 있다", async () => {
    const user = userEvent.setup();
    render(<TickerSearch />);

    const input = screen.getByPlaceholderText(/종목코드 또는 티커 입력/);
    await user.type(input, "TSLA{Enter}");

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/analysis/TSLA?market=KRX");
    });
  });

  it("onSearch prop이 있으면 router.push 대신 onSearch가 호출된다", async () => {
    const user = userEvent.setup();
    const mockOnSearch = jest.fn();
    render(<TickerSearch onSearch={mockOnSearch} />);

    const input = screen.getByPlaceholderText(/종목코드 또는 티커 입력/);
    await user.type(input, "005930");
    await user.click(screen.getByRole("button", { name: "검색" }));

    await waitFor(() => {
      expect(mockOnSearch).toHaveBeenCalledWith("005930", "KRX");
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("async onSearch가 완료될 때까지 searching 상태가 유지된다", async () => {
    const user = userEvent.setup();
    let resolveSearch: () => void;
    const mockOnSearch = jest.fn(
      () => new Promise<void>((resolve) => { resolveSearch = resolve; }),
    );
    render(<TickerSearch onSearch={mockOnSearch} />);

    const input = screen.getByPlaceholderText(/종목코드 또는 티커 입력/);
    await user.type(input, "AAPL");
    await user.click(screen.getByRole("button", { name: "검색" }));

    // 검색 중에는 버튼이 비활성화 (로딩 스피너 표시)
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "" })).toBeDisabled();
    });

    // resolve 후 버튼 다시 활성화
    resolveSearch!();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "검색" })).not.toBeDisabled();
    });
  });

  it("인기 종목 클릭 시 해당 종목으로 검색된다", async () => {
    const user = userEvent.setup();
    const mockOnSearch = jest.fn();
    render(<TickerSearch onSearch={mockOnSearch} />);

    await user.click(screen.getByText(/Apple/));

    await waitFor(() => {
      expect(mockOnSearch).toHaveBeenCalledWith("AAPL", "NASDAQ");
    });
  });
});
