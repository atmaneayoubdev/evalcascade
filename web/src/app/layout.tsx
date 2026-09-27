import type { Metadata, Viewport } from "next";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MobileNav, Sidebar } from "@/components/shell/sidebar";
import { THEME_SCRIPT, ThemeSync } from "@/components/shell/theme";

export const metadata: Metadata = {
  title: { default: "EvalCascade", template: "%s | EvalCascade" },
  description:
    "Local dashboard for EvalCascade: adaptive evaluation for LLM, RAG and agent systems. System One judges first, LLMs only when necessary.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f5f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0f13" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <ThemeSync />
        <TooltipProvider delayDuration={150}>
          <a
            href="#main"
            className="sr-only z-50 rounded-md bg-surface px-3 py-2 text-sm focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
          >
            Skip to content
          </a>
          <div className="flex min-h-dvh">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <MobileNav />
              <main id="main" className="mx-auto w-full max-w-[1360px] flex-1 px-4 pt-6 pb-16 sm:px-6 lg:px-8 lg:pt-8">
                {children}
              </main>
            </div>
          </div>
        </TooltipProvider>
      </body>
    </html>
  );
}
