import type { Metadata } from "next";
import { Suspense } from "react";
import { PageSkeleton } from "@/components/common/states";
import { ComparePage } from "@/components/pages/compare-page";

export const metadata: Metadata = { title: "Compare" };

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton kpis={4} panels={2} />}>
      <ComparePage />
    </Suspense>
  );
}
