"use client";

import { Suspense } from "react";
import OnboardingWizard from "@/components/onboarding/OnboardingWizard";

export default function OnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background">
          <p className="text-muted-foreground">로딩 중...</p>
        </div>
      }
    >
      <OnboardingWizard />
    </Suspense>
  );
}
