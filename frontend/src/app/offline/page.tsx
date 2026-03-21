"use client";

import { WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function OfflinePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-4 text-center">
      <WifiOff className="h-16 w-16 text-muted-foreground" />
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">
          오프라인 상태입니다
        </h1>
        <p className="text-sm text-muted-foreground">
          인터넷 연결을 확인한 후 다시 시도해 주세요.
        </p>
      </div>
      <Button onClick={() => window.location.reload()}>새로고침</Button>
    </div>
  );
}
