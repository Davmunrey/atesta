import { Suspense, type ReactNode } from "react";
import { AppHeader } from "@/components/app-header";
import { AuthGate } from "@/components/auth-gate";
import { OrganizationNav } from "@/components/organization-nav";
import { SiteFooter } from "@/components/site-footer";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <div className="flex min-h-dvh flex-col">
      <AppHeader />
      <div className="workspace w-full flex-1">
        <Suspense><OrganizationNav /></Suspense>
        <main id="main-content" tabIndex={-1} className="workspace-main">{children}</main>
      </div>
      <SiteFooter />
      </div>
    </AuthGate>
  );
}
