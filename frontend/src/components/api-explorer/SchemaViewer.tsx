"use client";

import { useState } from "react";
import type { SchemaObject } from "./ApiExplorer";

interface Props {
  schema: SchemaObject;
  schemas: Record<string, SchemaObject>;
  depth: number;
  fieldName?: string;
  required?: boolean;
}

function resolveRef(ref: string, schemas: Record<string, SchemaObject>): SchemaObject | null {
  const name = ref.replace("#/components/schemas/", "");
  return schemas[name] ?? null;
}

function resolveSchema(schema: SchemaObject, schemas: Record<string, SchemaObject>): SchemaObject {
  if (schema.$ref) {
    const resolved = resolveRef(schema.$ref, schemas);
    return resolved ?? schema;
  }
  if (schema.anyOf?.length) {
    const nonNull = schema.anyOf.find((s) => s.type !== "null");
    if (nonNull) return resolveSchema(nonNull, schemas);
  }
  if (schema.allOf?.length) {
    const merged = schema.allOf
      .map((s) => resolveSchema(s, schemas))
      .reduce<SchemaObject>(
        (acc, cur) => ({
          ...acc,
          ...cur,
          properties: {
            ...(acc.properties ?? {}),
            ...(cur.properties ?? {}),
          },
          required: Array.from(new Set([...(acc.required ?? []), ...(cur.required ?? [])])),
        }),
        {}
      );
    return merged;
  }
  return schema;
}

function getTypeBadge(schema: SchemaObject): string {
  if (schema.$ref) return schema.$ref.split("/").pop() ?? "object";
  if (schema.anyOf) {
    const types = schema.anyOf.map((s) => s.type ?? s.$ref?.split("/").pop() ?? "?").join(" | ");
    return types;
  }
  if (schema.type === "array" && schema.items) {
    const itemType = schema.items.$ref
      ? schema.items.$ref.split("/").pop()
      : schema.items.type;
    return `${itemType}[]`;
  }
  return schema.format ? `${schema.type}(${schema.format})` : schema.type ?? "any";
}

const TYPE_COLORS: Record<string, string> = {
  string: "text-emerald-400",
  integer: "text-blue-400",
  number: "text-blue-400",
  boolean: "text-amber-400",
  array: "text-violet-400",
  object: "text-indigo-400",
  any: "text-zinc-500",
};

export function SchemaViewer({ schema, schemas, depth, fieldName, required }: Props) {
  const [collapsed, setCollapsed] = useState(depth > 1);

  const resolved = resolveSchema(schema, schemas);
  const typeBadge = getTypeBadge(schema);
  const typeColor =
    TYPE_COLORS[resolved.type ?? ""] ??
    (resolved.properties ? TYPE_COLORS.object : TYPE_COLORS.any);

  const hasChildren = !!resolved.properties || (resolved.type === "array" && resolved.items);
  const indent = depth * 16;

  // 중첩 객체 렌더링
  if (hasChildren && resolved.properties) {
    return (
      <div className="rounded-lg bg-zinc-900/40 border border-zinc-800/50 overflow-hidden">
        {depth === 0 && !fieldName ? null : (
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-zinc-800/30 transition-colors"
            style={{ paddingLeft: indent + 12 }}
          >
            <svg
              className={`w-3 h-3 text-zinc-600 transition-transform ${collapsed ? "" : "rotate-90"}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            {fieldName && (
              <span className="font-mono text-xs text-zinc-300 font-semibold">{fieldName}</span>
            )}
            {required && <span className="text-[10px] text-red-400">*</span>}
            <span className={`font-mono text-[11px] ${typeColor}`}>{typeBadge}</span>
          </button>
        )}

        {!collapsed && (
          <div className="divide-y divide-zinc-800/40">
            {Object.entries(resolved.properties ?? {}).map(([name, propSchema]) => (
              <SchemaViewer
                key={name}
                schema={propSchema}
                schemas={schemas}
                depth={depth + 1}
                fieldName={name}
                required={resolved.required?.includes(name)}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // 배열 아이템
  if (resolved.type === "array" && resolved.items) {
    return (
      <div style={{ paddingLeft: indent }}>
        <div className="flex items-start gap-2 px-3 py-2">
          {fieldName && (
            <span className="font-mono text-xs text-zinc-300 font-semibold">{fieldName}</span>
          )}
          {required && <span className="text-[10px] text-red-400 mt-0.5">*</span>}
          <span className={`font-mono text-[11px] ${typeColor}`}>{typeBadge}</span>
        </div>
        <div className="pl-4">
          <SchemaViewer schema={resolved.items} schemas={schemas} depth={depth + 1} fieldName="items" />
        </div>
      </div>
    );
  }

  // 단순 필드
  return (
    <div
      className="flex items-start gap-2 px-3 py-2 hover:bg-zinc-800/20 transition-colors"
      style={{ paddingLeft: Math.max(12, indent + 12) }}
    >
      {fieldName && (
        <>
          <span className="font-mono text-xs text-zinc-200 font-semibold min-w-[100px]">{fieldName}</span>
          {required && <span className="text-[10px] text-red-400 mt-0.5">*</span>}
        </>
      )}
      <span className={`font-mono text-[11px] ${typeColor}`}>{typeBadge}</span>
      {resolved.description && (
        <span className="text-xs text-zinc-600 flex-1 truncate ml-2">{resolved.description}</span>
      )}
      {resolved.enum && (
        <span className="text-[10px] text-zinc-600 ml-1">
          [{resolved.enum.map((v) => JSON.stringify(v)).join(", ")}]
        </span>
      )}
      {resolved.default !== undefined && (
        <span className="text-[10px] text-zinc-700 ml-1">= {JSON.stringify(resolved.default)}</span>
      )}
    </div>
  );
}
