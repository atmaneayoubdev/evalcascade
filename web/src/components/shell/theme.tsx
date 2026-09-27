"use client";

import { useEffect } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "cn";
import { themePreference, useStored, type ThemePreference } from "@/hooks/use-stored";

/** Runs before first paint (inlined in <head>) so there is no light/dark flash. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem('evalcascade.theme');var d=t==='dark'||((!t||t==='system')&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;

function apply(pref: ThemePreference) {
  const dark =
    pref === "dark" || (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** Keeps the <html> class in sync with the preference and, in system mode, the OS. */
export function ThemeSync() {
  const [pref] = useStored(themePreference);
  useEffect(() => {
    apply(pref);
    if (pref !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [pref]);
  return null;
}

const OPTIONS: { value: ThemePreference; label: string; Icon: typeof Sun }[] = [
  { value: "system", label: "Match system", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
];

export function ThemeToggle({ className }: { className?: string }) {
  const [pref, setPref] = useStored(themePreference);
  return (
    <div
      role="radiogroup"
      aria-label="Color theme"
      className={cn("inline-flex items-center rounded-md border border-hairline bg-surface p-0.5", className)}
    >
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={pref === value}
          aria-label={label}
          title={label}
          onClick={() => setPref(value)}
          className={cn(
            "grid size-6 place-items-center rounded-[5px] text-ink-3 transition-colors hover:text-ink",
            pref === value && "bg-sunken text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong)]",
          )}
        >
          <Icon className="size-3.5" aria-hidden />
        </button>
      ))}
    </div>
  );
}
