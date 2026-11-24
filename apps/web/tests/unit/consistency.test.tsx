// @vitest-environment jsdom
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthGate } from "@/components/auth-gate";
import { IncidentsView } from "@/components/incidents-view";
import { MembersView } from "@/components/members-view";
import { MyWorkView } from "@/components/my-work-view";
import { ReportView, monthsUpTo } from "@/components/report-view";
import { STATE_SEVERITY } from "@/lib/severity";
import es from "../../messages/es.json";
import { renderWithProviders, stubApi } from "./render";

// Consistency and Spanish (console-unification spec, part 3).
vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const ORG = "primary";
const owner = { organization_id: ORG, organization_name: "Acme", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const src = join(__dirname, "../../src");
const css = (name: string) => readFileSync(join(src, "styles", name), "utf8");
const components = join(src, "components");

it("styles selects in forms like every other field", () => {
  expect(css("console.css")).toMatch(/\.routine-form :is\(input, textarea, select\), \.field \{[^}]*border: 1px solid var\(--color-border\)/);
});

it("draws every console badge from the one severity mapping", () => {
  // Public and landing views are another lane; the connections screen joined in issue 397.
  const own = readdirSync(components).filter((f) => f.endsWith(".tsx") && f !== "badge.tsx");
  const handmade = own.filter((f) => /className="badge"/.test(readFileSync(join(components, f), "utf8")));
  expect(handmade).toEqual([]);
  // "Sin aprobar" looks the same everywhere: the policy badge and the home's task use one severity.
  expect(STATE_SEVERITY.policyUnapproved).toBe("missing");
  expect(readFileSync(join(components, "readiness.tsx"), "utf8")).toContain('d.kind === "policy_unapproved" ? "missing"');
});

it("makes removing a member a button, confirmed with the danger action", async () => {
  stubApi({
    "GET /api/v1/me": [200, { id: "u-ana", email: "ana@example.com", email_verified: true, locale: "es", memberships: [owner] }],
    [`GET /api/v1/orgs/${ORG}/members`]: [200, [{ user_id: "u-ana", email: "ana@example.com", display_name: null, role: "owner" },
      { user_id: "u-cai", email: "cai@example.com", display_name: null, role: "member" }]],
  });
  renderWithProviders(<AuthGate><MembersView org={owner} /></AuthGate>);
  const remove = (await screen.findAllByRole("button", { name: "Quitar" }))[0]!;
  expect(remove.className).toBe("dashboard-button");
  fireEvent.click(remove);
  expect(screen.getByRole("button", { name: "Confirmar" }).className).toBe("button-danger");
  expect(screen.getByRole("combobox", { name: /Rol de cai@example.com/ }).className).toBe("field");
});

it("does not repeat the page title on the register panel", async () => {
  stubApi({ [`GET /api/v1/orgs/${ORG}/incidents`]: [200, []], [`GET /api/v1/orgs/${ORG}/incidents/criteria`]: [200, []] });
  renderWithProviders(<IncidentsView org={owner} />);
  await screen.findByText("No hay incidentes registrados.");
  expect(screen.getAllByRole("heading", { name: "Incidentes" })).toHaveLength(1);
});

it("bounds page descriptions, takes placeholders from the muted token and keeps room for the assistant", () => {
  const console_ = css("console.css");
  expect(console_).toMatch(/\.page-description \{ max-width: 72ch;/);
  expect(console_).toMatch(/\.console-page :is\(input, textarea\)::placeholder \{ color: var\(--color-muted\);/);
  expect(console_).toMatch(/body:has\(\.assistant-launcher\) \.console-page \{ padding-bottom:/);
  expect(console_).toMatch(/html:has\(\.console\):has\(\.assistant-launcher\) \{ scroll-padding-bottom:/);
});

it("offers an owner the way to assign measures, never 'an administrator can'", async () => {
  stubApi({ [`GET /api/v1/orgs/${ORG}/my-work`]: [200, []] });
  renderWithProviders(<MyWorkView org={owner} />);
  const assign = await screen.findByRole("link", { name: "Asigna medidas desde Marcos" });
  expect(assign.getAttribute("href")).toBe(`/app/frameworks?org=${ORG}`);
  expect(screen.queryByText(/administra/)).toBeNull();
  cleanup();
  renderWithProviders(<MyWorkView org={{ ...owner, role: "member" }} />);
  expect(await screen.findByText(/Quien administra la organización las asigna/)).toBeTruthy();
});

it("names report months in the interface language", async () => {
  expect(monthsUpTo("2026-02", 3)).toEqual(["2026-02", "2026-01", "2025-12"]);
  stubApi({ [`GET /api/v1/orgs/${ORG}/report`]: [404, {}] });
  renderWithProviders(<ReportView org={owner} initialMonth="2026-11" />);
  const month = screen.getByRole("combobox", { name: "Mes" });
  expect((month as HTMLSelectElement).selectedOptions[0]!.textContent).toBe("noviembre de 2026");
  cleanup();
  renderWithProviders(<ReportView org={owner} initialMonth="2026-11" />, "en");
  expect((screen.getByRole("combobox", { name: "Month" }) as HTMLSelectElement).selectedOptions[0]!.textContent).toBe("November 2026");
});

const PUBLIC = new Set(["landing", "public", "producto", "ens", "seguridad", "consultoras", "cookies", "footer", "legal", "home", "notFound", "brand", "locale"]);
function leaves(tree: object, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([k, v]) => typeof v === "object" && v !== null ? leaves(v, prefix ? `${prefix}.${k}` : k) : [[prefix ? `${prefix}.${k}` : k, String(v)]]);
}

it("addresses the reader as tú in every console string", () => {
  const vosotros = /\b(vuestr[oa]s?|vosotr[oa]s|os|usted(es)?|\p{L}+(steis|áis|éis))\b/iu;
  const offenders = leaves(es).filter(([key, value]) => !PUBLIC.has(key.split(".")[0]!) && vosotros.test(value)).map(([key]) => key);
  expect(offenders).toEqual([]);
  // The assistant's answers speak to the same reader.
  const faq = readFileSync(join(src, "content/assistant-faq.json"), "utf8");
  expect(faq.match(vosotros)).toBeNull();
});

it("uses plain terms: no 'Encargados' for owners, no 'de un vistazo', no slogans", () => {
  const app = leaves(es).filter(([key]) => !PUBLIC.has(key.split(".")[0]!)).map(([, v]) => v);
  expect(app.filter((v) => /Encargados|de un vistazo|Todo lo que pide el auditor|evidencias solas|Qué está comprobado, qué falta/.test(v))).toEqual([]);
  expect(es.insights.owners).toBe("Responsables de medidas");
});
