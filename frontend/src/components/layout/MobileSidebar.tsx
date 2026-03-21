"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { navItems } from "@/config/navigation";

export function MobileSidebar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const asideRef = useRef<HTMLElement>(null);
  const prevOpenRef = useRef(false);
  const prevOverflowRef = useRef("");

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

  // 열릴 때 body 스크롤 방지 (기존 overflow 값 보존)
  useEffect(() => {
    if (open) {
      prevOverflowRef.current = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = prevOverflowRef.current;
    }
    return () => {
      document.body.style.overflow = prevOverflowRef.current;
    };
  }, [open]);

  // 포커스 관리: 열릴 때 닫기 버튼에 포커스, 닫힐 때 트리거에 포커스 복원
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => closeBtnRef.current?.focus());
    } else if (prevOpenRef.current) {
      triggerRef.current?.focus();
    }
    prevOpenRef.current = open;
  }, [open]);

  // 포커스 트랩: aside 내부에서만 Tab 순환
  useEffect(() => {
    if (!open) return;
    const aside = asideRef.current;
    if (!aside) return;

    const handleTab = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const focusable = aside.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleTab);
    return () => document.removeEventListener("keydown", handleTab);
  }, [open]);

  const close = useCallback(() => setOpen(false), []);

  return (
    <>
      {/* 햄버거 버튼 — 모바일에서만 표시 */}
      <Button
        ref={triggerRef}
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
          <aside
            ref={asideRef}
            role="dialog"
            aria-modal="true"
            aria-label="네비게이션 메뉴"
            className="absolute inset-y-0 left-0 w-64 bg-background border-r border-border shadow-xl animate-in slide-in-from-left duration-200"
          >
            {/* 헤더 */}
            <div className="flex h-14 items-center justify-between border-b border-border px-4">
              <span className="text-sm font-semibold tracking-tight">WealthPilot</span>
              <Button
                ref={closeBtnRef}
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
                        onClick={close}
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
