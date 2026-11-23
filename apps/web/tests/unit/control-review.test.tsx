// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FrameworkDetailView } from "@/components/framework-detail";
import type { Role } from "@/lib/permissions";
import { paperEvidence, passingReview, withManualControl } from "../fixtures/framework";
import { renderWithProviders, stubApi } from "./render";

const detailPath = "GET /api/v1/orgs/primary/frameworks/synthetic_alpha";
const reviewsPath = "POST /api/v1/orgs/primary/controls/ctl.paper/reviews";
const membersPath = "GET /api/v1/orgs/primary/members";
const evidencePath = "GET /api/v1/orgs/primary/controls/ctl.paper/evidence";
const review = passingReview;
const withPaper = withManualControl;
const members = [{ user_id: review.reviewed_by, email: "ana@example.com", display_name: null, role: "admin" }];

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const render = (role: Role = "member") =>
  renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" role={role} />);
const paperCard = async () => (await screen.findByText("Plan de respuesta sintético")).closest("article")!;

it("shows the current review, its author and expiry to every member, without a form", async () => {
  stubApi({ [detailPath]: [200, withPaper(review)], [membersPath]: [200, members] });
  render("member");
  const card = await paperCard();
  expect(within(card).getByText("Implantado")).toBeTruthy();
  expect(await within(card).findByText(/ana@example\.com/)).toBeTruthy();
  expect(within(card).getByText(/1 oct 2027/)).toBeTruthy();
  expect(within(card).getByText(/Punto 3 aprobado/)).toBeTruthy();
  expect(within(card).queryByRole("button", { name: /revisión/i })).toBeNull();
});

it("flags an expired review and says no review exists yet", async () => {
  stubApi({ [detailPath]: [200, withPaper({ ...review, expired: true })], [membersPath]: [200, members] });
  render();
  expect(within(await paperCard()).getByText("Revisión caducada")).toBeTruthy();
  cleanup();
  stubApi({ [detailPath]: [200, withPaper(null)], [membersPath]: [200, members] });
  render();
  expect(within(await paperCard()).getByText(/Sin revisión registrada/)).toBeTruthy();
});

it("lets an admin record a review and refreshes the register", async () => {
  const requests = stubApi({
    [detailPath]: [[200, withPaper(null)], [200, withPaper(review)]],
    [membersPath]: [200, members],
    [evidencePath]: [200, paperEvidence],
    [reviewsPath]: [201, review],
  });
  render("admin");
  const card = await paperCard();
  fireEvent.click(within(card).getByRole("button", { name: "Registrar revisión" }));
  fireEvent.click(await within(card).findByRole("checkbox", { name: /Acta del comité 12/ }));
  fireEvent.click(within(card).getByRole("radio", { name: "Implantado" }));
  fireEvent.change(within(card).getByLabelText(/Justificación/), { target: { value: "  Acta 12 aprobada.  " } });
  fireEvent.change(within(card).getByLabelText(/Válida hasta/), { target: { value: "2027-10-01" } });
  fireEvent.click(within(card).getByRole("button", { name: "Guardar revisión" }));
  expect(await within(await paperCard()).findByRole("status")).toBeTruthy();
  const post = requests.find((r) => r.method === "POST")!;
  expect(await post.json()).toEqual({
    status: "pass", rationale: "Acta 12 aprobada.", valid_until: "2027-10-01", evidence_ids: [paperEvidence.items[0]!.id],
  });
  expect(requests.filter((r) => r.method === "GET" && new URL(r.url).pathname.endsWith("/frameworks/synthetic_alpha"))).toHaveLength(2);
});

it("shows the API's reason when a review is refused", async () => {
  stubApi({
    [detailPath]: [200, withPaper(null)],
    [membersPath]: [200, members],
    [evidencePath]: [200, { items: [], total: 0 }],
    [reviewsPath]: [409, { detail: { code: "compliance.control_not_manual" } }],
  });
  render("owner");
  const card = await paperCard();
  fireEvent.click(within(card).getByRole("button", { name: "Registrar revisión" }));
  fireEvent.click(within(card).getByRole("radio", { name: "No implantado" }));
  fireEvent.change(within(card).getByLabelText(/Justificación/), { target: { value: "Sin plan aprobado." } });
  fireEvent.click(within(card).getByRole("button", { name: "Guardar revisión" }));
  expect(await within(card).findByRole("alert")).toBeTruthy();
  expect(within(card).getByText(/comprobaciones automáticas/)).toBeTruthy();
});

it("never offers a review on an automated control", async () => {
  stubApi({ [detailPath]: [200, withPaper(null)], [membersPath]: [200, members] });
  render("owner");
  const automated = (await screen.findByText("Verificar acceso de prueba")).closest("article")!;
  expect(within(automated).queryByRole("button", { name: "Registrar revisión" })).toBeNull();
});

it("lists the evidence a review cites, or says it cites none", async () => {
  stubApi({ [detailPath]: [200, withPaper(review)], [membersPath]: [200, members] });
  render("member");
  const cited = within(await paperCard()).getByRole("list", { name: "Evidencias citadas" });
  expect(within(cited).getByText("Acta del comité 12")).toBeTruthy();
  cleanup();
  stubApi({ [detailPath]: [200, withPaper({ ...review, evidence: [] })], [membersPath]: [200, members] });
  render("member");
  expect(within(await paperCard()).getByText("No cita ninguna evidencia.")).toBeTruthy();
});

it("will not save a pass that cites no evidence", async () => {
  const requests = stubApi({ [detailPath]: [200, withPaper(null)], [membersPath]: [200, members], [evidencePath]: [200, paperEvidence] });
  render("admin");
  const card = await paperCard();
  fireEvent.click(within(card).getByRole("button", { name: "Registrar revisión" }));
  await within(card).findByRole("checkbox", { name: /Acta del comité 12/ });
  fireEvent.click(within(card).getByRole("radio", { name: "Implantado" }));
  fireEvent.change(within(card).getByLabelText(/Justificación/), { target: { value: "Acta 12." } });
  fireEvent.click(within(card).getByRole("button", { name: "Guardar revisión" }));
  const error = await within(card).findByRole("alert");
  expect(error.textContent).toBe("Marca al menos una evidencia para registrarlo como implantado.");
  expect(error.querySelector("svg")).toBeTruthy();  // icon and text, never colour alone
  const evidence = error.closest("fieldset")!;
  const first = within(evidence).getByRole("checkbox", { name: /Acta del comité 12/ }) as HTMLInputElement;
  expect(first.validationMessage).toBe("Marca al menos una evidencia para registrarlo como implantado.");
  expect(first.getAttribute("aria-invalid")).toBe("true");
  expect(requests.filter((r) => r.method === "POST")).toHaveLength(0);
  fireEvent.click(first);
  expect(first.validationMessage).toBe("");
});

it("ties the decision to the evidence help that explains a disabled pass (issue 321)", async () => {
  stubApi({ [detailPath]: [200, withPaper(null)], [membersPath]: [200, members], [evidencePath]: [200, { items: [], total: 0 }] });
  render("admin");
  const card = await paperCard();
  fireEvent.click(within(card).getByRole("button", { name: "Registrar revisión" }));
  const help = await within(card).findByText(/Registra primero una evidencia/);
  const decision = within(card).getByRole("group", { name: "Decisión" });
  expect(decision.getAttribute("aria-describedby")).toBe(help.id);
});

it("lets the reviewer page to older evidence and keeps what was cited (issue 321)", async () => {
  const item = (n: number) => ({ ...paperEvidence.items[0]!, id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`, title: `Acta ${n}` });
  const newest = { items: Array.from({ length: 20 }, (_, i) => item(i + 1)), total: 21 };
  const older = { items: [item(21)], total: 21 };
  const requests = stubApi({ [detailPath]: [200, withPaper(null)], [membersPath]: [200, members], [evidencePath]: [[200, newest], [200, older]], [reviewsPath]: [201, review] });
  render("admin");
  const card = await paperCard();
  fireEvent.click(within(card).getByRole("button", { name: "Registrar revisión" }));
  fireEvent.click(await within(card).findByRole("checkbox", { name: /Acta 2 ·/ }));
  fireEvent.click(within(card).getByRole("button", { name: "Anteriores" }));
  fireEvent.click(await within(card).findByRole("checkbox", { name: /Acta 21/ }));
  expect(within(card).getByText(/Evidencias 21–21 de 21\. 2 citadas\./)).toBeTruthy();
  fireEvent.click(within(card).getByRole("radio", { name: "Implantado" }));
  fireEvent.change(within(card).getByLabelText(/Justificación/), { target: { value: "Actas 2 y 21." } });
  fireEvent.click(within(card).getByRole("button", { name: "Guardar revisión" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
  expect((await requests.find((r) => r.method === "POST")!.json()).evidence_ids).toEqual([item(2).id, item(21).id]);
  expect(new URL(requests.filter((r) => r.url.includes("/evidence"))[1]!.url).searchParams.get("offset")).toBe("20");
});

it("offers only a fail when the control has no evidence yet", async () => {
  stubApi({ [detailPath]: [200, withPaper(null)], [membersPath]: [200, members], [evidencePath]: [200, { items: [], total: 0 }] });
  render("admin");
  const card = await paperCard();
  fireEvent.click(within(card).getByRole("button", { name: "Registrar revisión" }));
  expect(await within(card).findByText(/Registra primero una evidencia/)).toBeTruthy();
  expect((within(card).getByRole("radio", { name: "Implantado" }) as HTMLInputElement).disabled).toBe(true);
  expect((within(card).getByRole("radio", { name: "No implantado" }) as HTMLInputElement).disabled).toBe(false);
});
