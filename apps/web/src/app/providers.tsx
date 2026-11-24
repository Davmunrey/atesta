"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "@atesta/ui/i18n/provider";
import { type ReactNode, useState } from "react";
import { retryQuery } from "@/lib/api/retry";
import en from "../../messages/en.json";
import es from "../../messages/es.json";

const MESSAGES = { es, en } as const;

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: retryQuery } } }));
  return (
    <QueryClientProvider client={client}>
      <I18nProvider messages={MESSAGES}>{children}</I18nProvider>
    </QueryClientProvider>
  );
}
