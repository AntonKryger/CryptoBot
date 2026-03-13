"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { THEMES, type Theme } from "@/lib/constants";

export function ThemeForcer() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const themeParam = searchParams.get("theme") as Theme | null;
    if (themeParam && THEMES.includes(themeParam)) {
      document.documentElement.setAttribute("data-theme", themeParam);
    }
  }, [searchParams]);

  return null;
}
