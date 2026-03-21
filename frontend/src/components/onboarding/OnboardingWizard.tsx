"use client";

import { useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { assetTypeLabels } from "@/lib/format";
import { ASSET_TYPE_VALUES, type AssetType } from "@/types";
import type { TotpSetupResponse, TotpVerifyResponse } from "@/types/auth";

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

const STEPS = [
  { id: "welcome", title: "환영" },
  { id: "disclaimer", title: "면책 동의" },
  { id: "2fa", title: "2단계 인증" },
  { id: "asset-types", title: "자산 유형" },
  { id: "guide", title: "등록 가이드" },
  { id: "complete", title: "완료" },
] as const;

// 2FA와 면책 동의는 스킵 불가 (인덱스 1, 2)
const SKIPPABLE_STEPS = new Set([3, 4]); // asset-types, guide

// Asset type → icon
const ASSET_TYPE_ICONS: Record<AssetType, string> = {
  cash: "💰",
  domestic_stock: "📈",
  foreign_stock: "🌐",
  crypto: "₿",
  real_estate: "🏠",
};

// Asset type → guide text
const ASSET_TYPE_GUIDES: Record<AssetType, { title: string; steps: string[] }> = {
  cash: {
    title: "현금/예적금 등록 방법",
    steps: [
      "자산 유형에서 '현금/예적금'을 선택합니다.",
      "자산명(예: 신한은행 적금), 금액을 입력합니다.",
      "메타데이터에 은행명, 이율 등을 추가할 수 있습니다.",
    ],
  },
  domestic_stock: {
    title: "국내주식 등록 방법",
    steps: [
      "자산 유형에서 '국내주식'을 선택합니다.",
      "종목명과 종목코드(예: 삼성전자 005930)를 입력합니다.",
      "보유 수량과 평균 매입가를 입력합니다.",
      "시세 갱신 시 현재가가 자동으로 반영됩니다.",
    ],
  },
  foreign_stock: {
    title: "해외주식/ETF 등록 방법",
    steps: [
      "자산 유형에서 '해외주식/ETF'을 선택합니다.",
      "종목명과 티커(예: AAPL, TSLA)를 입력합니다.",
      "통화를 선택합니다 (기본 USD).",
      "대시보드에서 원화+원래통화 병기로 표시됩니다.",
    ],
  },
  crypto: {
    title: "암호화폐 등록 방법",
    steps: [
      "자산 유형에서 '암호화폐'를 선택합니다.",
      "종목명과 심볼(예: BTC, ETH)을 입력합니다.",
      "보유 수량과 평균 매입가를 입력합니다.",
      "CoinGecko API를 통해 시세가 자동 갱신됩니다.",
    ],
  },
  real_estate: {
    title: "부동산 등록 방법",
    steps: [
      "자산 유형에서 '부동산'을 선택합니다.",
      "자산명(예: 서울 아파트)과 매입가를 입력합니다.",
      "현재 시세는 수동으로 업데이트합니다.",
    ],
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function OnboardingWizard() {
  const { data: session, update } = useSession();
  const router = useRouter();

  // Step management
  const [currentStep, setCurrentStep] = useState(0);

  // Step 2: Disclaimer
  const [disclaimerAgreed, setDisclaimerAgreed] = useState(false);

  // Step 3: 2FA
  const [twoFaSubStep, setTwoFaSubStep] = useState<"intro" | "qr" | "verify" | "done">("intro");
  const [setupData, setSetupData] = useState<TotpSetupResponse | null>(null);
  const [otpCode, setOtpCode] = useState("");

  // Step 4: Asset types
  const [selectedTypes, setSelectedTypes] = useState<AssetType[]>([]);

  // Shared
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const accessToken = session?.accessToken;
  const is2FaAlreadySetup = session?.totpSetupRequired === false;

  // ── Navigation ──

  const goNext = useCallback(() => {
    setError("");
    setCurrentStep((prev) => Math.min(prev + 1, STEPS.length - 1));
  }, []);

  const goBack = useCallback(() => {
    setError("");
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  }, []);

  const skipStep = useCallback(() => {
    if (SKIPPABLE_STEPS.has(currentStep)) {
      goNext();
    }
  }, [currentStep, goNext]);

  // ── Step 3: 2FA handlers ──

  const handle2FaSetup = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<TotpSetupResponse>("/api/auth/2fa/setup", {
        method: "POST",
        accessToken,
      });
      setSetupData(data);
      setTwoFaSubStep("qr");
    } catch (e) {
      setError(e instanceof Error ? e.message : "2FA 설정에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handle2FaVerify = async () => {
    if (!accessToken || otpCode.length !== 6) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<TotpVerifyResponse>("/api/auth/2fa/verify", {
        method: "POST",
        accessToken,
        body: JSON.stringify({ code: otpCode }),
      });
      if (data.verified) {
        setTwoFaSubStep("done");
        await update({
          accessToken: data.access_token,
          totpRequired: false,
          totpSetupRequired: false,
        });
      } else {
        setError(data.message);
        setOtpCode("");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "인증에 실패했습니다.");
      setOtpCode("");
    } finally {
      setLoading(false);
    }
  };

  // ── Step 6: Complete onboarding ──

  const handleComplete = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError("");
    try {
      await apiFetch("/api/onboarding/complete", {
        method: "PUT",
        accessToken,
        body: JSON.stringify({
          disclaimer_agreed: true,
          selected_asset_types: selectedTypes,
        }),
      });
      await update({ onboardingCompleted: true });
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "온보딩 완료에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  // ── Asset type toggle ──

  const toggleAssetType = (type: AssetType) => {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  };

  // ── Render ──

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4">
      {/* Stepper */}
      <div className="mb-6 flex items-center gap-1">
        {STEPS.map((step, i) => (
          <div key={step.id} className="flex items-center">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition-colors ${
                i < currentStep
                  ? "bg-emerald-500 text-white"
                  : i === currentStep
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground"
              }`}
            >
              {i < currentStep ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                i + 1
              )}
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`mx-1 h-0.5 w-6 transition-colors ${
                  i < currentStep ? "bg-emerald-500" : "bg-muted"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      <p className="mb-4 text-sm text-muted-foreground">
        {currentStep + 1} / {STEPS.length} — {STEPS[currentStep].title}
      </p>

      {/* Step content */}
      <Card className="w-full max-w-lg">
        <CardContent className="p-6">
          {error && (
            <div className="mb-4 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {currentStep === 0 && <WelcomeStep onNext={goNext} />}
          {currentStep === 1 && (
            <DisclaimerStep
              agreed={disclaimerAgreed}
              onToggle={() => setDisclaimerAgreed((v) => !v)}
              onNext={goNext}
              onBack={goBack}
            />
          )}
          {currentStep === 2 && (
            <TwoFactorStep
              isAlreadySetup={is2FaAlreadySetup}
              subStep={twoFaSubStep}
              setupData={setupData}
              otpCode={otpCode}
              loading={loading}
              onSetup={handle2FaSetup}
              onOtpChange={setOtpCode}
              onVerify={handle2FaVerify}
              onQrNext={() => setTwoFaSubStep("verify")}
              onVerifyBack={() => setTwoFaSubStep("qr")}
              onNext={goNext}
              onBack={goBack}
            />
          )}
          {currentStep === 3 && (
            <AssetTypeStep
              selected={selectedTypes}
              onToggle={toggleAssetType}
              onNext={goNext}
              onBack={goBack}
              onSkip={skipStep}
            />
          )}
          {currentStep === 4 && (
            <AssetGuideStep
              selectedTypes={selectedTypes}
              onNext={goNext}
              onBack={goBack}
              onSkip={skipStep}
            />
          )}
          {currentStep === 5 && (
            <CompletionStep loading={loading} onComplete={handleComplete} onBack={goBack} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Welcome
// ---------------------------------------------------------------------------

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="space-y-6 text-center">
      <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10">
        <svg className="h-10 w-10 text-primary" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
        </svg>
      </div>

      <div>
        <h2 className="text-2xl font-bold">WealthPilot에 오신 것을 환영합니다</h2>
        <p className="mt-2 text-muted-foreground">
          개인 자산을 한눈에 관리하세요.
          <br />
          간단한 초기 설정을 도와드리겠습니다.
        </p>
      </div>

      <div className="space-y-2 text-left text-sm text-muted-foreground">
        <div className="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <span className="mt-0.5 text-emerald-500">✓</span>
          <span>다양한 자산(주식, 코인, 현금, 부동산)을 통합 관리</span>
        </div>
        <div className="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <span className="mt-0.5 text-emerald-500">✓</span>
          <span>실시간 시세 연동 및 수익률 분석</span>
        </div>
        <div className="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <span className="mt-0.5 text-emerald-500">✓</span>
          <span>AES-256 암호화로 금융 데이터 보호</span>
        </div>
      </div>

      <Button className="w-full" size="lg" onClick={onNext}>
        시작하기
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Disclaimer
// ---------------------------------------------------------------------------

function DisclaimerStep({
  agreed,
  onToggle,
  onNext,
  onBack,
}: {
  agreed: boolean;
  onToggle: () => void;
  onNext: () => void;
  onBack: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="text-center">
        <h2 className="text-xl font-bold">면책 조항 동의</h2>
        <p className="mt-1 text-sm text-muted-foreground">서비스 이용 전 반드시 확인해주세요.</p>
      </div>

      <div className="max-h-60 overflow-y-auto rounded-lg border border-border bg-muted/30 p-4 text-sm leading-relaxed text-muted-foreground">
        <p className="mb-3 font-medium text-foreground">투자 리스크 고지</p>
        <p className="mb-2">
          WealthPilot은 자산 현황을 정리하고 시각화하는 도구이며, 투자 자문 서비스가 아닙니다.
          본 서비스에서 제공하는 시세, 수익률, 분석 데이터는 참고용이며, 이를 근거로 한 투자 결정에 대한
          책임은 전적으로 사용자에게 있습니다.
        </p>
        <p className="mb-3 font-medium text-foreground">데이터 정확성</p>
        <p className="mb-2">
          시세 데이터는 외부 API(yfinance, CoinGecko 등)로부터 제공되며, 실시간 데이터와 차이가
          있을 수 있습니다. 시세 조회 실패, 지연, 오류 등으로 인한 데이터 부정확성에 대해
          WealthPilot은 책임을 지지 않습니다.
        </p>
        <p className="mb-3 font-medium text-foreground">보안 및 개인정보</p>
        <p>
          모든 금융 데이터는 AES-256 암호화하여 저장하며, 서비스 제공 목적 외에는 사용하지 않습니다.
          다만, 인터넷을 통한 데이터 전송은 100% 안전을 보장할 수 없으므로, 사용자는 본인의 계정
          보안(2FA 활성화, 비밀번호 관리 등)에 주의를 기울여야 합니다.
        </p>
      </div>

      <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-muted/50">
        <input
          type="checkbox"
          checked={agreed}
          onChange={onToggle}
          className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
        />
        <span className="text-sm">
          위 면책 조항을 모두 읽었으며, 이에 <strong>동의합니다</strong>.
        </span>
      </label>

      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={onBack}>
          이전
        </Button>
        <Button className="flex-1" onClick={onNext} disabled={!agreed}>
          동의하고 계속하기
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Two-Factor Auth
// ---------------------------------------------------------------------------

function TwoFactorStep({
  isAlreadySetup,
  subStep,
  setupData,
  otpCode,
  loading,
  onSetup,
  onOtpChange,
  onVerify,
  onQrNext,
  onVerifyBack,
  onNext,
  onBack,
}: {
  isAlreadySetup: boolean;
  subStep: "intro" | "qr" | "verify" | "done";
  setupData: TotpSetupResponse | null;
  otpCode: string;
  loading: boolean;
  onSetup: () => void;
  onOtpChange: (v: string) => void;
  onVerify: () => void;
  onQrNext: () => void;
  onVerifyBack: () => void;
  onNext: () => void;
  onBack: () => void;
}) {
  // 이미 2FA 설정 완료된 경우
  if (isAlreadySetup) {
    return (
      <div className="space-y-4 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10">
          <svg className="h-8 w-8 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold">2단계 인증 설정 완료</h2>
        <p className="text-sm text-muted-foreground">이미 2FA가 활성화되어 있습니다.</p>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onBack}>
            이전
          </Button>
          <Button className="flex-1" onClick={onNext}>
            다음
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h2 className="text-xl font-bold">2단계 인증 설정</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          보안을 위해 Google Authenticator 또는 호환 앱으로 2FA를 설정해주세요.
        </p>
      </div>

      {/* Intro */}
      {subStep === "intro" && (
        <div className="space-y-4">
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>1. Google Authenticator 앱을 설치해주세요.</p>
            <p>2. 아래 버튼을 눌러 QR 코드를 생성합니다.</p>
            <p>3. QR 코드를 스캔하고 인증 코드를 입력합니다.</p>
          </div>
          <Button className="w-full" onClick={onSetup} disabled={loading}>
            {loading ? "QR 코드 생성 중..." : "QR 코드 생성"}
          </Button>
          <Button variant="outline" className="w-full" onClick={onBack}>
            이전
          </Button>
        </div>
      )}

      {/* QR Code */}
      {subStep === "qr" && setupData && (
        <div className="space-y-4">
          <div className="flex justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/png;base64,${setupData.qr_code_base64}`}
              alt="2FA QR Code"
              className="rounded-lg"
              width={200}
              height={200}
            />
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">QR 코드를 스캔할 수 없다면 직접 입력:</p>
            <code className="block rounded bg-muted p-2 text-center font-mono text-xs break-all">
              {setupData.secret}
            </code>
          </div>
          <Button className="w-full" onClick={onQrNext}>
            다음: 인증 코드 입력
          </Button>
        </div>
      )}

      {/* Verify OTP */}
      {subStep === "verify" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            인증 앱에 표시된 6자리 코드를 입력해주세요.
          </p>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={6}
            placeholder="000000"
            value={otpCode}
            onChange={(e) => onOtpChange(e.target.value.replace(/\D/g, ""))}
            className="w-full rounded-lg border border-border bg-background px-4 py-3 text-center font-mono text-2xl tracking-[0.5em] placeholder:text-muted-foreground/50 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/50"
            autoFocus
          />
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={onVerifyBack}>
              뒤로
            </Button>
            <Button className="flex-1" onClick={onVerify} disabled={otpCode.length !== 6 || loading}>
              {loading ? "확인 중..." : "인증 확인"}
            </Button>
          </div>
        </div>
      )}

      {/* Done */}
      {subStep === "done" && (
        <div className="space-y-4 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10">
            <svg className="h-8 w-8 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="text-lg font-medium">2FA 설정 완료!</p>
          <p className="text-sm text-muted-foreground">
            이제 로그인할 때마다 인증 코드를 입력해야 합니다.
          </p>
          <Button className="w-full" onClick={onNext}>
            다음 단계로
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 4: Asset Type Selection
// ---------------------------------------------------------------------------

function AssetTypeStep({
  selected,
  onToggle,
  onNext,
  onBack,
  onSkip,
}: {
  selected: AssetType[];
  onToggle: (type: AssetType) => void;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="text-center">
        <h2 className="text-xl font-bold">어떤 자산을 보유하고 계세요?</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          해당하는 자산 유형을 선택해주세요. (복수 선택 가능)
        </p>
      </div>

      <div className="grid grid-cols-1 gap-2">
        {ASSET_TYPE_VALUES.map((type) => {
          const isSelected = selected.includes(type);
          return (
            <button
              key={type}
              type="button"
              onClick={() => onToggle(type)}
              className={`flex items-center gap-3 rounded-lg border p-3 text-left text-sm transition-colors ${
                isSelected
                  ? "border-primary bg-primary/5 text-foreground"
                  : "border-border text-muted-foreground hover:bg-muted/50"
              }`}
            >
              <span className="text-lg">{ASSET_TYPE_ICONS[type]}</span>
              <span className="font-medium">{assetTypeLabels[type]}</span>
              {isSelected && (
                <svg className="ml-auto h-4 w-4 text-primary" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={onBack}>
          이전
        </Button>
        <Button className="flex-1" onClick={onNext} disabled={selected.length === 0}>
          다음
        </Button>
      </div>
      <Button variant="ghost" className="w-full text-muted-foreground" onClick={onSkip}>
        건너뛰기
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 5: Asset Registration Guide
// ---------------------------------------------------------------------------

function AssetGuideStep({
  selectedTypes,
  onNext,
  onBack,
  onSkip,
}: {
  selectedTypes: AssetType[];
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const typesToShow = selectedTypes.length > 0 ? selectedTypes : ASSET_TYPE_VALUES.slice(0, 3);

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h2 className="text-xl font-bold">자산 등록 가이드</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          선택한 자산 유형별 등록 방법을 안내해드립니다.
        </p>
      </div>

      <div className="max-h-72 space-y-3 overflow-y-auto">
        {typesToShow.map((type) => {
          const guide = ASSET_TYPE_GUIDES[type];
          return (
            <div key={type} className="rounded-lg border border-border p-3">
              <p className="mb-2 text-sm font-medium">
                {ASSET_TYPE_ICONS[type]} {guide.title}
              </p>
              <ol className="space-y-1 text-xs text-muted-foreground">
                {guide.steps.map((step, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="font-mono text-muted-foreground/60">{i + 1}.</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          );
        })}
      </div>

      <p className="text-center text-xs text-muted-foreground">
        대시보드에서 언제든지 자산을 추가할 수 있습니다.
      </p>

      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={onBack}>
          이전
        </Button>
        <Button className="flex-1" onClick={onNext}>
          다음
        </Button>
      </div>
      <Button variant="ghost" className="w-full text-muted-foreground" onClick={onSkip}>
        건너뛰기
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 6: Completion
// ---------------------------------------------------------------------------

function CompletionStep({
  loading,
  onComplete,
  onBack,
}: {
  loading: boolean;
  onComplete: () => void;
  onBack: () => void;
}) {
  return (
    <div className="space-y-6 text-center">
      <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl bg-emerald-500/10">
        <svg className="h-10 w-10 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>

      <div>
        <h2 className="text-2xl font-bold">설정 완료!</h2>
        <p className="mt-2 text-muted-foreground">
          모든 초기 설정이 완료되었습니다.
          <br />
          이제 자산 현황을 확인해보세요.
        </p>
      </div>

      <div className="space-y-2 text-left text-sm text-muted-foreground">
        <div className="flex items-center gap-2 rounded-lg bg-muted/50 p-3">
          <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          <span>면책 조항 동의 완료</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-muted/50 p-3">
          <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          <span>2단계 인증 설정 완료</span>
        </div>
      </div>

      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={onBack}>
          이전
        </Button>
        <Button className="flex-1" size="lg" onClick={onComplete} disabled={loading}>
          {loading ? "처리 중..." : "대시보드로 이동"}
        </Button>
      </div>
    </div>
  );
}
