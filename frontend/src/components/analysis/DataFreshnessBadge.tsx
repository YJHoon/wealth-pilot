"use client";

import { Badge } from "@/components/ui/badge";
import { Clock } from "lucide-react";

interface DataFreshnessBadgeProps {
  dataSource: string | null;
  updatedAt: string | null;
}

export function DataFreshnessBadge({ dataSource, updatedAt }: DataFreshnessBadgeProps) {
  const formattedTime = updatedAt
    ? new Date(updatedAt).toLocaleString("ko-KR", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="flex items-center gap-2">
      {dataSource && (
        <Badge variant="secondary" className="text-xs font-normal">
          {dataSource}
        </Badge>
      )}
      {formattedTime && (
        <Badge variant="outline" className="gap-1 text-xs font-normal text-muted-foreground">
          <Clock className="size-3" />
          {formattedTime}
        </Badge>
      )}
    </div>
  );
}
