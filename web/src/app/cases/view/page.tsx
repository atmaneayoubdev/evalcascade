import type { Metadata } from "next";
import { Suspense } from "react";
import { PageSkeleton } from "@/components/common/states";
import { CasePage } from "@/components/pages/case-page";

export const metadata: Metadata = { title: "Case" };

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton kpis={4} panels={3} />}>
      <CasePage />
    </Suspense>
  );
}
