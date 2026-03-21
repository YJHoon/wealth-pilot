import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// --- mocks ---

const mockPush = jest.fn();
const mockUpdate = jest.fn();
let mockSession: Record<string, unknown> | null = {
  accessToken: "test-token",
  totpSetupRequired: true,
  onboardingCompleted: false,
};

jest.mock("next-auth/react", () => ({
  useSession: () => ({
    data: mockSession,
    update: mockUpdate,
  }),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/lib/api", () => ({
  apiFetch: jest.fn(),
}));

import { apiFetch } from "@/lib/api";
import OnboardingWizard from "@/components/onboarding/OnboardingWizard";

const mockApiFetch = apiFetch as jest.MockedFunction<typeof apiFetch>;

describe("OnboardingWizard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSession = {
      accessToken: "test-token",
      totpSetupRequired: true,
      onboardingCompleted: false,
    };
  });

  it("첫 화면에 환영 메시지가 표시된다", () => {
    render(<OnboardingWizard />);
    expect(screen.getByText("WealthPilot에 오신 것을 환영합니다")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "시작하기" })).toBeInTheDocument();
  });

  it("시작하기 클릭 → 면책 동의 단계로 이동", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizard />);

    await user.click(screen.getByRole("button", { name: "시작하기" }));
    expect(screen.getByText("면책 조항 동의")).toBeInTheDocument();
  });

  it("면책 동의 없이 다음 버튼 비활성화", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizard />);

    await user.click(screen.getByRole("button", { name: "시작하기" }));
    expect(screen.getByRole("button", { name: "동의하고 계속하기" })).toBeDisabled();
  });

  it("면책 동의 체크 → 다음 버튼 활성화", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizard />);

    await user.click(screen.getByRole("button", { name: "시작하기" }));
    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "동의하고 계속하기" })).toBeEnabled();
  });

  it("면책 동의 후 → 2FA 설정 단계로 이동", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizard />);

    await user.click(screen.getByRole("button", { name: "시작하기" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "동의하고 계속하기" }));

    expect(screen.getByText("2단계 인증 설정")).toBeInTheDocument();
  });

  it("2FA 이미 완료된 경우 → 완료 표시 + 다음 가능", async () => {
    mockSession = {
      ...mockSession,
      totpSetupRequired: false,
    };

    const user = userEvent.setup();
    render(<OnboardingWizard />);

    // Step 1 → 2 → 3
    await user.click(screen.getByRole("button", { name: "시작하기" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "동의하고 계속하기" }));

    expect(screen.getByText("2단계 인증 설정 완료")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다음" })).toBeEnabled();
  });

  it("자산 유형 선택 스킵 가능", async () => {
    mockSession = { ...mockSession, totpSetupRequired: false };
    const user = userEvent.setup();
    render(<OnboardingWizard />);

    // Step 1 → 2 → 3 → 4
    await user.click(screen.getByRole("button", { name: "시작하기" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "동의하고 계속하기" }));
    await user.click(screen.getByRole("button", { name: "다음" })); // skip 2FA (done)

    expect(screen.getByText("어떤 자산을 보유하고 계세요?")).toBeInTheDocument();

    // 건너뛰기
    await user.click(screen.getByRole("button", { name: "건너뛰기" }));
    expect(screen.getByText("자산 등록 가이드")).toBeInTheDocument();
  });

  it("자산 유형 토글 선택/해제", async () => {
    mockSession = { ...mockSession, totpSetupRequired: false };
    const user = userEvent.setup();
    render(<OnboardingWizard />);

    // Navigate to step 4
    await user.click(screen.getByRole("button", { name: "시작하기" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "동의하고 계속하기" }));
    await user.click(screen.getByRole("button", { name: "다음" }));

    // Select "국내주식"
    const stockButton = screen.getByRole("button", { name: /국내주식/ });
    await user.click(stockButton);

    // 다음 버튼 활성화
    expect(screen.getByTestId("onboarding-next")).toBeEnabled();
  });

  it("완료 단계에서 API 호출 + 대시보드 이동", async () => {
    mockSession = { ...mockSession, totpSetupRequired: false };
    mockApiFetch.mockResolvedValueOnce({
      onboarding_completed: true,
      message: "온보딩이 완료되었습니다.",
    });
    mockUpdate.mockResolvedValueOnce(undefined);

    const user = userEvent.setup();
    render(<OnboardingWizard />);

    // Navigate through all steps: 1→2→3→4(skip)→5(skip)→6
    await user.click(screen.getByRole("button", { name: "시작하기" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "동의하고 계속하기" }));
    await user.click(screen.getByRole("button", { name: "다음" })); // 2FA done
    await user.click(screen.getByRole("button", { name: "건너뛰기" })); // skip asset types
    await user.click(screen.getByRole("button", { name: "건너뛰기" })); // skip guide

    // Step 6: Completion
    expect(screen.getByText("설정 완료!")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "대시보드로 이동" }));

    expect(mockApiFetch).toHaveBeenCalledWith("/api/onboarding/complete", expect.objectContaining({
      method: "PUT",
    }));
    expect(mockUpdate).toHaveBeenCalledWith({ onboardingCompleted: true });
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("완료 단계에서 API 실패 시 에러 표시 + 대시보드 미이동", async () => {
    mockSession = { ...mockSession, totpSetupRequired: false };
    mockApiFetch.mockRejectedValueOnce(new Error("서버 오류가 발생했습니다."));

    const user = userEvent.setup();
    render(<OnboardingWizard />);

    // Navigate through all steps: 1→2→3→4(skip)→5(skip)→6
    await user.click(screen.getByRole("button", { name: "시작하기" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "동의하고 계속하기" }));
    await user.click(screen.getByRole("button", { name: "다음" }));
    await user.click(screen.getByRole("button", { name: "건너뛰기" }));
    await user.click(screen.getByRole("button", { name: "건너뛰기" }));

    await user.click(screen.getByRole("button", { name: "대시보드로 이동" }));

    expect(mockApiFetch).toHaveBeenCalledWith("/api/onboarding/complete", expect.objectContaining({
      method: "PUT",
    }));
    expect(screen.getByText("서버 오류가 발생했습니다.")).toBeInTheDocument();
    expect(mockUpdate).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("스텝 인디케이터가 현재 단계를 표시한다", () => {
    render(<OnboardingWizard />);
    expect(screen.getByText("1 / 6 — 환영")).toBeInTheDocument();
  });

  it("이전 버튼으로 뒤로 이동 가능", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizard />);

    await user.click(screen.getByRole("button", { name: "시작하기" }));
    expect(screen.getByText("면책 조항 동의")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "이전" }));
    expect(screen.getByText("WealthPilot에 오신 것을 환영합니다")).toBeInTheDocument();
  });
});
