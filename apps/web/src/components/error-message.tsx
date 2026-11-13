"use client";

import { useTranslations } from "next-intl";
import { ApiError } from "@/lib/api/hooks";
import { messageKey } from "@/lib/api/errors";

export function ErrorMessage({ error }: { error: unknown }) {
  const t = useTranslations();
  const code = error instanceof ApiError ? error.code : null;
  return (
    <p role="alert" className="rounded-md border border-danger px-3 py-2 text-danger">
      {t(messageKey(code))}
    </p>
  );
}
