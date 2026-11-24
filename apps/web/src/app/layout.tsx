import type { Metadata } from "next";
import type { ReactNode } from "react";
import { fontVariables } from "@atesta/ui/fonts";
import messages from "../../messages/es.json";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = { title: messages.brand.name };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es" className={fontVariables}>
      <body className="min-h-dvh bg-bg font-sans text-fg antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
