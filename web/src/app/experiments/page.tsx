import type { Metadata } from "next";
import { ExperimentsPage } from "@/components/pages/experiments-page";

export const metadata: Metadata = { title: "Experiments" };

export default function Page() {
  return <ExperimentsPage />;
}
