import type { Metadata } from "next";
import { MetricsPage } from "@/components/pages/metrics-page";

export const metadata: Metadata = { title: "Metrics" };

export default function Page() {
  return <MetricsPage />;
}
