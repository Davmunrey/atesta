import type { ReactNode } from "react";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public/public-footer";

export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="public-surface flex min-h-dvh flex-col bg-bg text-fg">
      <PublicHeader />
      {children}
      <PublicFooter />
    </div>
  );
}
