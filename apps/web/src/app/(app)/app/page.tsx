"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMe } from "@/components/auth-gate";
import { CreateOrgForm } from "@/components/create-org-form";
import { orgHome } from "@/lib/org";

/** First login without memberships lands on the create form; otherwise, pick an organization. */
export default function AppHome() {
  const t = useTranslations();
  const { memberships } = useMe();
  if (memberships.length === 0) return <CreateOrgForm />;
  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t("home.title")}</h1>
      <ul className="flex flex-col gap-2">
        {memberships.map((m) => (
          <li key={m.organization_id}>
            <Link href={orgHome(m.organization_id)} className="underline">
              {m.organization_name}
            </Link>{" "}
            <span className="text-sm text-muted">{t(`roles.${m.role}`)}</span>
          </li>
        ))}
      </ul>
      <Link href="/app/new" className="self-start text-sm underline">
        {t("home.createAnother")}
      </Link>
    </section>
  );
}
