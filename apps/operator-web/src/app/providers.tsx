"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { retryQuery } from "@atesta/ui/api-error";
import { I18nProvider } from "@atesta/ui/i18n/provider";
import { type ReactNode, useState } from "react";
import { MESSAGES } from "@/lib/messages";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: retryQuery } } }));
  return (
    <QueryClientProvider client={client}>
      <I18nProvider messages={MESSAGES}>{children}</I18nProvider>
    </QueryClientProvider>
  );
}
