"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { TotpSetupResponse, TotpVerifyResponse } from "@/types/auth";

export default function TwoFactorSetupPage() {
  const { data: session, update } = useSession();
  const router = useRouter();

  const [step, setStep] = useState<"intro" | "qr" | "verify" | "done">("intro");
  const [setupData, setSetupData] = useState<TotpSetupResponse | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const accessToken = session?.accessToken;

  const handleSetup = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError("");

    try {
      const data = await apiFetch<TotpSetupResponse>("/api/auth/2fa/setup", {
        method: "POST",
        accessToken,
      });
      setSetupData(data);
      setStep("qr");
    } catch (e) {
      setError(e instanceof Error ? e.message : "2FA 설정에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
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
        setStep("done");
        // 세션 업데이트: totp_verified=True 토큰으로 교체, 2FA 상태 반영
        await update({
          accessToken: data.access_token,  // 새 토큰 (totp_verified=true)
          totpRequired: false,             // 이번 세션 OTP 검증 완료
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

  return (
    <div className="flex min-h-[80vh] items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle>2단계 인증 설정</CardTitle>
          <CardDescription>
            보안을 위해 Google Authenticator 또는 호환 앱으로
            <br />
            2단계 인증을 설정해주세요.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {error && (
            <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Step 1: 안내 */}
          {step === "intro" && (
            <div className="space-y-4">
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>1. Google Authenticator 앱을 설치해주세요.</p>
                <p>2. 아래 버튼을 눌러 QR 코드를 생성합니다.</p>
                <p>3. QR 코드를 스캔하고 인증 코드를 입력합니다.</p>
              </div>
              <Button className="w-full" onClick={handleSetup} disabled={loading}>
                {loading ? "QR 코드 생성 중..." : "QR 코드 생성"}
              </Button>
            </div>
          )}

          {/* Step 2: QR 코드 */}
          {step === "qr" && setupData && (
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
                <code className="block rounded bg-muted p-2 text-center text-xs font-mono break-all">
                  {setupData.secret}
                </code>
              </div>

              <Button className="w-full" onClick={() => setStep("verify")}>
                다음: 인증 코드 입력
              </Button>
            </div>
          )}

          {/* Step 3: 인증 코드 확인 */}
          {step === "verify" && (
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
                onChange={(e) => {
                  const v = e.target.value.replace(/\D/g, "");
                  setOtpCode(v);
                }}
                className="w-full rounded-lg border border-border bg-background px-4 py-3 text-center text-2xl font-mono tracking-[0.5em] placeholder:text-muted-foreground/50 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/50"
                autoFocus
              />
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => setStep("qr")}
                >
                  뒤로
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleVerify}
                  disabled={otpCode.length !== 6 || loading}
                >
                  {loading ? "확인 중..." : "인증 확인"}
                </Button>
              </div>
            </div>
          )}

          {/* Step 4: 완료 */}
          {step === "done" && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex size-16 items-center justify-center rounded-full bg-emerald-500/10">
                <svg
                  className="size-8 text-emerald-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-lg font-medium">2FA 설정 완료!</p>
              <p className="text-sm text-muted-foreground">
                이제 로그인할 때마다 인증 코드를 입력해야 합니다.
              </p>
              <Button className="w-full" onClick={() => router.push("/dashboard")}>
                대시보드로 이동
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
