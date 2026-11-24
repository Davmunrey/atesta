// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ControlEvidence } from "@/components/control-evidence";
import { renderWithProviders, stubApi } from "./render";

const list = "GET /api/v1/orgs/primary/controls/ctl.paper/evidence";
const files = "POST /api/v1/orgs/primary/controls/ctl.paper/evidence/files";
const members = { "GET /api/v1/orgs/primary/members": [200, []] as [number, unknown] };
const uploads = { enabled: true, max_bytes: 25 * 1024 * 1024, extensions: ["csv", "docx", "jpeg", "jpg", "pdf", "png", "txt", "xlsx"] };
const page = (items: unknown[] = [], enabled = true) => ({ total: items.length, items, file_uploads: { ...uploads, enabled } });
const stored = {
  id: "11111111-1111-4111-8111-111111111111", kind: "document", title: "Política de acceso", statement: null, reference_url: null,
  created_by: null, created_at: "2026-11-24T09:00:00Z", collected_at: "2026-11-24T09:00:00Z",
  file: { name: "politica.pdf", media_type: "application/pdf", size_bytes: 345_678, sha256: "a".repeat(64), scan_status: "no_threats_found" },
};
const scanned = (scan_status: string) => ({ ...stored, file: { ...stored.file, scan_status } });
const download = `GET /api/v1/orgs/primary/evidence/${stored.id}/file`;
const pdf = (name = "Política de acceso v2.pdf", size = 12) => new File([new Uint8Array(size)], name, { type: "application/pdf" });

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const render = () => renderWithProviders(<ControlEvidence orgId="primary" controlKey="ctl.paper" />);
const open = () => fireEvent.click(screen.getByRole("button", { name: "Ver evidencias" }));
const choose = (file: File) => fireEvent.change(screen.getByLabelText("Archivo"), { target: { files: [file] } });
async function startUpload() {
  render(); open();
  fireEvent.click(await screen.findByRole("button", { name: "Subir archivo" }));
}

it("offers uploads only where the API says they work", async () => {
  stubApi({ ...members, [list]: [200, page([], false)] });
  render(); open();
  expect(await screen.findByRole("button", { name: "Registrar evidencia" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Subir archivo" })).toBeNull();
});

it("states the limits and that files are scanned for malware before a file is chosen", async () => {
  stubApi({ ...members, [list]: [200, page()] });
  await startUpload();
  expect(document.activeElement).toBe(screen.getByLabelText("Archivo"));
  expect(screen.getByText("PDF, PNG, JPG, TXT, CSV, DOCX o XLSX. Hasta 25 MB.")).toBeTruthy();
  expect(screen.getByText("Atesta analiza cada archivo en busca de malware antes de que se pueda descargar.")).toBeTruthy();
  expect(screen.queryByText(/no lo analiza/)).toBeNull();
  expect(screen.getByLabelText("Archivo").getAttribute("accept")).toBe(".csv,.docx,.jpeg,.jpg,.pdf,.png,.txt,.xlsx");
  expect((screen.getByRole("button", { name: "Subir archivo" }) as HTMLButtonElement).disabled).toBe(true);
});

it("uploads a file with a title taken from its name and refreshes the list", async () => {
  const calls = stubApi({ ...members, [list]: [[200, page()], [200, page([stored])]], [files]: [201, stored] });
  await startUpload();
  choose(pdf());
  const title = screen.getByLabelText("Nombre de la evidencia") as HTMLInputElement;
  expect(title.value).toBe("Política de acceso v2");
  fireEvent.change(title, { target: { value: "  Política de acceso  " } });
  fireEvent.click(screen.getByRole("button", { name: "Subir archivo" }));
  expect(await screen.findByText("Archivo subido. La revisión se decide por separado.")).toBeTruthy();
  const sent = await calls.find((c) => c.method === "POST")!.formData();
  expect(sent.get("title")).toBe("Política de acceso");
  expect(String(sent.get("submission_id"))).toMatch(/^[a-f0-9-]{36}$/);
  // jsdom's FormData loses the file name when Node re-parses the request; the e2e test checks it in a browser.
  expect((sent.get("file") as File).size).toBe(12);
  expect(await screen.findByText("politica.pdf")).toBeTruthy();
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Subir archivo" })));
});

it.each([
  ["a file over the limit", () => Object.defineProperty(pdf(), "size", { value: 25 * 1024 * 1024 + 1 }), "El archivo supera el límite de 25 MB. Redúcelo o divídelo antes de subirlo."],
  ["a type outside the list", () => pdf("instalador.exe"), "Ese tipo de archivo no se admite. Sube un PDF, PNG, JPG, TXT, CSV, DOCX o XLSX."],
  ["an empty file", () => pdf("vacio.pdf", 0), "El archivo está vacío. Elige un archivo con contenido."],
])("refuses %s before sending anything", async (_, file, message) => {
  const calls = stubApi({ ...members, [list]: [200, page()] });
  await startUpload();
  choose(file());
  expect(within(screen.getByRole("alert")).getByText(message)).toBeTruthy();
  expect((screen.getByRole("button", { name: "Subir archivo" }) as HTMLButtonElement).disabled).toBe(true);
  expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
});

it("shows the API's reason and keeps the same submission on a retry", async () => {
  const calls = stubApi({ ...members, [list]: [200, page()], [files]: [[503, { detail: { code: "evidence.storage_unavailable" } }], [201, stored]] });
  await startUpload();
  choose(pdf());
  fireEvent.click(screen.getByRole("button", { name: "Subir archivo" }));
  expect(within(await screen.findByRole("alert")).getByText(/Ahora mismo no se pueden guardar ni leer archivos/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Subir archivo" }));
  await screen.findByText("Archivo subido. La revisión se decide por separado.");
  const [first, second] = await Promise.all(calls.filter((c) => c.method === "POST").map((c) => c.formData()));
  expect(first!.get("submission_id")).toBe(second!.get("submission_id"));
});

it("lists an uploaded file with its name, type and size, and downloads it on request", async () => {
  const calls = stubApi({ ...members, [list]: [200, page([stored])], [download]: [200, "synthetic bytes"] });
  const created = vi.fn(() => "blob:synthetic");
  const revoked = vi.fn();
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked }));
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  render(); open();
  const item = (await screen.findByText("Política de acceso")).closest("li")!;
  expect(within(item).getByText("politica.pdf")).toBeTruthy();
  expect(within(item).getByText(/PDF · 338 kB/)).toBeTruthy();
  expect(within(item).queryByText(/no está disponible desde esta pantalla/)).toBeNull();
  fireEvent.click(within(item).getByRole("button", { name: "Descargar politica.pdf" }));
  await waitFor(() => expect(clicked).toHaveBeenCalledTimes(1));
  expect(created).toHaveBeenCalledTimes(1);
  expect(revoked).toHaveBeenCalledWith("blob:synthetic");
  expect(calls.filter((c) => new URL(c.url).pathname.endsWith("/file"))).toHaveLength(1);
});

it("shows an integrity failure as such, never as a missing file", async () => {
  stubApi({ ...members, [list]: [200, page([stored])], [download]: [409, { detail: { code: "evidence.file_integrity_failed" } }] });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  render(); open();
  const item = (await screen.findByText("Política de acceso")).closest("li")!;
  fireEvent.click(within(item).getByRole("button", { name: "Descargar politica.pdf" }));
  expect(within(await within(item).findByRole("alert")).getByText(/ya no coincide con el que se registró/)).toBeTruthy();
  expect(clicked).not.toHaveBeenCalled();
});

it("keeps scan outputs without a download", async () => {
  const scan = { ...stored, id: "scan-1", kind: "scan_output", title: "prowler.ocsf.json", file: null };
  stubApi({ ...members, [list]: [200, page([scan])] });
  render(); open();
  const item = (await screen.findByText("prowler.ocsf.json")).closest("li")!;
  expect(within(item).getByText(/no está disponible desde esta pantalla/)).toBeTruthy();
  expect(within(item).queryByRole("button")).toBeNull();
});

// evidence-malware-scanning spec (#431): each file says where its scan stands; only a file the API
// will serve offers "Descargar".
it.each([
  ["pending", "En análisis", "pending", /Podrás descargarlo cuando termine el análisis/, false],
  ["threats_found", "Bloqueado: posible malware", "overdue", /Nadie puede descargarlo\. Averigua de dónde salió/, false],
  ["unsupported", "No se pudo analizar", "missing", /sube una copia sin contraseña/, false],
  ["access_denied", "No se pudo analizar", "missing", /sube una copia sin contraseña/, false],
  ["failed", "No se pudo analizar", "missing", /sube una copia sin contraseña/, false],
  ["not_scanned", "Sin analizar (entorno de desarrollo)", "pending", null, true],
  ["no_threats_found", "Sin amenazas detectadas", "done", null, true],
] as const)("shows a %s file as %j and offers a download only when it is served", async (status, label, severity, help, served) => {
  stubApi({ ...members, [list]: [200, page([scanned(status)])] });
  render(); open();
  const item = (await screen.findByText("Política de acceso")).closest("li")!;
  const badge = within(item).getByText(label).closest(".badge")!;
  expect(badge.getAttribute("data-severity")).toBe(severity);
  expect(badge.querySelector("svg")).toBeTruthy(); // icon plus text, never colour alone
  if (help) expect(within(item).getByText(help)).toBeTruthy();
  expect(within(item).queryByRole("button", { name: "Descargar politica.pdf" }) !== null).toBe(served);
});

it("shows the API's refusal if a file is blocked after the list was loaded", async () => {
  stubApi({ ...members, [list]: [200, page([stored])], [download]: [409, { detail: { code: "evidence.file_malware_found" } }] });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  render(); open();
  const item = (await screen.findByText("Política de acceso")).closest("li")!;
  fireEvent.click(within(item).getByRole("button", { name: "Descargar politica.pdf" }));
  expect(within(await within(item).findByRole("alert")).getByText(/posible amenaza en este archivo/)).toBeTruthy();
  expect(clicked).not.toHaveBeenCalled();
});
