// @vitest-environment jsdom
import { cleanup, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ExpectedEvidence } from "@/components/expected-evidence";
import { renderWithProviders } from "./render";

// Expected evidence polish (ui-polish spec, issue 295).
afterEach(cleanup);
const ref = (section: string, page: number) => ({ guide: "CCN-STIC 808", edition: "2026-04", section, page });
const item = (es: string, r: ReturnType<typeof ref>) => ({ es, en: es, ref: r });

it("states a reference shared by every item once, under the status line", () => {
  renderWithProviders(<ExpectedEvidence evidence={{ reviewed_by: null, items: [item("Uno.", ref("6.2.1", 18)), item("Dos.", ref("6.2.1", 18))] }} />);
  expect(screen.getAllByText(/CCN-STIC 808/)).toHaveLength(1);
  expect(screen.getByText("Referencia: CCN-STIC 808 (abril de 2026), apartado 6.2.1, pág. 18")).toBeTruthy();
});

it("keeps each item's reference when they differ", () => {
  renderWithProviders(<ExpectedEvidence evidence={{ reviewed_by: null, items: [item("Uno.", ref("6.2.1", 18)), item("Dos.", ref("6.2.2", 19))] }} />);
  expect(screen.getByText("CCN-STIC 808 (abril de 2026), apartado 6.2.1, pág. 18")).toBeTruthy();
  expect(screen.getByText("CCN-STIC 808 (abril de 2026), apartado 6.2.2, pág. 19")).toBeTruthy();
  expect(screen.queryByText(/^Referencia:/)).toBeNull();
});
