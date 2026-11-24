import localFont from "next/font/local";

// Self-hosted faces (styles/fonts/README.md); tokens.css reads them through these variables.
const sans = localFont({ src: "./styles/fonts/ibm-plex-sans-latin-wght-normal.woff2", variable: "--font-plex-sans", weight: "100 700", display: "swap" });
const display = localFont({ src: "./styles/fonts/newsreader-latin-wght-normal.woff2", variable: "--font-newsreader", weight: "200 800", display: "swap" });
const mono = localFont({ src: "./styles/fonts/ibm-plex-mono-latin-400-normal.woff2", variable: "--font-plex-mono", weight: "400", display: "swap", preload: false });

/** The class names that define the three font variables; the root `<html>` carries them. */
export const fontVariables = `${sans.variable} ${display.variable} ${mono.variable}`;
