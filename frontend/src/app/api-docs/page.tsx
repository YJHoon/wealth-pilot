import { ApiExplorer } from "@/components/api-explorer/ApiExplorer";

export const metadata = {
  title: "API Explorer — WealthPilot",
  description: "WealthPilot 백엔드 API 탐색기",
};

export default function ApiDocsPage() {
  return <ApiExplorer />;
}
