"use client";

import { useState, useEffect } from "react";

/**
 * 미디어 쿼리 상태를 추적하는 훅
 * SSR에서는 false를 반환하고, 클라이언트에서 실제 매치 결과를 반환한다.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);

    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);

  return matches;
}
