import type { Metadata } from "next";
import { UnsubscribeConfirm } from "@/components/unsubscribe-confirm";

// The token lives in the fragment, which browsers never send; no referrer leaves this page either.
export const metadata: Metadata = { referrer: "no-referrer" };

export default function UnsubscribePage() {
  return (
    <main id="content" tabIndex={-1} className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6 py-12">
      <UnsubscribeConfirm />
    </main>
  );
}
