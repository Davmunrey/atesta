import type { Metadata } from "next";
import { TrainingConfirm } from "@/components/training-confirm";

// The token lives in the fragment, which browsers never send; no referrer leaves this page either.
export const metadata: Metadata = { referrer: "no-referrer" };

export default function TrainingPage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6 py-12">
      <TrainingConfirm />
    </main>
  );
}
