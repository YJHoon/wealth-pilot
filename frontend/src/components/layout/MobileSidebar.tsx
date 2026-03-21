"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import {
  BarChart2,
  Coins,
  FolderKanban,
  History,
  LineChart,
  Newspaper,
  Settings,
  Shield,
  Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "대시보드", icon: BarChart2 },
  { href: "/assets", label: "자산", icon: Wallet },
  { href: "/groups", label: "그룹", icon: FolderKanban },
  { href: "/analysis", label: "분석", icon: LineChart },
  { href: "/spending", label: "지출", icon: Coins },
  { href: "/news", label: "뉴스", icon: Newspaper },
  { href: "/history", label: "이력", icon: History },
  { href: "/security", label: "보안", icon: Shield },
  { href: "/settings", label: "설정", icon: Settings },
];

export function MobileSidebar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // 경로 변경 시 자동 닫기
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // ESC 키로 닫기
  useEffect(() => {
    if (!open) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [open]);

  // 열릴 때 body 스크롤 방지
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const close = useCallback(() => setOpen(false), []);

  return (
    <>
      {/* 햄버거 버튼 — 모바일에서만 표시 */}
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="메뉴 열기"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* 오버레이 + 드로어 */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          {/* 배경 오버레이 */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={close}
            aria-hidden="true"
          />

          {/* 사이드 드로어 */}
          <aside className="absolute inset-y-0 left-0 w-64 bg-background border-r border-border shadow-xl animate-in slide-in-from-left duration-200">
            {/* 헤더 */}
            <div className="flex h-14 items-center justify-between border-b border-border px-4">
              <span className="text-sm font-semibold tracking-tight">WealthPilot</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={close}
                aria-label="메뉴 닫기"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* 네비게이션 */}
            <nav className="flex-1 overflow-y-auto py-3">
              <ul className="space-y-0.5 px-2">
                {navItems.map(({ href, label, icon: Icon }) => {
                  const isActive = pathname === href || pathname.startsWith(`${href}/`);
                  return (
                    <li key={href}>
                      <Link
                        href={href}
                        className={cn(
                          "flex items-center gap-2.5 rounded-md px-3 py-2.5 text-sm transition-colors",
                          isActive
                            ? "bg-accent text-accent-foreground font-medium"
                            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        {label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </aside>
        </div>
      )}
    </>
  );
}
