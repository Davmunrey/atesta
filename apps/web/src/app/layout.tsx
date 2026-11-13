import type { Metadata } from "next";
import type { ReactNode } from "react";
import localFont from "next/font/local";
import messages from "../../messages/es.json";
import "./globals.css";
import { Providers } from "./providers";

const sans = localFont({ src: "../styles/fonts/ibm-plex-sans-latin-wght-normal.woff2", variable: "--font-plex-sans", weight: "100 700", display: "swap" });
const display = localFont({ src: "../styles/fonts/newsreader-latin-wght-normal.woff2", variable: "--font-newsreader", weight: "200 800", display: "swap" });
const mono = localFont({ src: "../styles/fonts/ibm-plex-mono-latin-400-normal.woff2", variable: "--font-plex-mono", weight: "400", display: "swap", preload: false });

export const metadata: Metadata = { title: messages.brand.name };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es" className={`${sans.variable} ${display.variable} ${mono.variable}`}>
      <body className="min-h-dvh bg-bg font-sans text-fg antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
