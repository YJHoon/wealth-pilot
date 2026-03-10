"use client";

import { Eye, EyeOff, Monitor, Moon, Sun, TerminalSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";

export function Header() {
  const { viewMode, setViewMode, isMasked, toggleMask, theme, toggleTheme } =
    useAppStore();

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-4">
      {/* 모바일 로고 (사이드바 없을 때) */}
      <div className="lg:hidden text-sm font-semibold">WealthPilot</div>
      <div className="hidden lg:block" />

      {/* 우측 컨트롤 */}
      <div className="flex items-center gap-1">
        {/* 뷰 모드 토글 */}
        <div className="flex items-center rounded-md border border-border p-0.5">
          <Button
            variant={viewMode === "minimal" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1.5 px-2.5 text-xs"
            onClick={() => setViewMode("minimal")}
            title="미니멀 모드"
          >
            <Monitor className="h-3.5 w-3.5" />
            미니멀
          </Button>
          <Button
            variant={viewMode === "terminal" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1.5 px-2.5 text-xs"
            onClick={() => setViewMode("terminal")}
            title="터미널 모드"
          >
            <TerminalSquare className="h-3.5 w-3.5" />
            터미널
          </Button>
        </div>

        <Separator orientation="vertical" className="h-5 mx-1" />

        {/* 금액 마스킹 토글 */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={toggleMask}
          title={isMasked ? "금액 보기" : "금액 숨기기"}
        >
          {isMasked ? (
            <EyeOff className="h-4 w-4" />
          ) : (
            <Eye className="h-4 w-4" />
          )}
        </Button>

        {/* 테마 토글 */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={toggleTheme}
          title={theme === "dark" ? "라이트 모드" : "다크 모드"}
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </Button>
      </div>
    </header>
  );
}
