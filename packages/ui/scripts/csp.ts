/**
 * Build step (web-shell spec, security headers): writes the Content-Security-Policy that
 * CloudFront sends (infra spec applies it). A static export has no per-request nonce, and one
 * hash per page grew the header towards CloudFront's limit (#212), so every inline script moves
 * into a same-origin file named by its SHA-256 and `script-src 'self'` covers it.
 * Usage, from the app's directory after next build: node node_modules/@atesta/ui/scripts/csp.ts.
 * Shared by every Atesta web app (ADR-017); writes csp-policy.json next to the app's out/.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** CloudFront quota "Maximum length of the Content-Security-Policy header value" (AWS docs,
 * CloudFront quotas, checked 2026-11-13). Adjustable via Service Quotas if ever needed. */
export const CLOUDFRONT_CSP_LIMIT = 1783;

const SCRIPT = /<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g;
const INLINE = /<script((?![^>]*\ssrc=)[^>]*)>([\s\S]*?)<\/script>/g;
const JS_TYPE = /\stype=["']?(?!(?:text\/javascript|module)["'\s>])([^"'\s>]+)/i;

export type ScriptFile = { path: string; body: string };

/** Moves every inline script into `/_next/static/inline/<sha256>.js`, loaded by a classic
 *  `<script src>` in the same place: it runs in the same order, before parsing goes on. A script
 *  of another type (JSON data, templates) would lose its content, so it stops the build. */
export function externalize(html: string): { html: string; files: ScriptFile[] } {
  const files: ScriptFile[] = [];
  const out = html.replace(INLINE, (_whole, attributes: string, body: string) => {
    if (body.length === 0) return _whole;
    const type = attributes.match(JS_TYPE)?.[1];
    if (type) throw new Error(`cannot move an inline script of type ${type} out of the page`);
    const path = `/_next/static/inline/${createHash("sha256").update(body, "utf8").digest("hex")}.js`;
    files.push({ path, body });
    return `<script${attributes} src="${path}"></script>`;
  });
  return { html: out, files };
}
const STYLE = /<style[\s>]|\sstyle="/g;

export const inlineScripts = (html: string): string[] =>
  [...html.matchAll(SCRIPT)].map((m) => m[1] ?? "").filter((body) => body.length > 0);

export const inlineStyles = (html: string): number => html.match(STYLE)?.length ?? 0;

export const sha256 = (text: string): string =>
  `'sha256-${createHash("sha256").update(text, "utf8").digest("base64")}'`;

export function buildPolicy(hashes: string[]): string {
  const scripts = [...new Set(hashes)].sort().join(" ");
  const policy = [
    "default-src 'self'",
    ["script-src 'self'", scripts].filter(Boolean).join(" "),
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "object-src 'none'",
  ].join("; ");
  if (policy.length > CLOUDFRONT_CSP_LIMIT) {
    throw new Error(`CSP is ${policy.length} characters; CloudFront allows ${CLOUDFRONT_CSP_LIMIT}`);
  }
  return policy;
}

function htmlFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? htmlFiles(join(dir, entry.name)) : entry.name.endsWith(".html") ? [join(dir, entry.name)] : [],
  );
}

// The app runs this file through its node_modules link, so compare real paths.
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = process.cwd();
  const out = join(root, "out");
  const pages = htmlFiles(out).map((file) => {
    const moved = externalize(readFileSync(file, "utf8"));
    for (const script of moved.files) {
      mkdirSync(dirname(join(out, script.path)), { recursive: true });
      writeFileSync(join(out, script.path), script.body);
    }
    writeFileSync(file, moved.html);
    return { file, html: moved.html };
  });
  const styled = pages.filter((page) => inlineStyles(page.html) > 0).map((page) => page.file);
  if (styled.length > 0) throw new Error(`inline styles would be blocked by style-src 'self': ${styled.join(", ")}`);
  const hashes = pages.flatMap((page) => inlineScripts(page.html).map(sha256));
  const policy = buildPolicy(hashes);
  writeFileSync(join(root, "csp-policy.json"), `${JSON.stringify({ policy, hashes: [...new Set(hashes)].sort() }, null, 2)}\n`);
  console.log(`CSP: ${new Set(hashes).size} script hashes, ${policy.length}/${CLOUDFRONT_CSP_LIMIT} characters`);
}
