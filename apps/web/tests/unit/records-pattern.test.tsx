// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ActivityView } from "@/components/activity-view";
import { changedDays, OwnerInsights, ProgressInsights } from "@/components/insights";
import { IntegrationsView } from "@/components/integrations-view";
import { PoliciesView } from "@/components/policies-view";
import type { Register } from "@/lib/api/register-hooks";
import { renderWithProviders, stubApi } from "./render";

// Records pages, charts and nesting (console-unification spec, part 2).
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const approval = (on: string) => ({ version: "1.0", approver_name: "Comité", approved_on: on, sha256: null, recorded_at: `${on}T00:00:00Z` });
const policy = (id: string, latest: string | null, next: string | null) => ({ id, title: id, location_url: "https://example.com/p", review_months: 12, created_at: "2026-01-01T00:00:00Z", latest: latest ? approval(latest) : null, next_review_on: next });

it("leads a records page with one sentence holding only the figures that need action, and no tiles", async () => {
  vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-11-23T12:00:00Z"));
  stubApi({ "GET /api/v1/orgs/primary/policies": [200, [policy("Copias", "2025-01-10", "2026-01-10"), policy("Uso", null, null), policy("Seguridad", "2026-06-01", "2027-06-01")]] });
  renderWithProviders(<PoliciesView org={owner} />);
  const lead = (await screen.findByText(/revisión vencida/)).closest(".record-summary")!;
  expect(lead.tagName).toBe("P");
  expect(lead.textContent).toBe("Requiere acción 1 política con la revisión vencida y 1 política sin aprobar.");
  expect(document.querySelector(".kpis, .kpi, dl")).toBeNull();
  expect(screen.queryByText("Aprobadas y al día")).toBeNull();
  // The register is the page: it follows the sentence, and the form comes after it.
  const order = [...document.querySelectorAll(".panel-grid > *")].map((el) => el.className.split(" ")[0]);
  expect(order.slice(1, 3)).toEqual(["record-summary", "panel"]);
});

it("says why nothing needs action, without a zero or a total", async () => {
  stubApi({ "GET /api/v1/orgs/primary/policies": [200, [policy("Seguridad", "2026-06-01", "2999-06-01")]] });
  renderWithProviders(<PoliciesView org={owner} />);
  const lead = (await screen.findByText("Todas las políticas están aprobadas y al día.")).closest(".record-summary")!;
  expect(within(lead as HTMLElement).getByText("Al día").closest(".badge")?.getAttribute("data-severity")).toBe("done");
  expect(lead.textContent).not.toMatch(/\d/);
});

it("does not make the last use of a key a headline figure", async () => {
  const token = { id: "t", name: "CI", prefix: "atesta_x", scopes: ["evidence:write"], rate_limit_per_minute: 60, read_only: false, created_at: "2026-11-01T00:00:00Z",
    created_by_email: "a@example.test", expires_at: "2999-01-01T00:00:00Z", revoked_at: null, last_used_at: "2026-11-20T10:00:00Z" };
  stubApi({ "GET /api/v1/orgs/primary/api-tokens": [200, [token]] });
  renderWithProviders(<IntegrationsView org={owner} />);
  const lead = (await screen.findByText("Hay al menos un token activo.")).closest(".record-summary")!;
  expect(lead.textContent).not.toContain("Último uso");
});

const day = (n: number) => `2026-11-${String(n).padStart(2, "0")}`;
it("counts the days a series moved", () => {
  expect(changedDays([1, 1, 2, 2, 3].map((value, i) => ({ label: day(i + 1), value })))).toBe(3);
  expect(changedDays([])).toBe(0);
});

const base = "/api/v1/orgs/primary/frameworks/synthetic_alpha";
const register = { framework_key: "synthetic_alpha", framework_version: "2", catalog_version: "c", axes: {}, groups_es: [], term_labels: [], profiles: [], scope_guide: null, scope: null, review: null, items: [] } as unknown as Register;
const history = (values: number[]) => values.map((implemented, i) => ({ day: day(i + 1), assessed: implemented, implemented, not_applicable: 0 }));

it.each([[[1, 2, 3, 4, 5, 6, 6, 6], false], [[1, 2, 3, 4, 5, 6, 7], true]] as const)(
  "draws the ENS trend only with 7 days of change (%j)", async (values, shown) => {
    stubApi({ [`GET ${base}/register/history`]: [200, history([...values])], [`GET ${base}/trend`]: [200, []] });
    renderWithProviders(<ProgressInsights orgId="primary" frameworkKey="synthetic_alpha" register={register} />);
    if (shown) expect(await screen.findByRole("img", { name: /Medidas implantadas a lo largo del tiempo/ })).toBeTruthy();
    else {
      expect(await screen.findByText("La evolución aparece cuando el registro haya cambiado en al menos 7 días distintos.")).toBeTruthy();
      expect(screen.queryByRole("img")).toBeNull();
    }
  });

it.each([[6, false], [7, true]] as const)("draws actions per day only with activity on 7 days (%i days)", async (days, shown) => {
  stubApi({ "GET /api/v1/orgs/primary/activity": [200, { days: 30, daily: Array.from({ length: 10 }, (_, i) => ({ day: day(i + 1), count: i < days ? 2 : 0 })),
    events: [{ occurred_at: "2026-11-22T10:00:00Z", actor_email: "ana@example.test", action: "requirement.assessed", target_type: "requirement", target_id: "ens:org.1" }] }] });
  renderWithProviders(<ActivityView org={{ ...owner, role: "admin" }} />);
  expect(await screen.findByText("Evaluó una medida")).toBeTruthy();
  expect(screen.queryAllByRole("img", { name: "Acciones por día" })).toHaveLength(shown ? 1 : 0);
});

it("compares people with bars only when two or more own measures", async () => {
  const owned = (owner_user_id: string, code: string) => ({ code, title_es: code, title_en: null, selection_basis: null, proposal: { decision: "undecided", rule: null, level: null },
    assessment: null, assignment: { owner_user_id, due_on: null, assigned_at: "2026-11-20T10:00:00Z" } });
  const members = [{ user_id: "u-ana", email: "ana@example.test", display_name: null, role: "admin" }, { user_id: "u-luis", email: "luis@example.test", display_name: null, role: "member" }];
  stubApi({ "GET /api/v1/orgs/primary/members": [200, members] });
  renderWithProviders(<OwnerInsights orgId="primary" register={{ ...register, items: [owned("u-ana", "a.1"), owned("u-ana", "a.2")] } as unknown as Register} />);
  expect(await screen.findByText("ana@example.test tiene las 2 medidas abiertas asignadas.")).toBeTruthy();
  expect(document.querySelector(".ranked-bars")).toBeNull();
  cleanup();
  renderWithProviders(<OwnerInsights orgId="primary" register={{ ...register, items: [owned("u-ana", "a.1"), owned("u-luis", "a.2")] } as unknown as Register} />);
  expect(await screen.findByText("luis@example.test")).toBeTruthy();
  expect(document.querySelector(".ranked-bars")).not.toBeNull();
});

it("never boxes figures inside a panel", () => {
  const css = readFileSync(join(__dirname, "../../src/styles/framework.css"), "utf8");
  const tiles = css.split("\n").filter((line) => /^\s*\.stat-tiles( > div)? \{/.test(line)).join("\n");
  expect(tiles).not.toMatch(/background|border-radius|border:/);
  const console_ = readFileSync(join(__dirname, "../../src/styles/console.css"), "utf8");
  expect(console_).not.toMatch(/\.kpis\b/);
});
