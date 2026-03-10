"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { TotpVerifyResponse } from "@/types/auth";

export default function TwoFactorVerifyPage() {
  const { data: session, update } = useSession();
  const router = useRouter();

  const [otpCode, setOtpCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const accessToken = session?.accessToken;

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
        // 세션 업데이트: totp_verified=True 토큰으로 교체
        await update({
          accessToken: data.access_token,
          totpRequired: false,
        });
        router.push("/dashboard");
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
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle>2단계 인증</CardTitle>
          <CardDescription>
            인증 앱에 표시된 6자리 코드를 입력해주세요.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {error && (
            <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

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

          <Button
            className="w-full"
            onClick={handleVerify}
            disabled={otpCode.length !== 6 || loading}
          >
            {loading ? "확인 중..." : "인증 확인"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
