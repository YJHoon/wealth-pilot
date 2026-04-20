"use client";

/**
 * 국내 종목 자동완성 콤보박스.
 *
 * 사용자는 종목명(삼성전자) 또는 6자리 코드로 검색해 선택한다.
 * `mode="multiple"` — 체크박스처럼 여러 종목 선택, chip 표시.
 * `mode="single"` — 단일 선택, 선택 즉시 드롭다운 닫힘.
 */

import { useEffect, useId, useRef, useState } from "react";
import { Search, X, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useTickerSearch, type TickerSearchItem } from "@/hooks/useTickerSearch";

interface BaseProps {
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** 외부에서 주입한 초기 이름 매핑 (ticker → name). 사용자가 아직 검색 안 했어도 chip에 이름 표시. */
  resolvedNames?: Record<string, string>;
}

interface MultipleProps extends BaseProps {
  mode: "multiple";
  value: string[];
  onChange: (next: string[]) => void;
  max?: number;
}

interface SingleProps extends BaseProps {
  mode: "single";
  value: string | null;
  onChange: (ticker: string | null, item: TickerSearchItem | null) => void;
}

type Props = MultipleProps | SingleProps;

export function TickerCombobox(props: Props) {
  const { placeholder = "종목명 또는 코드 검색 (예: 삼성전자)", disabled, className, resolvedNames = {} } = props;
  const { query, setQuery, results, loading, error } = useTickerSearch();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [nameCache, setNameCache] = useState<Record<string, string>>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();

  // 검색 결과의 이름을 캐시해두어 chip 라벨에 재사용
  useEffect(() => {
    if (results.length === 0) return;
    setNameCache((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const r of results) {
        if (next[r.ticker] !== r.name) {
          next[r.ticker] = r.name;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [results]);

  // 바깥 클릭 시 드롭다운 닫기
  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  // 결과 바뀌면 하이라이트 초기화
  useEffect(() => {
    setActiveIndex(0);
  }, [results]);

  const selectItem = (item: TickerSearchItem) => {
    if (props.mode === "multiple") {
      if (props.value.includes(item.ticker)) return;
      if (props.max && props.value.length >= props.max) return;
      props.onChange([...props.value, item.ticker]);
      setQuery("");
      inputRef.current?.focus();
    } else {
      props.onChange(item.ticker, item);
      setQuery("");
      setOpen(false);
    }
  };

  const removeItem = (ticker: string) => {
    if (props.mode === "multiple") {
      props.onChange(props.value.filter((t) => t !== ticker));
    } else {
      props.onChange(null, null);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) setOpen(true);
      setActiveIndex((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const hit = results[activeIndex];
      if (hit) selectItem(hit);
    } else if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key === "Backspace" && !query && props.mode === "multiple" && props.value.length > 0) {
      props.onChange(props.value.slice(0, -1));
    }
  };

  const labelOf = (ticker: string) =>
    resolvedNames[ticker] ?? nameCache[ticker] ?? ticker;

  const selectedTickers =
    props.mode === "multiple" ? props.value : props.value ? [props.value] : [];
  const maxReached =
    props.mode === "multiple" && props.max != null && props.value.length >= props.max;

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <div
        className={cn(
          "flex flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5 focus-within:ring-2 focus-within:ring-ring",
          disabled && "opacity-60",
        )}
      >
        {selectedTickers.map((t) => (
          <Badge key={t} variant="secondary" className="gap-1 pr-1">
            <span className="text-xs">
              {labelOf(t)} <span className="text-muted-foreground">({t})</span>
            </span>
            <button
              type="button"
              aria-label={`${t} 제거`}
              className="ml-0.5 rounded-sm hover:bg-muted"
              onClick={() => removeItem(t)}
              disabled={disabled}
            >
              <X className="size-3" />
            </button>
          </Badge>
        ))}
        <div className="relative flex min-w-[8rem] flex-1 items-center">
          <Search className="pointer-events-none absolute left-1 size-3.5 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (!open) setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            placeholder={
              props.mode === "single" && props.value ? "" : maxReached ? "최대 개수 도달" : placeholder
            }
            disabled={disabled || maxReached || (props.mode === "single" && !!props.value)}
            role="combobox"
            aria-expanded={open}
            aria-controls={listboxId}
            aria-autocomplete="list"
            className="h-7 border-0 bg-transparent pl-6 text-sm shadow-none focus-visible:ring-0"
          />
        </div>
      </div>

      {open && query.trim() && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border border-border bg-popover shadow-md"
        >
          {loading && (
            <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
              <Loader2 className="size-3 animate-spin" /> 검색 중…
            </div>
          )}
          {error && !loading && (
            <div className="px-3 py-2 text-xs text-destructive">{error}</div>
          )}
          {!loading && !error && results.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">검색 결과 없음</div>
          )}
          {!loading && !error &&
            results.map((item, idx) => {
              const isSelected = selectedTickers.includes(item.ticker);
              const isActive = idx === activeIndex;
              return (
                <button
                  key={item.ticker}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => selectItem(item)}
                  disabled={isSelected}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm",
                    isActive && !isSelected && "bg-accent",
                    isSelected && "cursor-not-allowed opacity-60",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{item.name}</span>
                    <span className="text-xs text-muted-foreground">{item.ticker}</span>
                  </span>
                  <Badge variant="outline" className="text-[10px]">
                    {item.market}
                  </Badge>
                </button>
              );
            })}
        </div>
      )}
    </div>
  );
}
