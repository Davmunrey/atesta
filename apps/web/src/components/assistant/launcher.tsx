"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, lazy, useId, useState } from "react";
import { BrandMark } from "../brand-mark";
import type { Surface } from "./panel";

const Panel = lazy(() => import("./panel"));

/**
 * The assistant's launcher (assistant spec): a button fixed at the bottom right and a non-modal
 * `<dialog popover="auto">` (modern-web-guidance, dialog rule 2). The page stays usable, Esc and
 * the close button dismiss it, and the browser returns focus to the launcher. The panel, the
 * engine and the index load on first open only. `invite` adds an inline button that opens the same
 * dialog, for pages that point a visitor to the assistant (the 404, issue 384).
 */
export function AssistantLauncher({ surface, orgId, invite }: { surface: Surface; orgId?: string | null; invite?: string }) {
  const t = useTranslations("assistant");
  const id = useId().replace(/:/g, "");
  const [opens, setOpens] = useState(0);
  return (
    <>
      {invite ? <button type="button" className="landing-cta" popoverTarget={`assistant-${id}`}>{invite}</button> : null}
      <button type="button" className="assistant-launcher" popoverTarget={`assistant-${id}`}>
        <BrandMark />
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
