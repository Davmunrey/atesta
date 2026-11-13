import type { ReactNode } from "react";
import { AppHeader } from "@/components/app-header";
import { AuthGate } from "@/components/auth-gate";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <AppHeader />
      <main className="mx-auto max-w-4xl px-6 py-8">{children}</main>
    </AuthGate>
  );
}
