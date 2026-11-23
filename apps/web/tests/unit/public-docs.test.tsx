// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ApiReference } from "@/components/api-reference";
import { McpGuide, MCP_TOOLS } from "@/components/mcp-guide";
import { keyOperations } from "@/lib/api-reference";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import { renderWithProviders } from "./render";

afterEach(cleanup);

it("reads every key route, its permission and its body from the contract", () => {
  const ops = keyOperations();
  expect(ops.map((o) => `${o.method} ${o.path}`)).toContain("POST /api/v1/ingest/evidence");
  expect(ops).toHaveLength(14);
  const ingest = ops.find((o) => o.path === "/api/v1/ingest/evidence")!;
  expect(ingest.scope).toBe("evidence:write");
  expect(ingest.body.find((f) => f.name === "title")).toEqual({ name: "title", type: "string", required: true, limits: ["1–200"] });
  expect(ops.find((o) => o.path === "/api/v1/key")!.scope).toBeNull();
  for (const op of ops) {
    expect((es.apiDocs.operations as Record<string, string>)[op.id], op.id).toBeTruthy();
    expect((en.apiDocs.operations as Record<string, string>)[op.id], op.id).toBeTruthy();
  }
});

it("lists every key route under its permission, in Spanish and English", () => {
  const ops = keyOperations();
  renderWithProviders(<ApiReference operations={ops} />);
  for (const op of ops) expect(screen.getByRole("heading", { name: `${op.method} ${op.path}` })).toBeTruthy();
  expect(screen.getByRole("heading", { level: 1, name: "Referencia de la API" })).toBeTruthy();
  const scope = screen.getByRole("region", { name: /Registrar evidencias/ });
  expect(within(scope).getByRole("heading", { name: "POST /api/v1/ingest/evidence" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Guía para agentes de IA (MCP)" }).getAttribute("href")).toBe("/docs/mcp");
  cleanup();
  renderWithProviders(<ApiReference operations={ops} />, "en");
  expect(screen.getByRole("heading", { level: 1, name: "API reference" })).toBeTruthy();
});

it("offers exactly the tools the MCP server defines", () => {
  const server = readFileSync(join(__dirname, "../../../mcp/src/atesta_mcp/server.py"), "utf8");
  const defined = [...server.matchAll(/@tool\([^)]*\)\n\s+async def (\w+)\(/g)].map((m) => m[1]);
  expect(defined.length).toBe(14);
  expect([...MCP_TOOLS.read, ...MCP_TOOLS.write].map((t) => t.name).sort()).toEqual(defined.sort());
});

it("explains the safety model and says the hosted server is not available yet", () => {
  renderWithProviders(<McpGuide />);
  expect(screen.getByRole("heading", { level: 1, name: "Guía para agentes de IA (MCP)" })).toBeTruthy();
  expect(screen.getByText(/queda pendiente hasta que una persona la confirma/)).toBeTruthy();
  expect(screen.getByText(/aún no está disponible/)).toBeTruthy();
  expect(screen.getByText(/Todavía no se distribuye públicamente/)).toBeTruthy();
  const config = screen.getByLabelText("Configuración del cliente") as HTMLTextAreaElement;
  expect(JSON.parse(config.value).mcpServers.atesta.env.ATESTA_API_KEY).toBe("atesta_…");
  cleanup();
  renderWithProviders(<McpGuide />, "en");
  expect(screen.getByRole("heading", { level: 1, name: "AI agent guide (MCP)" })).toBeTruthy();
});
