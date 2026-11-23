"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, lazy, useId, useState } from "react";
import type { Surface } from "./panel";

const Panel = lazy(() => import("./panel"));

/**
 * The assistant's launcher (assistant spec): a button fixed at the bottom right and a non-modal
 * `<dialog popover="auto">` (modern-web-guidance, dialog rule 2). The page stays usable, Esc and
 * the close button dismiss it, and the browser returns focus to the launcher. The panel, the
 * engine and the index load on first open only.
 */
export function AssistantLauncher({ surface, orgId }: { surface: Surface; orgId?: string | null }) {
  const t = useTranslations("assistant");
  const id = useId().replace(/:/g, "");
  const [opens, setOpens] = useState(0);
  return (
    <>
      <button type="button" className="assistant-launcher" popoverTarget={`assistant-${id}`}>
        <svg aria-hidden="true" viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 4.5h12v8H9l-3.5 3v-3H4z" /><path d="M7.5 7.5h5M7.5 10h3" />
        </svg>
        <span>{t("open")}</span>
      </button>
      <dialog id={`assistant-${id}`} popover="auto" className="assistant-dialog" aria-labelledby={`assistant-${id}-title`}
        onToggle={(event) => { if ((event.nativeEvent as ToggleEvent).newState === "open") setOpens((n) => n + 1); }}>
        <div className="assistant-head">
          <h2 id={`assistant-${id}-title`} className="assistant-title">{t("title")}</h2>
          <button type="button" className="assistant-button" popoverTarget={`assistant-${id}`} popoverTargetAction="hide">{t("close")}</button>
        </div>
        {opens > 0 ? <Suspense fallback={<p className="assistant-body text-muted">{t("loading")}</p>}><Panel surface={surface} orgId={orgId} focusTick={opens} /></Suspense> : null}
      </dialog>
    </>
  );
}

/** The signed-in assistant: answers link to the measure in the organization named in the URL. */
export function AppAssistant() {
  return <AssistantLauncher surface="app" orgId={useSearchParams().get("org")} />;
}
