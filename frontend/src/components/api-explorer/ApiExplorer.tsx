"use client";

import { useCallback, useEffect, useState } from "react";
import { EndpointCard } from "./EndpointCard";

export interface OpenAPISpec {
  info: { title: string; version: string; description?: string };
  paths: Record<string, Record<string, PathItem>>;
  components?: {
    schemas?: Record<string, SchemaObject>;
  };
  tags?: Array<{ name: string; description?: string }>;
}

export interface PathItem {
  summary?: string;
  description?: string;
  tags?: string[];
  operationId?: string;
  parameters?: Parameter[];
  requestBody?: RequestBody;
  responses?: Record<string, Response>;
  security?: Record<string, string[]>[];
}

export interface Parameter {
  name: string;
  in: "query" | "path" | "header" | "cookie";
  required?: boolean;
  description?: string;
  schema?: SchemaObject;
}

export interface RequestBody {
  required?: boolean;
  content?: Record<string, { schema?: SchemaObject }>;
  description?: string;
}

export interface Response {
  description?: string;
  content?: Record<string, { schema?: SchemaObject }>;
}

export interface SchemaObject {
  type?: string;
  format?: string;
  description?: string;
  properties?: Record<string, SchemaObject>;
  items?: SchemaObject;
  required?: string[];
  enum?: unknown[];
  $ref?: string;
  anyOf?: SchemaObject[];
  allOf?: SchemaObject[];
  example?: unknown;
  default?: unknown;
  pattern?: string;
}

export interface EndpointInfo {
  method: string;
  path: string;
  item: PathItem;
}

const METHOD_ORDER = ["get", "post", "put", "patch", "delete"];

function groupByTag(paths: OpenAPISpec["paths"]): Record<string, EndpointInfo[]> {
  const groups: Record<string, EndpointInfo[]> = {};

  for (const [path, methods] of Object.entries(paths)) {
    for (const method of METHOD_ORDER) {
      const item = methods[method] as PathItem | undefined;
      if (!item) continue;

      const tags = item.tags?.length ? item.tags : ["기타"];
      for (const tag of tags) {
        if (!groups[tag]) groups[tag] = [];
        groups[tag].push({ method, path, item });
      }
    }
  }

  return groups;
}

export function ApiExplorer() {
  const [spec, setSpec] = useState<OpenAPISpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const fetchSpec = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${backendUrl}/openapi.json`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: OpenAPISpec = await res.json();
      setSpec(data);
      setLastFetched(new Date());
    } catch (e) {
      setError(
        e instanceof Error
          ? `백엔드 서버에 연결할 수 없습니다: ${e.message}\n${backendUrl}/openapi.json 확인`
          : "알 수 없는 오류"
      );
    } finally {
      setLoading(false);
    }
  }, [backendUrl]);

  useEffect(() => {
    fetchSpec();
  }, [fetchSpec]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950">
        <div className="text-center space-y-4">
          <div className="relative mx-auto w-12 h-12">
            <div className="absolute inset-0 rounded-full border-2 border-indigo-500/30 animate-ping" />
            <div className="absolute inset-0 rounded-full border-2 border-t-indigo-400 border-zinc-800 animate-spin" />
          </div>
          <p className="text-zinc-400 text-sm">API 스펙 로딩 중...</p>
        </div>
      </div>
    );
  }

  if (error || !spec) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950">
        <div className="max-w-md text-center space-y-4 p-8 rounded-2xl border border-red-900/50 bg-red-950/20">
          <div className="text-4xl">⚠️</div>
          <p className="text-red-400 font-semibold">연결 실패</p>
          <pre className="text-zinc-500 text-xs text-left whitespace-pre-wrap">{error}</pre>
          <button
            onClick={fetchSpec}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm transition-colors"
          >
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  const groups = groupByTag(spec.paths);
  const tagNames = Object.keys(groups);

  const effectiveSelectedTag = selectedTag && groups[selectedTag] ? selectedTag : (tagNames[0] ?? null);

  const filteredEndpoints = effectiveSelectedTag
    ? groups[effectiveSelectedTag]?.filter((e) => {
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
          e.path.toLowerCase().includes(q) ||
          e.item.summary?.toLowerCase().includes(q) ||
          e.method.toLowerCase().includes(q)
        );
      }) ?? []
    : [];

  const totalCount = new Set(
    Object.values(groups).flat().map((e) => `${e.method}:${e.path}`)
  ).size;

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950 text-zinc-100 font-sans">
      {/* 사이드바 */}
      <aside className="w-64 flex-shrink-0 border-r border-zinc-800/60 flex flex-col">
        {/* 헤더 */}
        <div className="p-5 border-b border-zinc-800/60">
          <div className="flex items-center gap-2.5 mb-1">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-xs font-bold shadow-lg shadow-indigo-900/40">
              API
            </div>
            <span className="font-semibold text-sm text-zinc-100">{spec.info.title}</span>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 border border-indigo-500/20 font-mono">
              v{spec.info.version}
            </span>
            <span className="text-[10px] text-zinc-500">{totalCount}개 엔드포인트</span>
          </div>
        </div>

        {/* 태그 목록 */}
        <nav className="flex-1 overflow-y-auto p-3 space-y-0.5">
          <p className="text-[10px] text-zinc-600 uppercase tracking-wider px-2 pb-2 pt-1">태그</p>
          {tagNames.map((tag) => (
            <button
              key={tag}
              onClick={() => { setSelectedTag(tag); setSearchQuery(""); }}
              className={`w-full flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-all text-left group ${
                effectiveSelectedTag === tag
                  ? "bg-indigo-500/15 text-indigo-300 border border-indigo-500/20"
                  : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200 border border-transparent"
              }`}
            >
              <span className="truncate">{tag}</span>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                  effectiveSelectedTag === tag
                    ? "bg-indigo-500/25 text-indigo-400"
                    : "bg-zinc-800 text-zinc-500 group-hover:bg-zinc-700"
                }`}
              >
                {groups[tag]?.length ?? 0}
              </span>
            </button>
          ))}
        </nav>

        {/* 하단 정보 */}
        <div className="p-3 border-t border-zinc-800/60 space-y-2">
          <button
            onClick={fetchSpec}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 text-xs transition-all border border-zinc-700/30"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            새로고침
          </button>
          {lastFetched && (
            <p className="text-[10px] text-zinc-600 text-center">
              {lastFetched.toLocaleTimeString("ko-KR")} 기준
            </p>
          )}
        </div>
      </aside>

      {/* 메인 패널 */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* 상단 바 */}
        <header className="flex items-center gap-3 px-6 py-4 border-b border-zinc-800/60 flex-shrink-0">
          <div className="flex-1">
            <h1 className="text-base font-semibold text-zinc-100">{effectiveSelectedTag}</h1>
            <p className="text-xs text-zinc-500 mt-0.5">{filteredEndpoints.length}개 엔드포인트</p>
          </div>
          <div className="relative w-64">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="엔드포인트 검색..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-zinc-800/60 border border-zinc-700/40 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500/50 focus:bg-zinc-800 transition-all"
            />
          </div>
          <a
            href={`${backendUrl}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 text-xs transition-all border border-zinc-700/30"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            Swagger UI
          </a>
        </header>

        {/* 엔드포인트 목록 */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {filteredEndpoints.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="text-4xl mb-3">🔍</div>
              <p className="text-zinc-500 text-sm">검색 결과가 없습니다</p>
            </div>
          ) : (
            filteredEndpoints.map((endpoint, i) => (
              <EndpointCard
                key={`${endpoint.method}-${endpoint.path}-${i}`}
                endpoint={endpoint}
                schemas={spec.components?.schemas ?? {}}
              />
            ))
          )}
        </div>
      </main>
    </div>
  );
}
