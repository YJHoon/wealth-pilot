import { MinimalDashboard } from "@/components/dashboard/MinimalDashboard";

export default function DashboardPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">대시보드</h1>
      <MinimalDashboard />
    </div>
  );
}
