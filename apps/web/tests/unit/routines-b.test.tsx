// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { IncidentView } from "@/components/incident-view";
import { IncidentsView } from "@/components/incidents-view";
import { useAttention } from "@/components/readiness";
import { captureTrainingToken, TrainingConfirm } from "@/components/training-confirm";
import { TrainingView } from "@/components/training-view";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.history.replaceState(null, "", "/"); window.sessionStorage.clear(); });
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const auditor = { ...owner, role: "auditor" as const, access_expires_on: "2027-01-01" };
const base = "/api/v1/orgs/primary";
const TOKEN = "t".repeat(43);

async function posted(requests: Request[], path: string) {
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "POST" && r.url.endsWith(path))) throw new Error(`no POST ${path}`); });
  return requests.find((r) => r.method === "POST" && r.url.endsWith(path))!.clone().json();
}

it("takes the token from the fragment, clears it, and confirms with name and email", async () => {
  window.history.replaceState(null, "", `/training#token=${TOKEN}`);
  const requests = stubApi({
    "POST /api/v1/training/link": [200, { title: "Phishing 2026", material_url: "https://example.com/m.pdf", closes_on: "2026-12-31" }],
    "POST /api/v1/training/acknowledge": [200, { recorded: true }],
  });
  renderWithProviders(<TrainingConfirm />);
  expect(await screen.findByRole("heading", { name: "Phishing 2026" })).toBeTruthy();
  expect(window.location.hash).toBe("");
  expect(captureTrainingToken()).toBe(TOKEN); // a second effect run, or a reload, still finds it
  expect(await posted(requests, "/training/link")).toEqual({ token: TOKEN });
  expect(requests.every((r) => !new URL(r.url).search)).toBe(true);
  fireEvent.change(screen.getByLabelText("Nombre y apellidos"), { target: { value: "Ana Pérez" } });
  fireEvent.change(screen.getByLabelText("Correo electrónico"), { target: { value: "ana@example.com" } });
  fireEvent.click(screen.getByLabelText("He leído el material"));
  fireEvent.submit(screen.getByRole("form", { name: "Confirmar la lectura" }));
  expect(await posted(requests, "/training/acknowledge")).toEqual({ token: TOKEN, full_name: "Ana Pérez", email: "ana@example.com" });
  expect(await screen.findByText("Gracias. Tu confirmación ha quedado registrada.")).toBeTruthy();
});

it("explains a missing or closed training link", async () => {
  renderWithProviders(<TrainingConfirm />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Falta el enlace de la formación. Ábrelo tal como te lo enviaron.");
  cleanup();
  window.history.replaceState(null, "", `/training#token=${TOKEN}`);
  stubApi({ "POST /api/v1/training/link": [410, { detail: { code: "compliance.training_closed" } }] });
  renderWithProviders(<TrainingConfirm />, "en");
  expect(await screen.findByText("This training is closed and takes no more confirmations.")).toBeTruthy();
});

it("shows a new training link once, for copying", async () => {
  const link = `https://app.example.com/training#token=${TOKEN}`;
  const requests = stubApi({
    [`GET ${base}/training-campaigns`]: [200, []],
    [`POST ${base}/training-campaigns`]: [201, { id: "c1", title: "Phishing", material_url: "https://example.com/m", closes_on: "2026-12-31", created_at: "2026-11-23T10:00:00Z", closed_at: null, acknowledged: 0, link }],
  });
  renderWithProviders(<TrainingView org={owner} />);
  fireEvent.change(await screen.findByLabelText("Nombre de la formación"), { target: { value: "Phishing" } });
  fireEvent.change(screen.getByLabelText("Enlace al material (https)"), { target: { value: "https://example.com/m" } });
  fireEvent.change(screen.getByLabelText("Fecha de cierre"), { target: { value: "2026-12-31" } });
  fireEvent.click(screen.getByRole("button", { name: "Crear y obtener el enlace" }));
  expect(await posted(requests, "/training-campaigns")).toEqual({ title: "Phishing", material_url: "https://example.com/m", closes_on: "2026-12-31" });
  expect(await screen.findByDisplayValue(link)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Copiar el enlace" })).toBeTruthy();
});

const clock = (over: object) => ({
  ref: "nis2:early_warning", framework_key: "nis2", framework_name: "NIS2", requirement: "art23.4a",
  title_es: "Alerta temprana", title_en: "Early warning", state: "overdue", due_at: "2026-11-21T09:30:00Z", met_at: null, late: false, ...over,
});
const incident = {
  id: "i1", title: "Ransomware", aware_at: "2026-11-20T09:30:00Z", significant: true, personal_data: false,
  created_at: "2026-11-20T10:00:00Z", closed_at: null, next_due_at: "2026-11-21T09:30:00Z", overdue: 1,
  clocks: [
    clock({}),
    clock({ ref: "nis2:notification", requirement: "art23.4b", title_es: "Notificación del incidente", title_en: "Incident notification", state: "met", met_at: "2026-11-22T08:00:00Z", due_at: "2026-11-23T09:30:00Z" }),
    clock({ ref: "nis2:final_report", requirement: "art23.4d", title_es: "Informe final", title_en: "Final report", state: "waiting", due_at: null }),
  ],
  updates: [{ kind: "clock", clock: "nis2:notification", note: "", recorded_at: "2026-11-22T08:00:00Z" }],
};

it("shows each reporting deadline from pack content and marks one as sent", async () => {
  const requests = stubApi({ [`GET ${base}/incidents/i1`]: [200, incident], [`POST ${base}/incidents/i1/updates`]: [201, incident] });
  renderWithProviders(<IncidentView org={owner} incidentId="i1" />);
  expect(await screen.findByText("Vencido")).toBeTruthy();
  expect(screen.getByText("Enviado el 22 nov 2026, 8:00")).toBeTruthy();
  expect(screen.getByText("Empieza con el aviso anterior")).toBeTruthy();
  expect(screen.getByText("Aviso enviado: Notificación del incidente")).toBeTruthy();
  expect(screen.getAllByRole("button", { name: /^Marcar/ })).toHaveLength(1);
  // WCAG 2.5.3 (ui-polish spec): the accessible name starts with the visible text.
  const send = screen.getByRole("button", { name: "Marcar como enviado: «Alerta temprana»" });
  expect(send.textContent!.startsWith("Marcar como enviado")).toBe(true);
  fireEvent.click(send);
  expect(await posted(requests, "/updates")).toEqual({ kind: "clock", clock: "nis2:early_warning", note: "" });
});

it("reads an incident in English and offers no actions to an auditor", async () => {
  stubApi({ [`GET ${base}/incidents/i1`]: [200, incident] });
  renderWithProviders(<IncidentView org={auditor} incidentId="i1" />, "en");
  expect(await screen.findByText("Early warning")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});

function Attention() {
  const items = useAttention(owner, []);
  return <ul>{items.map((i) => <li key={i.key}><a href={i.href}>{i.text}</a></li>)}</ul>;
}

it("lists running incident deadlines and unclosed trainings in Ahora, with links", async () => {
  stubApi({ [`GET ${base}/routines/due`]: [200, [
    { kind: "incident_clock", id: "i1", title: "Ransomware", due_on: "2026-11-21", due_at: "2026-11-21T09:30:00Z", overdue: true,
      clock: { es: "Alerta temprana", en: "Early warning", framework: "NIS2" } },
    { kind: "training_unclosed", id: "c1", title: "Phishing", due_on: "2026-11-20", overdue: true, due_at: null, clock: null },
  ]] });
  renderWithProviders(<Attention />);
  const clockItem = await screen.findByRole("link", { name: "Alerta temprana (NIS2) del incidente «Ransomware»: venció el 21 nov 2026, 9:30" });
  expect(clockItem.getAttribute("href")).toBe("/app/incident?org=primary&id=i1");
  const training = screen.getByRole("link", { name: "Cerrar la formación «Phishing» y registrar la evidencia (terminaba el 20 de noviembre de 2026)" });
  expect(training.getAttribute("href")).toBe("/app/training-campaign?org=primary&id=c1");
});

it("shows the official criteria behind each incident flag, in the reader's language when official", async () => {
  stubApi({
    [`GET ${base}/incidents`]: [200, []],
    [`GET ${base}/incidents/criteria`]: [200, [
      { needs: "significant", framework_key: "nis2", framework_name: "NIS2", requirement: "art23.3", title_es: "Obligaciones de notificación · apartado 3",
        title_en: "Reporting obligations · paragraph 3", text_es: "3. Un incidente se considerará significativo:\n\na) si ha causado…", text_en: "3. An incident shall be considered significant if:\n\n(a) it has caused…", source: "https://example.test/nis2" },
      { needs: "personal_data", framework_key: "lopd", framework_name: "LOPD", requirement: "art1", title_es: "Artículo 1", title_en: null,
        text_es: "Texto solo en español.", text_en: null, source: "https://example.test/lopd" },
    ]],
  });
  renderWithProviders(<IncidentsView org={owner} />, "en");
  const significant = await screen.findByText("What NIS2 says: Reporting obligations · paragraph 3");
  expect(significant.closest("details")!.textContent).toContain("(a) it has caused…");
  const spanishOnly = screen.getByText("What LOPD says: Artículo 1").closest("details")!;
  expect(spanishOnly.querySelector("[lang='es']")!.textContent).toBe("Texto solo en español.");
});

it("groups a framework's incident criteria under one disclosure, in the API's order", async () => {
  const item = (framework_key: string, framework_name: string, requirement: string) => ({
    needs: "significant", framework_key, framework_name, requirement, title_es: `Artículo ${requirement}`, title_en: null,
    text_es: `Texto ${requirement}.`, text_en: null, source: `https://example.test/${requirement}`,
  });
  stubApi({
    [`GET ${base}/incidents`]: [200, []],
    [`GET ${base}/incidents/criteria`]: [200, [
      item("dora", "DORA", "1"), item("dora", "DORA", "2"), item("nis2", "NIS2", "23"), item("dora", "DORA", "3"),
    ]],
  });
  renderWithProviders(<IncidentsView org={owner} />);
  const dora = (await screen.findByText("Qué dice DORA (3 criterios)")).closest("details")!;
  const inner = [...dora.querySelectorAll(".criteria-group > details > summary")].map((s) => s.textContent);
  expect(inner).toEqual(["Artículo 1", "Artículo 2", "Artículo 3"]);
  expect(dora.querySelectorAll("a[href^='https://example.test/']")).toHaveLength(3);
  expect(screen.getByText("Qué dice NIS2: Artículo 23")).toBeTruthy();
  const order = [...document.querySelectorAll(".criteria > details > summary")].map((s) => s.textContent);
  expect(order).toEqual(["Qué dice DORA (3 criterios)", "Qué dice NIS2: Artículo 23"]);
});
