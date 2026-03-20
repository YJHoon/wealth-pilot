import { create } from "zustand";
import { persist } from "zustand/middleware";

type ViewMode = "minimal" | "terminal";
type Theme = "dark" | "light";

interface AppState {
  // 뷰 모드: 미니멀(기본) ↔ 트레이딩 터미널
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;

  // 금액 마스킹 (기본: true — 보안 원칙)
  isMasked: boolean;
  toggleMask: () => void;

  // 테마 (기본: dark)
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      viewMode: "minimal",
      setViewMode: (mode) => set({ viewMode: mode }),

      isMasked: false,
      toggleMask: () => set((state) => ({ isMasked: !state.isMasked })),

      theme: "dark",
      setTheme: (theme) => set({ theme }),
      toggleTheme: () =>
        set((state) => ({ theme: state.theme === "dark" ? "light" : "dark" })),
    }),
    {
      name: "wealthpilot-app-store",
      // viewMode, isMasked, theme 모두 localStorage에 저장
      partialize: (state) => ({
        viewMode: state.viewMode,
        isMasked: state.isMasked,
        theme: state.theme,
      }),
    }
  )
);
