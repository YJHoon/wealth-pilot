"use client";

import { SessionProvider } from "next-auth/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { IdleTimeoutProvider } from "@/components/providers/IdleTimeoutProvider";
import { Toaster } from "@/components/ui/sonner";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <TooltipProvider>
        <IdleTimeoutProvider>
          {children}
          <Toaster position="top-right" richColors />
        </IdleTimeoutProvider>
      </TooltipProvider>
    </SessionProvider>
  );
}
