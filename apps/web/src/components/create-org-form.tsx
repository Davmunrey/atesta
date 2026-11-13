"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";
import { useCreateOrg } from "@/lib/api/hooks";
import { goTo } from "@/lib/navigation";
import { orgHome } from "@/lib/org";
import { ErrorMessage } from "./error-message";

export function CreateOrgForm() {
  const t = useTranslations("createOrg");
  const create = useCreateOrg();
  const nameId = useId();

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    create.mutate(name, { onSuccess: (org) => goTo(orgHome(org.id)) });
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-3">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <p className="text-muted">{t("help")}</p>
      <label htmlFor={nameId} className="font-medium">
        {t("name")}
      </label>
      <input
        id={nameId}
        name="name"
        required
        maxLength={200}
        autoComplete="organization"
        className="rounded-md border border-border bg-bg px-3 py-2"
      />
      {create.isError ? <ErrorMessage error={create.error} /> : null}
      <button
        type="submit"
        disabled={create.isPending}
        className="self-start rounded-md bg-accent px-4 py-2 font-medium text-accent-fg disabled:opacity-60"
      >
        {t("submit")}
      </button>
    </form>
  );
}
