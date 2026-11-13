"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { I18nProvider } from "@/i18n/provider";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } }));
  return (
    <QueryClientProvider client={client}>
      <I18nProvider>{children}</I18nProvider>
    </QueryClientProvider>
  );
}
