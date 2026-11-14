// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ControlEvidence } from "@/components/control-evidence";
import { renderWithProviders, stubApi } from "./render";

const path = "/api/v1/orgs/primary/controls/ctl.paper/evidence";
const proof = { id: "proof-1", kind: "attestation", title: "Acta sintética", statement: "<b>Texto literal</b>", reference_url: "https://example.test/policy", created_by: null, created_at: "2026-11-14T12:00:00Z", collected_at: "2026-11-14T12:00:00Z" };
const members = { "GET /api/v1/orgs/primary/members": [200, []] as [number, unknown] };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const render = () => renderWithProviders(<ControlEvidence orgId="primary" controlKey="ctl.paper" />);
const open = () => fireEvent.click(screen.getByRole("button", { name: "Ver evidencias" }));

it("loads only on demand, with an explicit empty state", async () => {
  const calls = stubApi({ ...members, [`GET ${path}`]: [200, { total: 0, items: [] }] });
  render();
  expect(calls).toHaveLength(0);
  open();
  expect(await screen.findByText("Todavía no hay evidencias para este control.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Registrar evidencia" })).toBeTruthy();
});

it("records a statement and refreshes the list without rendering HTML", async () => {
  const calls = stubApi({ ...members, [`GET ${path}`]: [[200, { total: 0, items: [] }], [200, { total: 1, items: [proof] }]], [`POST ${path}`]: [201, proof] });
  render(); open();
  fireEvent.click(await screen.findByRole("button", { name: "Registrar evidencia" }));
  fireEvent.change(screen.getByLabelText("Nombre de la evidencia"), { target: { value: "  Acta sintética  " } });
  fireEvent.change(screen.getByLabelText("Qué demuestra"), { target: { value: "  <b>Texto literal</b>  " } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar evidencia" }));
  expect(await screen.findByText("Evidencia registrada. La revisión se decide por separado.")).toBeTruthy();
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Registrar evidencia" })));
  expect(await screen.findByText("<b>Texto literal</b>")).toBeTruthy();
  const body = await calls.find((c) => c.method === "POST")!.json();
  expect(body).toMatchObject({ title: "Acta sintética", statement: "<b>Texto literal</b>", reference_url: null });
  expect(body.submission_id).toMatch(/^[a-f0-9-]{36}$/);
});

it("keeps input and the submission id when retrying an uncertain failure", async () => {
  const calls = stubApi({ ...members, [`GET ${path}`]: [200, { total: 0, items: [] }], [`POST ${path}`]: [[503, {}], [201, proof]] });
  render(); open();
  fireEvent.click(await screen.findByRole("button", { name: "Registrar evidencia" }));
  fireEvent.change(screen.getByLabelText("Nombre de la evidencia"), { target: { value: "Test" } });
  fireEvent.change(screen.getByLabelText("Qué demuestra"), { target: { value: "Synthetic only" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar evidencia" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect((screen.getByLabelText("Qué demuestra") as HTMLTextAreaElement).value).toBe("Synthetic only");
  fireEvent.click(screen.getByRole("button", { name: "Ocultar evidencias" }));
  open();
  expect((screen.getByLabelText("Qué demuestra") as HTMLTextAreaElement).value).toBe("Synthetic only");
  fireEvent.click(screen.getByRole("button", { name: "Guardar evidencia" }));
  await screen.findByText("Evidencia registrada. La revisión se decide por separado.");
  const posts = calls.filter((c) => c.method === "POST");
  expect(await posts[0]!.json()).toEqual(await posts[1]!.json());
});

it("offers a retry after a list failure", async () => {
  stubApi({ ...members, [`GET ${path}`]: [[503, {}], [200, { total: 1, items: [proof] }]] });
  render(); open();
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  await waitFor(() => expect(screen.getByText("Acta sintética")).toBeTruthy());
});

it("moves focus into the form and restores it on cancel", async () => {
  stubApi({ ...members, [`GET ${path}`]: [200, { total: 0, items: [] }] });
  render(); open();
  fireEvent.click(await screen.findByRole("button", { name: "Registrar evidencia" }));
  expect(document.activeElement).toBe(screen.getByLabelText("Nombre de la evidencia"));
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Registrar evidencia" })));
});

it("moves focus to the result region after changing pages", async () => {
  const calls = stubApi({ ...members, [`GET ${path}`]: [[200, { total: 21, items: [proof] }], [200, { total: 21, items: [{ ...proof, id: "second", title: "Segunda página" }] }]] });
  render(); open();
  fireEvent.click(await screen.findByRole("button", { name: "Siguiente" }));
  await screen.findByText("Segunda página");
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("region", { name: "Páginas de evidencias" })));
  expect(calls.some((r) => new URL(r.url).searchParams.get("offset") === "20")).toBe(true);
});
