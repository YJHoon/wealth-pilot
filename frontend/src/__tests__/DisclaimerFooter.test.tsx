import { render, screen } from "@testing-library/react";
import { DisclaimerFooter } from "@/components/dashboard/DisclaimerFooter";

describe("DisclaimerFooter", () => {
  it("renders disclaimer text", () => {
    render(<DisclaimerFooter />);
    expect(screen.getByText(/투자 판단의 근거로 사용할 수 없습니다/)).toBeInTheDocument();
  });
});
