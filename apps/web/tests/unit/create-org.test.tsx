// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CreateOrgForm } from "@/components/create-org-form";
import { goTo } from "@/lib/navigation";
import { renderWithProviders, stubFetch } from "./render";

vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(goTo).mockReset();
});

function submit(name: string) {
  fireEvent.change(screen.getByLabelText("Nombre de la organización"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "Crear organización" }));
}

it("creates the organization and opens it", async () => {
  const requests = stubFetch([201, { id: "org-1", name: "Acme" }]);
  renderWithProviders(<CreateOrgForm />);
  submit("Acme");
  await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith("/app/org?org=org-1"));
  expect(requests[0]!.method).toBe("POST");
  expect(await requests[0]!.json()).toEqual({ name: "Acme" });
});

it("shows the API's error in Spanish", async () => {
  stubFetch([403, { detail: { code: "identity.forbidden" } }]);
  renderWithProviders(<CreateOrgForm />);
  submit("Acme");
  expect((await screen.findByRole("alert")).textContent).toBe("Tu rol no permite esta acción.");
  expect(goTo).not.toHaveBeenCalled();
});
