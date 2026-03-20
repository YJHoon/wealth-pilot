"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded bg-muted ${className ?? ""}`} />
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      {/* TotalAssetCard skeleton */}
      <Card>
        <CardHeader>
          <SkeletonBlock className="h-4 w-24" />
        </CardHeader>
        <CardContent className="space-y-3">
          <SkeletonBlock className="h-10 w-48" />
          <div className="flex gap-4">
            <SkeletonBlock className="h-5 w-32" />
            <SkeletonBlock className="h-5 w-24" />
          </div>
        </CardContent>
      </Card>

      {/* Charts row skeleton */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <SkeletonBlock className="h-4 w-32" />
          </CardHeader>
          <CardContent>
            <SkeletonBlock className="h-52 w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <SkeletonBlock className="h-4 w-32" />
          </CardHeader>
          <CardContent>
            <SkeletonBlock className="h-52 w-full" />
          </CardContent>
        </Card>
      </div>

      {/* Group cards skeleton */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Card key={i} size="sm">
            <CardHeader>
              <SkeletonBlock className="h-4 w-20" />
            </CardHeader>
            <CardContent className="space-y-2">
              <SkeletonBlock className="h-6 w-32" />
              <SkeletonBlock className="h-2 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
