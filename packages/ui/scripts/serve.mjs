/**
 * Stand-in for CloudFront in e2e (web-shell and infra specs): serves an app's static export,
 * routes /api and /auth to its API, and adds the security headers the response headers policy
 * adds. Shared by every Atesta web app (ADR-017). Usage, from the app's directory:
 * node node_modules/@atesta/ui/scripts/serve.mjs   (PORT 3000, API_ORIGIN http://127.0.0.1:8000,
 * NO_REFERRER: comma-separated path prefixes sent with Referrer-Policy no-referrer)
 */
import { readFileSync } from "node:fs";
import { request as forward, createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const ROOT = process.cwd();
const OUT = join(ROOT, "out");
const API = new URL(process.env.API_ORIGIN ?? "http://127.0.0.1:8000");
const { policy } = JSON.parse(readFileSync(join(ROOT, "csp-policy.json"), "utf8"));
const NO_REFERRER = (process.env.NO_REFERRER ?? "").split(",").filter(Boolean);
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".woff2": "font/woff2" };

function securityHeaders(path) {
  return {
    "content-security-policy": policy,
    "strict-transport-security": "max-age=63072000; includeSubDomains; preload",
    "x-content-type-options": "nosniff",
    "referrer-policy": NO_REFERRER.some((p) => path.startsWith(p)) ? "no-referrer" : "same-origin",
  };
}

function resolveFile(path) {
  const clean = normalize(decodeURIComponent(path)).replace(/^(\.\.[/\\])+/, "");
  for (const candidate of [clean, `${clean}.html`, join(clean, "index.html")]) {
    try {
      return { body: readFileSync(join(OUT, candidate)), type: TYPES[extname(candidate)] ?? "application/octet-stream" };
    } catch {}
  }
  return null;
}

createServer((req, res) => {
  const { pathname } = new URL(req.url, "http://localhost");
  if (pathname.startsWith("/api/") || pathname.startsWith("/auth/")) {
    const upstream = forward({ host: API.hostname, port: API.port, method: req.method, path: req.url, headers: req.headers }, (answer) => {
      res.writeHead(answer.statusCode ?? 502, answer.headers);
      answer.pipe(res);
    });
    upstream.on("error", () => res.writeHead(502).end());
    req.pipe(upstream);
    return;
  }
  const found = resolveFile(pathname === "/" ? "/index.html" : pathname);
  const file = found ?? resolveFile("/404.html");
  res.writeHead(found ? 200 : 404, { ...securityHeaders(pathname), "content-type": file?.type ?? "text/plain" });
  res.end(file?.body ?? "");
}).listen(Number(process.env.PORT ?? 3000));
