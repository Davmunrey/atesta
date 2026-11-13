import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { vi } from "vitest";
import es from "../../messages/es.json";

export function renderWithProviders(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="es" messages={es} timeZone="UTC">
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

/** Replaces fetch with one canned JSON response per call, in order; records the requests. */
export function stubFetch(...responses: [number, unknown][]): Request[] {
  const requests: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      requests.push(request);
      const [status, body] = responses.shift() ?? [500, {}];
      return new Response(status === 204 ? null : JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return requests;
}
