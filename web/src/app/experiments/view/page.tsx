import type { Metadata } from "next";
import { Suspense } from "react";
import { PageSkeleton } from "@/components/common/states";
import { ExperimentPage } from "@/components/pages/experiment-page";

export const metadata: Metadata = { title: "Experiment" };

// Static export: the experiment id arrives as ?id=..., read on the client.
export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton kpis={8} panels={3} />}>
      <ExperimentPage />
    </Suspense>
  );
}
