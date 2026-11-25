/**
 * Each app ships only its own screens (ADR-017, "What each bundle holds"): after both builds, the
 * console's export holds no portal route or text and the portal's none of the console's.
 * Usage, from apps/operator-web after both builds: node scripts/check-bundles.ts ../web/out out
 */
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

type Tree = Record<string, unknown>;
const leaves = (tree: Tree): string[] => Object.values(tree).flatMap((v) =>
  v !== null && typeof v === "object" ? leaves(v as Tree) : [String(v)]);

/** Texts one app has and the other does not; long enough not to occur by chance. */
export function ownTexts(mine: Tree[], theirs: Tree[]): string[] {
  const other = new Set(theirs.flatMap(leaves));
  return [...new Set(mine.flatMap(leaves))].filter((t) => t.length >= 24 && !other.has(t) && !/[{}'"\\]/.test(t));
}

/** Routes of an export: its HTML files, without the shared root and error pages. */
export function routes(files: string[]): string[] {
  return files.filter((f) => f.endsWith(".html")).map((f) => `/${f.replace(/(index)?\.html$/, "")}`.replace(/\/$/, "") || "/")
    .filter((r) => !["/", "/404", "/_not-found"].includes(r));
}

/** What one export holds of another app: its routes, its texts. */
export function leaks(files: Record<string, string>, foreignRoutes: string[], foreignTexts: string[]): string[] {
  const own = new Set(routes(Object.keys(files)));
  return [
    ...foreignRoutes.filter((r) => own.has(r)).map((r) => `route ${r}`),
    ...Object.entries(files).flatMap(([name, body]) => foreignTexts.filter((t) => body.includes(t)).map((t) => `${name}: "${t.slice(0, 40)}"`)),
  ];
}

function read(out: string): Record<string, string> {
  const walk = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(join(dir, e.name)) : /\.(html|js|txt)$/.test(e.name) ? [join(dir, e.name)] : []);
  return Object.fromEntries(walk(out).map((f) => [relative(out, f), readFileSync(f, "utf8")]));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [consoleOut, portalOut] = process.argv.slice(2) as [string, string];
  // Each app's texts: its messages; the portal's also include the operator API's error texts.
  const apps = fileURLToPath(new URL("../../", import.meta.url));
  const messages = (dir: string) => ["es", "en"].map((l) => JSON.parse(readFileSync(join(apps, dir, `${l}.json`), "utf8")) as Tree);
  const [web, portal] = [messages("web/messages"), [...messages("operator-web/messages"), ...messages("operator/contract/messages")]];
  const [webFiles, portalFiles] = [read(consoleOut), read(portalOut)];
  const found = [
    ...leaks(webFiles, routes(Object.keys(portalFiles)), ownTexts(portal, web)).map((l) => `console holds portal ${l}`),
    ...leaks(portalFiles, routes(Object.keys(webFiles)), ownTexts(web, portal)).map((l) => `portal holds console ${l}`),
  ];
  for (const line of found) console.error(line);
  console.log(`bundles: ${found.length} leaks; ${routes(Object.keys(webFiles)).length} console and ${routes(Object.keys(portalFiles)).length} portal routes`);
  process.exit(found.length > 0 ? 1 : 0);
}
