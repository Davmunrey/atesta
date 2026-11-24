import type { Metadata } from "next";
import { PublicCard } from "@/components/public/public-card";
import { TrainingConfirm } from "@/components/training-confirm";

// The token lives in the fragment, which browsers never send; no referrer leaves this page either.
export const metadata: Metadata = { referrer: "no-referrer" };

export default function TrainingPage() {
  return (
    <main id="content" tabIndex={-1} className="public-card-page">
      <PublicCard><TrainingConfirm /></PublicCard>
    </main>
  );
}
