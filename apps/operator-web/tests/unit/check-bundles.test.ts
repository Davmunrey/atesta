import { expect, it } from "vitest";
import { leaks, ownTexts, routes } from "../../scripts/check-bundles";

it("lists an export's routes without the root and error pages", () => {
  expect(routes(["index.html", "404.html", "_not-found.html", "team.html", "app/org.html", "x.js"])).toEqual(["/team", "/app/org"]);
});

it("keeps only long texts that the other app does not have", () => {
  const mine = { portal: { name: "Portal de operaciones de Atesta", short: "Equipo" }, shared: { retry: "Reintentar la solicitud ahora" } };
  const theirs = { app: { retry: "Reintentar la solicitud ahora" } };
  expect(ownTexts([mine], [theirs])).toEqual(["Portal de operaciones de Atesta"]);
});

it("catches a planted route and a planted text", () => {
  const files = { "index.html": "<p>hola</p>", "team.html": "", "_next/static/chunks/a.js": 'x="Portal de operaciones de Atesta"' };
  expect(leaks(files, ["/team", "/log"], ["Portal de operaciones de Atesta"])).toEqual([
    "route /team", '_next/static/chunks/a.js: "Portal de operaciones de Atesta"']);
  expect(leaks({ "index.html": "" }, ["/team"], ["Portal de operaciones de Atesta"])).toEqual([]);
});
