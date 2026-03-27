import {
  BarChart2,
  Bot,
  Coins,
  FolderKanban,
  History,
  LineChart,
  Newspaper,
  Settings,
  Shield,
  Star,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const navItems: NavItem[] = [
  { href: "/dashboard", label: "대시보드", icon: BarChart2 },
  { href: "/assets", label: "자산", icon: Wallet },
  { href: "/trading", label: "자동매매", icon: Bot },
  { href: "/groups", label: "그룹", icon: FolderKanban },
  { href: "/analysis", label: "분석", icon: LineChart },
  { href: "/watchlist", label: "관심종목", icon: Star },
  { href: "/spending", label: "지출", icon: Coins },
  { href: "/news", label: "뉴스", icon: Newspaper },
  { href: "/history", label: "이력", icon: History },
  { href: "/security", label: "보안", icon: Shield },
  { href: "/settings", label: "설정", icon: Settings },
];
