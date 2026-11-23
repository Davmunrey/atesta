// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AccessReviewView } from "@/components/access-review-view";
import { PoliciesView } from "@/components/policies-view";
import { parseAccounts } from "@/lib/api/routines";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const base = "/api/v1/orgs/primary";

it("reads accounts from pasted lines or a CSV, skipping a header, blanks and duplicates", () => {
  expect(parseAccounts("cuenta,detalle\nana@example.com, Global admin\n\nluis@example.com\nANA@example.com\n\"marta@example.com\";Lectora"))
    .toEqual([
      { account: "ana@example.com", detail: "Global admin" },
      { account: "luis@example.com", detail: "" },
      { account: "marta@example.com", detail: "Lectora" },
    ]);
});

const review = (decisions: (null | "keep" | "revoke")[], closed = false) => ({
  id: "r1", title: "Q4", system: "Microsoft 365", due_on: null, created_at: "2026-11-23T10:00:00Z", closed_at: closed ? "2026-11-23T12:00:00Z" : null,
  total: decisions.length, keep: decisions.filter((d) => d === "keep").length, revoke: decisions.filter((d) => d === "revoke").length,
  pending: decisions.filter((d) => d === null).length,
  entries: decisions.map((d, i) => ({ id: `e${i}`, account: `user${i}@example.com`, detail: "", decision: d, note: "", decided_at: null })),
});

it("decides account by account and closes only when every account is decided", async () => {
  const requests = stubApi({
    [`GET ${base}/access-reviews/r1`]: [[200, review([null, "keep"])], [200, review(["revoke", "keep"])]],
    [`POST ${base}/access-reviews/r1/decisions`]: [201, { id: "e0", account: "user0@example.com", detail: "", decision: "revoke", note: "", decided_at: null }],
    [`POST ${base}/access-reviews/r1/close`]: [200, review(["revoke", "keep"], true)],
  });
  renderWithProviders(<AccessReviewView org={owner} reviewId="r1" />);
  const close = await screen.findByRole("button", { name: "Cerrar y registrar" }) as HTMLButtonElement;
  expect(close.disabled).toBe(true);
  expect(screen.getAllByText("Falta 1 cuenta por decidir").length).toBeGreaterThan(0);
  fireEvent.click(within(screen.getByRole("group", { name: "Decisión para user0@example.com" })).getByRole("button", { name: "Retirar" }));
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "POST" && r.url.endsWith("/decisions"))) throw new Error("no decision"); });
  const post = requests.find((r) => r.method === "POST" && r.url.endsWith("/decisions"))!;
  expect(await post.json()).toEqual({ entry_id: "e0", decision: "revoke", note: "" });
});

it("shows a policy's approval state and computes no hash unless a file is chosen", async () => {
  stubApi({ [`GET ${base}/policies`]: [200, [
    { id: "p1", title: "Política de seguridad", location_url: "https://example.com/p.pdf", review_months: 12, created_at: "2026-01-01T00:00:00Z",
      latest: { version: "1.0", approver_name: "Comité", approved_on: "2025-01-10", sha256: "a".repeat(64), recorded_at: "2025-01-10T00:00:00Z" }, next_review_on: "2026-01-10" },
    { id: "p2", title: "Política de copias", location_url: "https://example.com/c.pdf", review_months: 12, created_at: "2026-01-01T00:00:00Z", latest: null, next_review_on: null },
  ]] });
  renderWithProviders(<PoliciesView org={owner} />);
  expect(await screen.findByText(/Revisión vencida el 10 ene 2026/)).toBeTruthy();
  expect(screen.getByText("Sin aprobar")).toBeTruthy();
  expect(screen.getByText(/Versión 1.0, aprobada por Comité/)).toBeTruthy();
  fireEvent.click(screen.getAllByRole("button", { name: "Registrar aprobación" })[0]!);
  expect(screen.getByText("Se calcula su huella SHA-256 en tu navegador; el documento no se sube.")).toBeTruthy();
});
