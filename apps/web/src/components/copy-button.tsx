"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

/**
 * A visible copy button (modern-web-guidance copy-button, issue 384). React handles the click
 * because Invoker Commands are not Baseline Widely available. The status region beside the button,
 * not inside it, announces the result, success or failure. The button never disables itself, so
 * focus stays and a retry works.
 */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const t = useTranslations("public.copy");
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copy = async () => {
    window.clearTimeout(timer.current);
    let ok = true;
    try { await navigator.clipboard.writeText(text); } catch { ok = false; }
    setState(ok ? "done" : "failed");
    timer.current = window.setTimeout(() => setState("idle"), 2500);
  };
  return <span className="copy">
    <button type="button" className="copy-button" data-state={state} onClick={() => void copy()}>{label}</button>
    <span className="copy-status" role="status">{state === "idle" ? "" : t(state)}</span>
  </span>;
}
