"use client";

import { useTranslations } from "next-intl";
import customers from "@/content/customers.json";

type Customer = { name: string; logo?: string; permission_ref: string; permission_date: string };

/** Customer logos only with written permission (A3); `test_claims` checks every entry. The file
 *  starts empty, and the section does not render while it is. */
export function CustomerLogos() {
  const t = useTranslations("public.customers");
  const list = customers as Customer[];
  if (list.length === 0) return null;
  return <section className="customer-logos" aria-label={t("title")}>
    {/* eslint-disable-next-line @next/next/no-img-element -- static export: images are not optimised (next.config) */}
    <ul>{list.map((c) => <li key={c.name}>{c.logo ? <img src={c.logo} alt={c.name} /> : c.name}</li>)}</ul>
  </section>;
}
