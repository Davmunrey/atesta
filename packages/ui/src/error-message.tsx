"use client";

import { useMessages, useTranslations } from "next-intl";
import { ApiError, messageKey } from "./api-error";

export function ErrorMessage({ error }: { error: unknown }) {
  const t = useTranslations();
  const messages = useMessages();
  const code = error instanceof ApiError ? error.code : null;
  return (
    <p role="alert" className="rounded-md border border-danger px-3 py-2 text-danger">
      {t(messageKey(code, messages))}
    </p>
  );
}
