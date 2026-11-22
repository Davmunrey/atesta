// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OwnerInsights } from "@/components/insights";
import { MyWorkView } from "@/components/my-work-view";
import { AssessmentForm } from "@/components/self-assessment";
import { isMyWorkOverdue, type MyWorkItem, type Register } from "@/lib/api/register-hooks";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const org = { organization_id: "primary", organization_name: "Synthetic Team", role: "member" as const, access_expires_on: null };
const work = (code: string, over: Partial<MyWorkItem> = {}): MyWorkItem => ({
  framework_key: "synthetic_alpha", framework_name: "Synthetic Alpha", code, title_es: `Medida ${code}`, title_en: null,
  due_on: null, applicability: null, implementation: null, ...over,
});

it("flags a measure as overdue only while it is still open", () => {
  expect(isMyWorkOverdue(work("a", { due_on: "2026-01-01" }), "2026-11-22")).toBe(true);
  expect(isMyWorkOverdue(work("b", { due_on: "2026-01-01", applicability: "applies", implementation: "implemented" }), "2026-11-22")).toBe(false);
  expect(isMyWorkOverdue(work("c", { due_on: "2026-01-01", applicability: "not_applicable", implementation: "not_implemented" }), "2026-11-22")).toBe(false);
  expect(isMyWorkOverdue(work("d", { due_on: "2099-01-01" }), "2026-11-22")).toBe(false);
  expect(isMyWorkOverdue(work("e"), "2026-11-22")).toBe(false);
});

it("lists my measures with their framework, due date, state and a link to each", async () => {
  stubApi({ "GET /api/v1/orgs/primary/my-work": [200, [
    work("op.acc.1", { due_on: "2026-01-15" }),
    work("op.exp.2", { applicability: "applies", implementation: "partially_implemented" }),
  ]] });
  renderWithProviders(<MyWorkView org={org} />);
  const rows = within(await screen.findByRole("table")).getAllByRole("row").slice(1);
  expect(within(rows[0]!).getByText("Vencida")).toBeTruthy();
  expect(within(rows[0]!).getByText("Sin evaluar")).toBeTruthy();
  expect(within(rows[0]!).getByRole("link", { name: "Abrir op.acc.1" }).getAttribute("href"))
    .toBe("/app/framework?org=primary&framework=synthetic_alpha#req-op.acc.1");
  expect(within(rows[1]!).getByText("Sin fecha")).toBeTruthy();
  expect(within(rows[1]!).getByText("Implantada en parte")).toBeTruthy();
});

it("says what to do when nothing is assigned", async () => {
  stubApi({ "GET /api/v1/orgs/primary/my-work": [200, []] });
  renderWithProviders(<MyWorkView org={org} />);
  expect(await screen.findByText(/No tienes medidas asignadas/)).toBeTruthy();
});

const item: Register["items"][number] = {
  code: "a.1", title_es: "a.1", title_en: null, selection_basis: null,
  proposal: { decision: "undecided", rule: null, level: null }, assessment: null,
  assignment: { owner_user_id: "u-ana", due_on: null, assigned_at: "2026-11-20T10:00:00Z" },
};

it.each([[true, 1], [false, 0]] as const)("a contributor sees the assess button only on a measure they own (%s)", (owns, buttons) => {
  stubApi({});
  renderWithProviders(<AssessmentForm item={item} orgId="primary" frameworkKey="synthetic_alpha" canEdit={false} canAssess={owns} />);
  expect(screen.queryAllByRole("button", { name: "Evaluar esta medida" })).toHaveLength(buttons);
});

it("does not ask an auditor's browser for the people list", () => {
  const requests = stubApi({});
  const register = { items: [item] } as Register;
  renderWithProviders(<OwnerInsights orgId="primary" register={register} showPeople={false} />);
  expect(requests.some((r) => r.url.includes("/members"))).toBe(false);
  expect(screen.queryByText("Medidas abiertas por responsable")).toBeNull();
});

it("keys owner bars by person, so two former members never collide", async () => {
  stubApi({ "GET /api/v1/orgs/primary/members": [200, []] });
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  const owned = (code: string, owner: string) => ({ ...item, code, assignment: { owner_user_id: owner, due_on: null, assigned_at: "2026-11-20T10:00:00Z" } });
  renderWithProviders(<OwnerInsights orgId="primary" register={{ items: [owned("a", "u-1"), owned("b", "u-2")] } as Register} />);
  expect(await screen.findAllByText("Antiguo miembro")).toHaveLength(2);
  expect(errors.mock.calls.some((call) => String(call[0]).includes("same key"))).toBe(false);
  errors.mockRestore();
});
