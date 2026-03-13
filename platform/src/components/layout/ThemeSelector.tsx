"use client";

import { useState, useRef, useEffect } from "react";
import { Paintbrush } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { THEMES, THEME_LABELS, type Theme } from "@/lib/constants";
import { cn } from "@/lib/utils";

const THEME_ACCENT_COLORS: Record<Theme, string> = {
  midnight: "#6366f1",
  matrix: "#22c55e",
  aurora: "#a78bfa",
  stealth: "#e5e5e5",
  solar: "#f59e0b",
};

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-lg transition-colors",
          "text-text-secondary hover:text-text-primary hover:bg-bg-card-hover"
        )}
        title="Change theme"
      >
        <Paintbrush className="h-[18px] w-[18px]" />
      </button>

      {open && (
        <div
          className={cn(
            "absolute right-0 top-full mt-2 w-48 rounded-lg border border-border bg-bg-card p-1.5 shadow-xl",
            "animate-fade-in z-50"
          )}
        >
          <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-text-muted">
            Theme
          </p>
          {THEMES.map((t) => (
            <button
              key={t}
              onClick={() => {
                setTheme(t);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                t === theme
                  ? "bg-accent-muted text-accent"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-card-hover"
              )}
            >
              <span
                className="h-3 w-3 rounded-full shrink-0 border border-border"
                style={{ backgroundColor: THEME_ACCENT_COLORS[t] }}
              />
              <span>{THEME_LABELS[t]}</span>
              {t === theme && (
                <span className="ml-auto text-xs text-accent">&#10003;</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
