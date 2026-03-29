"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { navSections } from "@/config/navigation";

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
        {navSections.map((section) => (
          <div key={section.label} className="mb-3">
            <p className="px-4 mb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/60">
              {section.label}
            </p>
            <ul className="space-y-0.5 px-2">
              {section.items.map(({ href, label, icon: Icon }) => {
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
          </div>
        ))}
      </nav>
    </aside>
  );
}
