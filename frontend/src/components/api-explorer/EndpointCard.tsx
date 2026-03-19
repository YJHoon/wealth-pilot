"use client";

import { useEffect, useState } from "react";
import type { EndpointInfo, SchemaObject } from "./ApiExplorer";
import { SchemaViewer } from "./SchemaViewer";

const METHOD_STYLES: Record<string, { badge: string; border: string; text: string }> = {
  get:    { badge: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30", border: "border-emerald-500/25 hover:border-emerald-500/50", text: "text-emerald-400" },
  post:   { badge: "bg-blue-500/15 text-blue-400 border-blue-500/30",         border: "border-blue-500/25 hover:border-blue-500/50",     text: "text-blue-400" },
  put:    { badge: "bg-amber-500/15 text-amber-400 border-amber-500/30",       border: "border-amber-500/25 hover:border-amber-500/50",   text: "text-amber-400" },
  patch:  { badge: "bg-orange-500/15 text-orange-400 border-orange-500/30",    border: "border-orange-500/25 hover:border-orange-500/50", text: "text-orange-400" },
  delete: { badge: "bg-red-500/15 text-red-400 border-red-500/30",             border: "border-red-500/25 hover:border-red-500/50",       text: "text-red-400" },
};

const STATUS_COLOR: Record<string, string> = {
  "2": "text-emerald-400",
  "4": "text-amber-400",
  "5": "text-red-400",
};

interface Props {
  endpoint: EndpointInfo;
  schemas: Record<string, SchemaObject>;
}

export function EndpointCard({ endpoint, schemas }: Props) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"params" | "body" | "responses">("responses");

  const style = METHOD_STYLES[endpoint.method] ?? METHOD_STYLES.get;
  const { item } = endpoint;

  const hasParams = (item.parameters?.length ?? 0) > 0;
  const hasBody = !!item.requestBody;
  const hasResponses = !!item.responses && Object.keys(item.responses).length > 0;

  useEffect(() => {
    if (hasResponses) setActiveTab("responses");
    else if (hasBody) setActiveTab("body");
    else if (hasParams) setActiveTab("params");
  }, [hasResponses, hasBody, hasParams]);

  const requiresAuth = item.security !== undefined && item.security.length > 0;

  const formattedPath = endpoint.path;

  return (
    <div
      className={`rounded-xl border bg-zinc-900/50 transition-all duration-200 ${style.border} ${open ? "shadow-lg shadow-black/20" : ""}`}
    >
      {/* 헤더 — 클릭으로 열기/닫기 */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3.5 text-left group"
      >
        <span
          className={`flex-shrink-0 text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border font-mono min-w-[52px] text-center ${style.badge}`}
        >
          {endpoint.method}
        </span>

        <span className="flex-1 font-mono text-sm text-zinc-200 truncate">
          {formattedPath.split(/(\{[^}]+\})/).map((part, i) =>
            part.startsWith("{") ? (
              <span key={i} className={`${style.text} font-bold`}>{part}</span>
            ) : (
              <span key={i}>{part}</span>
            )
          )}
        </span>

        {item.summary && (
          <span className="hidden md:block text-xs text-zinc-500 truncate max-w-xs">{item.summary}</span>
        )}

        <div className="flex items-center gap-2 flex-shrink-0">
          {requiresAuth && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700/50 text-zinc-500 flex items-center gap-1">
              <span>🔒</span>
            </span>
          )}
          <svg
            className={`w-4 h-4 text-zinc-600 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* 확장 영역 */}
      {open && (
        <div className="border-t border-zinc-800/60 px-4 pb-4 pt-3 space-y-4">
          {/* 설명 */}
          {item.description && (
            <p className="text-sm text-zinc-400 leading-relaxed">{item.description}</p>
          )}

          {/* 탭 */}
          <div className="flex gap-1 border-b border-zinc-800/60 pb-0">
            {hasParams && (
              <TabButton active={activeTab === "params"} onClick={() => setActiveTab("params")}>
                파라미터 <span className="ml-1 text-[10px]">({item.parameters?.length})</span>
              </TabButton>
            )}
            {hasBody && (
              <TabButton active={activeTab === "body"} onClick={() => setActiveTab("body")}>
                요청 Body
              </TabButton>
            )}
            {hasResponses && (
              <TabButton active={activeTab === "responses"} onClick={() => setActiveTab("responses")}>
                응답
              </TabButton>
            )}
          </div>

          {/* 탭 콘텐츠 */}
          <div className="min-h-[60px]">
            {activeTab === "params" && hasParams && (
              <div className="space-y-2">
                {item.parameters?.map((param, i) => (
                  <div key={i} className="flex items-start gap-3 py-2 border-b border-zinc-800/40 last:border-0">
                    <span className="font-mono text-xs text-indigo-400 font-semibold min-w-[100px]">{param.name}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 border border-zinc-700/40 uppercase">{param.in}</span>
                    {param.required && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">required</span>}
                    <span className="text-xs text-zinc-500 flex-1">{param.description ?? param.schema?.type ?? ""}</span>
                  </div>
                ))}
              </div>
            )}

            {activeTab === "body" && hasBody && (
              <div className="space-y-2">
                {Object.entries(item.requestBody?.content ?? {}).map(([mime, content]) => (
                  <div key={mime}>
                    <p className="text-[10px] text-zinc-600 mb-2 font-mono">{mime}</p>
                    {content.schema && (
                      <SchemaViewer schema={content.schema} schemas={schemas} depth={0} />
                    )}
                  </div>
                ))}
              </div>
            )}

            {activeTab === "responses" && hasResponses && (
              <div className="space-y-3">
                {Object.entries(item.responses ?? {}).map(([code, response]) => {
                  const colorClass = STATUS_COLOR[code[0]] ?? "text-zinc-400";
                  const hasContent = !!response.content && Object.keys(response.content).length > 0;
                  return (
                    <div key={code} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className={`font-mono text-sm font-bold ${colorClass}`}>{code}</span>
                        <span className="text-xs text-zinc-500">{response.description}</span>
                      </div>
                      {hasContent && Object.entries(response.content ?? {}).map(([mime, content]) => (
                        <div key={mime} className="pl-4">
                          <p className="text-[10px] text-zinc-600 mb-1.5 font-mono">{mime}</p>
                          {content.schema && (
                            <SchemaViewer schema={content.schema} schemas={schemas} depth={0} />
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            )}

            {/* 탭이 없을 때 */}
            {!hasParams && !hasBody && !hasResponses && (
              <p className="text-xs text-zinc-600 py-2">상세 정보 없음</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs rounded-t-lg border-b-2 transition-all ${
        active
          ? "border-indigo-500 text-indigo-300 bg-indigo-500/5"
          : "border-transparent text-zinc-500 hover:text-zinc-300"
      }`}
    >
      {children}
    </button>
  );
}
