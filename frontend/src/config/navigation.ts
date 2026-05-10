import {
  BarChart2,
  Bot,
  ClipboardList,
  LineChart,
  Settings,
  Shield,
  Sparkles,
  Star,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

export const navSections: NavSection[] = [
  {
    label: "홈",
    items: [
      { href: "/dashboard", label: "대시보드", icon: BarChart2 },
    ],
  },
  {
    label: "투자",
    items: [
      { href: "/assets", label: "내 자산", icon: Wallet },
      { href: "/advisory", label: "원클릭 분석", icon: Sparkles },
      { href: "/trading", label: "자동매매", icon: Bot },
      { href: "/orders", label: "매매 내역", icon: ClipboardList },
    ],
  },
  {
    label: "리서치",
    items: [
      { href: "/analysis", label: "종목 분석", icon: LineChart },
      { href: "/watchlist", label: "관심종목", icon: Star },
    ],
  },
  {
    label: "설정",
    items: [
      { href: "/security", label: "보안", icon: Shield },
      { href: "/settings", label: "설정", icon: Settings },
    ],
  },
];

/** 플랫 리스트 (하위 호환) */
export const navItems: NavItem[] = navSections.flatMap((s) => s.items);
