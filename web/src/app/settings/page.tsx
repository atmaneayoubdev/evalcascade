import type { Metadata } from "next";
import { SettingsPage } from "@/components/pages/settings-page";

export const metadata: Metadata = { title: "Settings" };

export default function Page() {
  return <SettingsPage />;
}
