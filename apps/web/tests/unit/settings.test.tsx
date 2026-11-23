// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SettingsView } from "@/components/settings-view";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const org = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };

it("is for owners only", () => {
  stubApi({});
  renderWithProviders(<SettingsView org={{ ...org, role: "admin" }} />);
  expect(screen.getByText(/Solo la persona propietaria/)).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Descargar exportación" })).toBeNull();
});

it("links the export download", () => {
  stubApi({});
  renderWithProviders(<SettingsView org={org} />);
  expect(screen.getByRole("link", { name: "Descargar exportación" }).getAttribute("href")).toBe("/api/v1/orgs/primary/export");
});

it("asks for the exact name before requesting closure", async () => {
  const requests = stubApi({ "POST /api/v1/orgs/primary/closure": [202, { requested_at: "2026-11-23T10:00:00Z", erase_after: "2026-12-23T10:00:00Z" }] });
  renderWithProviders(<SettingsView org={org} />);
  const close = screen.getByRole("button", { name: "Cerrar la organización" }) as HTMLButtonElement;
  const input = screen.getByLabelText("Escribe «Synthetic Team» para confirmar");
  fireEvent.change(input, { target: { value: "synthetic team" } });
  expect(close.disabled).toBe(true);
  fireEvent.change(input, { target: { value: "Synthetic Team" } });
  expect(close.disabled).toBe(false);
  fireEvent.click(close);
  const post = await vi.waitFor(() => { const r = requests.find((q) => q.method === "POST"); if (!r) throw new Error("no post"); return r; });
  expect(await post.json()).toEqual({ confirm_name: "Synthetic Team" });
});

it("shows the erase date and lets the owner cancel", async () => {
  const requests = stubApi({ "DELETE /api/v1/orgs/primary/closure": [204, null] });
  renderWithProviders(<SettingsView org={{ ...org, closure_erase_after: "2026-12-23T10:00:00Z" }} />);
  expect(screen.getByRole("status").textContent).toBe("Cierre solicitado: los datos se borrarán el 23 de diciembre de 2026.");
  fireEvent.click(screen.getByRole("button", { name: "Cancelar el cierre" }));
  await vi.waitFor(() => { if (!requests.some((q) => q.method === "DELETE")) throw new Error("no delete"); });
});
