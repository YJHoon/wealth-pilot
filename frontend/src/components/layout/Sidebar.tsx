"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-56 flex-col border-r border-border bg-background">
      {/* 로고 */}
      <div className="flex h-14 items-center px-4 border-b border-border">
        <span className="text-sm font-semibold tracking-tight">WealthPilot</span>
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
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
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
  );
}
