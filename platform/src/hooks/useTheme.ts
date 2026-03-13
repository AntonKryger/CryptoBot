"use client";

import { useCallback, useEffect, useState } from "react";
import { type Theme, THEMES } from "@/lib/constants";

const STORAGE_KEY = "cryptobot-theme";

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>("midnight");

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored && THEMES.includes(stored)) {
      setThemeState(stored);
      document.documentElement.setAttribute("data-theme", stored);
    }
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem(STORAGE_KEY, t);
    document.documentElement.setAttribute("data-theme", t);
  }, []);

  return { theme, setTheme };
}
