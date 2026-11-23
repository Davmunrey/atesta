"use client";

import { useTranslations } from "next-intl";
import { LOCALE_COOKIE, ONE_YEAR_SECONDS } from "@/i18n/locale";
import { INVITE_KEY } from "@/lib/invite";

// Browser tests compare these documented lifetimes with the real API's cookies.
const COOKIES = [
  { key: "locale", name: LOCALE_COOKIE, seconds: ONE_YEAR_SECONDS },
  { key: "auth", name: "atesta_auth", seconds: 600 },
  { key: "access", name: "atesta_at", seconds: 43200 },
  { key: "refresh", name: "atesta_rt", seconds: 43200 },
] as const;
const SECTIONS = ["inventory", "storage", "signin", "choices"] as const;

export default function CookiesPage() {
  const t = useTranslations("cookies");
  const brand = useTranslations("brand");
  function duration(seconds: number) {
    if (seconds >= 86400) return t("days", { count: seconds / 86400 });
    if (seconds >= 3600) return t("hours", { count: seconds / 3600 });
    return t("minutes", { count: seconds / 60 });
  }
  return (
    <>
      <main id="content" tabIndex={-1} className="policy-page">
        <div className="policy-heading">
          <h1 className="page-title">{t("title")}</h1>
          <p className="text-sm text-muted">{t("updated")}</p>
          <p>{t("intro")}</p>
        </div>
        <div className="policy-layout">
          <nav aria-label={t("index")} className="policy-index">
            <p className="font-medium">{t("index")}</p>
            {SECTIONS.map((id) => <a key={id} href={`#${id}`} className="underline">{t(`${id}.title`, { brand: brand("name") })}</a>)}
          </nav>
          <div className="policy-copy">
            <section id="inventory" aria-labelledby="inventory-title">
              <h2 id="inventory-title">{t("inventory.title", { brand: brand("name") })}</h2>
              <p>{t("inventory.intro", { brand: brand("name") })}</p>
              <dl className="storage-list">
                {COOKIES.map(({ key, name, seconds }) => (
                  <div key={name}>
                    <dt><code className="font-mono text-sm">{name}</code></dt>
                    <dd>
                      <p>{t(`items.${key}`)}</p>
                      <p className="cookie-period"><span>{t("duration")}</span> <time dateTime={`PT${seconds}S`}>{duration(seconds)}</time></p>
                    </dd>
                  </div>
                ))}
              </dl>
              <p>{t("inventory.retention")}</p>
            </section>
            <section id="storage" aria-labelledby="storage-title">
              <h2 id="storage-title">{t("storage.title")}</h2>
              <p>{t.rich("storage.body", { key: () => <code className="font-mono text-sm">{INVITE_KEY}</code> })}</p>
            </section>
            <section id="signin" aria-labelledby="signin-title">
              <h2 id="signin-title">{t("signin.title")}</h2>
              <p>{t("signin.body", { brand: brand("name") })}</p>
              <a href="https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html" className="text-link underline">{t("signin.source")}</a>
            </section>
            <section id="choices" aria-labelledby="choices-title">
              <h2 id="choices-title">{t("choices.title")}</h2>
              <p>{t("choices.body", { brand: brand("name") })}</p>
              <p>{t("choices.consequences")}</p>
            </section>
          </div>
        </div>
      </main>
    </>
  );
}
