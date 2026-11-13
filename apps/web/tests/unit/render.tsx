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

type Reply = [status: number, body: unknown];

/**
 * Replaces fetch with canned replies keyed by "METHOD /path". A list is consumed in order and its
 * last reply repeats. Unrouted requests get 404. Returns every request made, in order.
 */
export function stubApi(routes: Record<string, Reply | Reply[]>): Request[] {
  const requests: Request[] = [];
  const queues = new Map(
    Object.entries(routes).map(([key, value]) => [key, Array.isArray(value[0]) ? [...(value as Reply[])] : [value as Reply]]),
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      requests.push(request);
      const queue = queues.get(`${request.method} ${new URL(request.url).pathname}`);
      const [status, body] = (queue && queue.length > 1 ? queue.shift() : queue?.[0]) ?? [404, {}];
      return new Response(status === 204 ? null : JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return requests;
}
