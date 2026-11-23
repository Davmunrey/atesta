// @vitest-environment jsdom
import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NotFound from "@/app/not-found";
import { AcceptInvite } from "@/components/accept-invite";
import { PublicHeader } from "@/components/public-header";
import { TrainingConfirm } from "@/components/training-confirm";
import { renderWithProviders, stubApi } from "./render";

// Public pages (ui-polish spec, issue 301).
vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));
beforeEach(() => { sessionStorage.clear(); window.history.replaceState(null, "", "/"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("gives every public page one header: skip link, wordmark home and the language switcher", () => {
  renderWithProviders(<PublicHeader />);
  expect(screen.getByRole("link", { name: "Saltar al contenido" }).getAttribute("href")).toBe("#content");
  expect(screen.getByRole("link", { name: "Volver al inicio de Atesta" }).getAttribute("href")).toBe("/");
  expect(screen.getByRole("navigation", { name: "Idioma" })).toBeTruthy();
});

it("frames the 404 page like every public page", () => {
  renderWithProviders(<NotFound />);
  expect(screen.getByRole("link", { name: "Volver al inicio de Atesta" })).toBeTruthy();
  expect(screen.getByRole("heading", { level: 1, name: "Esta página no existe." })).toBeTruthy();
  expect(document.querySelector("main#content")).toBeTruthy();
});

it("heads a missing invitation link and says what to do", async () => {
  renderWithProviders(<AcceptInvite />);
  expect(await screen.findByRole("heading", { level: 1, name: "Invitación no disponible" })).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toBe("Este enlace de invitación no es válido o ya se ha usado. Pide una invitación nueva.");
});

it("calls a malformed training link invalid, never a form error", async () => {
  window.history.replaceState(null, "", "/training#token=not-a-real-token");
  stubApi({ "POST /api/v1/training/link": [422, { detail: { code: "request.invalid", fields: ["body.token"] } }] });
  renderWithProviders(<TrainingConfirm />);
  expect(await screen.findByRole("heading", { level: 1, name: "Formación no disponible" })).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toBe("Este enlace de formación no es válido. Pide uno nuevo a quien te lo envió.");
});

it("heads a missing training link too", async () => {
  renderWithProviders(<TrainingConfirm />);
  expect(await screen.findByRole("heading", { level: 1, name: "Formación no disponible" })).toBeTruthy();
});
