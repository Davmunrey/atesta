// @vitest-environment jsdom
/** Assistant surfaces (assistant spec): launcher, cited cards, no answer, guided flows. */
import { join } from "node:path";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildIndex } from "../../scripts/assistant-index";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { AssistantPanel } from "@/components/assistant/panel";
import { categoryFor } from "@/lib/assistant/flows";
import faq from "@/content/assistant-faq.json";
import { legalEntity } from "@/content/legal-entity";
import { renderWithProviders } from "./render";

const index = buildIndex(join(import.meta.dirname, "../../../../catalog"), faq);
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(JSON.stringify(index), { headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const panel = (props: Partial<Parameters<typeof AssistantPanel>[0]> = {}, locale: "es" | "en" = "es") =>
  renderWithProviders(<AssistantPanel surface="landing" focusTick={0} {...props} />, locale);

async function ask(query: string) {
  const field = await screen.findByRole("searchbox", { name: /busca en el catálogo|search the catalog/i });
  fireEvent.change(field, { target: { value: query } });
  fireEvent.submit(field.closest("form") as HTMLFormElement);
}
const cards = () => screen.queryAllByRole("article");

describe("launcher", () => {
  it("is a button that opens a named non-modal dialog, and loads nothing until opened", () => {
    renderWithProviders(<AssistantLauncher surface="landing" />);
    const button = screen.getByRole("button", { name: "Asistente" });
    const dialog = document.getElementById(button.getAttribute("popovertarget") ?? "");
    expect(dialog?.tagName).toBe("DIALOG");
    expect(dialog?.getAttribute("popover")).toBe("auto");
    expect(dialog?.getAttribute("aria-labelledby")).toBeTruthy();
    expect(within(dialog as HTMLElement).getByRole("button", { name: "Cerrar", hidden: true }).getAttribute("popovertargetaction")).toBe("hide");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("mounts the panel and fetches the index on first open", async () => {
    renderWithProviders(<AssistantLauncher surface="landing" />);
    const dialog = document.querySelector("dialog") as HTMLDialogElement;
    fireEvent(dialog, Object.assign(new Event("toggle"), { newState: "open" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/assistant/index.json", expect.anything()));
  });
});

describe("search", () => {
  it("answers op.acc.6 with cited cards and announces the count", async () => {
    panel();
    await ask("op.acc.6");
    expect((await screen.findByRole("status"))?.textContent).toMatch("2 respuestas");
    expect((cards()[0])?.textContent).toMatch("op.acc.6");
    expect(within(cards()[0] as HTMLElement).getByRole("link", { name: /texto oficial/i }).getAttribute("href")).toMatch(/^https:\/\/www\.boe\.es\//);
  });

  it.each(["op.acc.6", "copias de seguridad", "plazo NIS2 24 horas", "categoría MEDIA", "¿Qué cubre Atesta?", "perfil esencial 890C"])("every card for %s carries a citation", async (query) => {
    panel();
    await ask(query);
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    for (const card of cards()) {
      const cite = card.querySelector("footer");
      expect(cite?.textContent?.trim(), card.textContent ?? "").toMatch(/Fuente: .{6,}/);
    }
  });

  it("says plainly when there is no answer and offers the contact address", async () => {
    panel();
    await ask("receta de paella valenciana");
    expect((await screen.findByRole("status"))?.textContent).toMatch("Sin respuesta en el catálogo");
    expect(cards()).toHaveLength(0);
    expect(screen.getByRole("link", { name: legalEntity.email }).getAttribute("href")).toBe(`mailto:${legalEntity.email}`);
  });

  it("marks Spanish-only official text as Spanish in the English interface", async () => {
    panel({}, "en");
    await ask("op.acc.6");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(cards()[0]?.querySelector("blockquote")?.getAttribute("lang")).toBe("es");
  });

  it("links a requirement to the organization's framework page in the app, never on the landing", async () => {
    panel({ surface: "app", orgId: "org-1" });
    await ask("op.acc.6");
    const link = await screen.findAllByRole("link", { name: "Ver en tu organización" });
    expect(link[0]?.getAttribute("href")).toBe("/app/framework?org=org-1&framework=ens_rd311_2022#req-op.acc.6");
    cleanup();
    panel();
    await ask("op.acc.6");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(screen.queryByRole("link", { name: "Ver en tu organización" })).toBeNull();
  });

  it("offers a retry when the index cannot load", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 503 }));
    panel();
    fireEvent.click(await screen.findByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("searchbox")).toBeTruthy();
  });
});

describe("guided flows", () => {
  const open = async (name: RegExp) => fireEvent.click(await screen.findByRole("button", { name }));

  it("category: the highest level picked sets the category, per CCN-STIC 803", async () => {
    panel();
    await open(/qué categoría ens tengo/i);
    const groups = await screen.findAllByRole("radiogroup");
    expect(groups).toHaveLength(5);
    expect(screen.getAllByText(/CCN-STIC 803 \(2025-06\), apartado 3\.\d, pág\. 9/).length).toBe(5);
    for (const group of groups) fireEvent.click(within(group).getByLabelText("BAJO"));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Categoría orientativa: BÁSICA"));
    expect(screen.getAllByText("Categoría orientativa: BÁSICA")).toHaveLength(2); // the result and the announcement
    fireEvent.click(within(groups[4] as HTMLElement).getByLabelText("MEDIO"));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Categoría orientativa: MEDIA"));
    expect(screen.getByText(/apartado 4\.1, pág\. 12/)).toBeTruthy();
  });

  it("evidence: a measure's signed 808 items, each cited", async () => {
    panel();
    await open(/qué evidencias pide/i);
    fireEvent.change(await screen.findByLabelText("Medida"), { target: { value: "op.acc.6" } });
    const card = await screen.findByRole("article");
    expect(within(card).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect((card.querySelector("footer"))?.textContent).toMatch(/CCN-STIC 808 \(2026-04\)/);
  });

  it("profile: does not fit unless every dimension is low; otherwise the profile for the scope", async () => {
    panel();
    await open(/perfil esencial/i);
    fireEvent.click(await screen.findByLabelText("No"));
    expect(await screen.findByText(/CCN-STIC 890C \(2026-11\), apartado 2, pág\. 4/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Sí"));
    fireEvent.click(await screen.findByLabelText(/solo tecnologías de la información/i));
    const card = await screen.findByRole("article");
    expect((card)?.textContent).toMatch(index.flows.profiles?.profiles[0]?.title.es ?? "missing");
    expect((card.querySelector("footer"))?.textContent).toMatch(/CCN-STIC 890C/);
  });

  it("clocks: NIS2 deadlines with the official text they come from", async () => {
    panel();
    await open(/qué plazos tengo/i);
    fireEvent.click(await screen.findByLabelText(/incidente significativo/i));
    expect(await screen.findByText("24 horas")).toBeTruthy();
    expect(screen.getByText("72 horas")).toBeTruthy();
    expect(screen.getByText("1 mes")).toBeTruthy();
    expect(cards().some((card) => card.querySelector("footer")?.textContent?.includes("art23.4a"))).toBe(true);
  });

  it("FAQ: every entry, marked pending review until the owner signs", async () => {
    panel();
    await open(/qué cubre atesta/i);
    await waitFor(() => expect(cards()).toHaveLength(faq.entries.length));
    for (const card of cards()) expect((card)?.textContent).toMatch("Pendiente de revisión");
  });

  it("a back button returns to the search", async () => {
    panel();
    await open(/qué cubre atesta/i);
    fireEvent.click(await screen.findByRole("button", { name: "Volver" }));
    expect(await screen.findByRole("searchbox")).toBeTruthy();
  });
});

describe("categoryFor", () => {
  const flow = index.flows.valuation!;
  it("follows the highest level, and waits for every answer", () => {
    expect(categoryFor(flow, { C: "BAJO", I: "BAJO", T: "BAJO", A: "BAJO", D: "BAJO" })).toBe("BÁSICA");
    expect(categoryFor(flow, { C: "BAJO", I: "ALTO", T: "BAJO", A: "MEDIO", D: "BAJO" })).toBe("ALTA");
    expect(categoryFor(flow, { C: "BAJO" })).toBeNull();
  });
});
