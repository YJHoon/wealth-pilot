import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";

export default async function RootPage() {
  const session = await auth();

  if (!session) {
    redirect("/login");
  }

  // 2FA 미설정 시 설정 페이지로
  if (session.totpSetupRequired) {
    redirect("/security/2fa/setup");
  }

  redirect("/dashboard");
}
