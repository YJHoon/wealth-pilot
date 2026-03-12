"use client";

import { SessionProvider } from "next-auth/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { IdleTimeoutProvider } from "@/components/providers/IdleTimeoutProvider";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <TooltipProvider>
        <IdleTimeoutProvider>{children}</IdleTimeoutProvider>
      </TooltipProvider>
    </SessionProvider>
  );
}
