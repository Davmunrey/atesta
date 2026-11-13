import type { ReactNode } from "react";
import { SiteFooter } from "@/components/site-footer";

export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="public-surface flex min-h-dvh flex-col bg-bg text-fg">
      {children}
      <SiteFooter />
    </div>
  );
}
