// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FrameworkDetailView } from "@/components/framework-detail";
import type { Role } from "@/lib/permissions";
import { passingReview, withManualControl } from "../fixtures/framework";
import { renderWithProviders, stubApi } from "./render";

const detailPath = "GET /api/v1/orgs/primary/frameworks/synthetic_alpha";
const reviewsPath = "POST /api/v1/orgs/primary/controls/ctl.paper/reviews";
const membersPath = "GET /api/v1/orgs/primary/members";
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
    [reviewsPath]: [201, review],
  });
  render("admin");
  const card = await paperCard();
  fireEvent.click(within(card).getByRole("button", { name: "Registrar revisión" }));
  fireEvent.click(within(card).getByRole("radio", { name: "Implantado" }));
  fireEvent.change(within(card).getByLabelText(/Justificación/), { target: { value: "  Acta 12 aprobada.  " } });
  fireEvent.change(within(card).getByLabelText(/Válida hasta/), { target: { value: "2027-10-01" } });
  fireEvent.click(within(card).getByRole("button", { name: "Guardar revisión" }));
  expect(await within(await paperCard()).findByRole("status")).toBeTruthy();
  const post = requests.find((r) => r.method === "POST")!;
  expect(await post.json()).toEqual({ status: "pass", rationale: "Acta 12 aprobada.", valid_until: "2027-10-01" });
  expect(requests.filter((r) => r.method === "GET" && new URL(r.url).pathname.endsWith("/frameworks/synthetic_alpha"))).toHaveLength(2);
});

it("shows the API's reason when a review is refused", async () => {
  stubApi({
    [detailPath]: [200, withPaper(null)],
    [membersPath]: [200, members],
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
