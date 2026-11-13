import { Suspense, type ReactNode } from "react";
import { AppHeader } from "@/components/app-header";
import { AuthGate } from "@/components/auth-gate";
import { OrganizationNav } from "@/components/organization-nav";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <AppHeader />
      <div className="workspace">
        <Suspense><OrganizationNav /></Suspense>
        <main id="main-content" tabIndex={-1} className="workspace-main">{children}</main>
      </div>
    </AuthGate>
  );
}
