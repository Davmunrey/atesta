import type { Metadata } from "next";
import type { ReactNode } from "react";
import { I18nProvider } from "@/i18n/provider";
import "./globals.css";

export const metadata: Metadata = { title: "Atesta" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-dvh bg-bg font-sans text-fg antialiased">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
