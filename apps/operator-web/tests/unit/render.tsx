import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { StaffContext } from "@/components/portal-shell";
import { MESSAGES } from "@/lib/messages";
import type { StaffRole } from "@/lib/roles";

/** A screen inside the shell, signed in with `role`. */
export function renderAs(role: StaffRole, ui: ReactNode, locale: "es" | "en" = "es") {
  return renderWithProviders(<StaffContext value={{ email: `${role}@atesta.test`, role }}>{ui}</StaffContext>, locale);
}

export function renderWithProviders(ui: ReactNode, locale: "es" | "en" = "es") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="UTC">{ui}</NextIntlClientProvider>
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
  vi.stubGlobal("fetch", vi.fn(async (request: Request) => {
    requests.push(request);
    const queue = queues.get(`${request.method} ${new URL(request.url).pathname}`);
    const [status, body] = (queue && queue.length > 1 ? queue.shift() : queue?.[0]) ?? [404, {}];
    return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }));
  return requests;
}
