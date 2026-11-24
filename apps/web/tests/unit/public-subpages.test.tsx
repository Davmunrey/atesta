// @vitest-environment jsdom
/** Existing subpages in the public style (landing-legal amendment A3, issue 384). */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import NotFound from "@/app/not-found";
import InvitePage from "@/app/(public)/invite/page";
import TrainingPage from "@/app/(public)/training/page";
import UnsubscribePage from "@/app/(public)/unsubscribe/page";
import { McpGuide } from "@/components/mcp-guide";
import { renderWithProviders } from "./render";

vi.mock("next/navigation", () => ({ usePathname: () => "/x", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it.each([["/invite", InvitePage], ["/training", TrainingPage], ["/unsubscribe", UnsubscribePage]])("%s shows its message in a centred card with the seal", (_, Page) => {
  renderWithProviders(<Page />);
  const card = document.querySelector("main#content .public-card");
  expect(card).toBeTruthy();
  expect(card?.querySelector("svg.brand-seal")).toBeTruthy();
});

it("the 404 explains, links home, to Producto and to ENS, and opens the assistant from the card", () => {
  renderWithProviders(<NotFound />);
  const card = document.querySelector("main#content .public-card") as HTMLElement;
  expect(within(card).getByRole("heading", { level: 1, name: "Esta página no existe." })).toBeTruthy();
  expect(within(card).getAllByRole("paragraph").length).toBeGreaterThan(0);
  const hrefs = within(card).getAllByRole("link").map((a) => a.getAttribute("href"));
  expect(hrefs).toEqual(expect.arrayContaining(["/", "/producto", "/ens"]));
  const ask = within(card).getByRole("button", { name: "Pregunta al asistente" });
  const dialog = document.getElementById(ask.getAttribute("popovertarget") ?? "");
  expect(dialog?.tagName).toBe("DIALOG");
});

it("the MCP configuration has a visible copy button that announces success and never disables itself", async () => {
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  renderWithProviders(<McpGuide />);
  const button = screen.getByRole("button", { name: "Copiar configuración" });
  const config = (document.querySelector("textarea.code-example") as HTMLTextAreaElement).value;
  await act(async () => { fireEvent.click(button); });
  expect(writeText).toHaveBeenCalledWith(config);
  const status = document.querySelector(".copy-status");
  expect(status?.getAttribute("role")).toBe("status");
  expect(status?.textContent).toBe("Copiado");
  expect(button.hasAttribute("disabled")).toBe(false);
});

it("says when the copy fails", async () => {
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: vi.fn(async () => { throw new Error("denied"); }) } });
  renderWithProviders(<McpGuide />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Copiar configuración" })); });
  expect(document.querySelector(".copy-status")?.textContent).toBe("No se pudo copiar");
});

it("draws the page index as a compact list, never as underlined utility links", () => {
  for (const file of ["src/components/api-reference.tsx", "src/components/mcp-guide.tsx", "src/components/legal-draft.tsx", "src/app/(public)/cookies/page.tsx"]) {
    const source = readFileSync(join(import.meta.dirname, "../..", file), "utf8");
    const nav = source.slice(source.indexOf("policy-index"), source.indexOf("</nav>", source.indexOf("policy-index")));
    expect(nav, file).not.toMatch(/className="underline"/);
  }
});
