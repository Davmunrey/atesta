import type { Metadata } from "next";
import { type ReactNode, Suspense } from "react";
import { fontVariables } from "@atesta/ui/fonts";
import { PortalShell } from "@/components/portal-shell";
import messages from "../../messages/es.json";
import "./globals.css";
import { Providers } from "./providers";

// Staff only: no search engine lists the portal.
export const metadata: Metadata = { title: messages.portal.title, robots: { index: false, follow: false } };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es" className={fontVariables}>
      <body className="min-h-dvh bg-bg font-sans text-fg antialiased">
        <Providers><Suspense><PortalShell>{children}</PortalShell></Suspense></Providers>
      </body>
    </html>
  );
}
