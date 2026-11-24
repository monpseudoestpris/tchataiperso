"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import {
  INTERFACE_THEMES,
  getOppositeModeTheme,
  readInterfaceTheme,
  saveInterfaceTheme,
  subscribeInterfaceTheme,
} from "@/lib/interface-themes";

const serverTheme = () => INTERFACE_THEMES[0];

/** Bascule rapide Clair ↔ Sombre dans la barre supérieure. */
export function QuickThemeToggle() {
  const selected = useSyncExternalStore(subscribeInterfaceTheme, readInterfaceTheme, serverTheme);
  const isDark = selected.mode === "dark";
  const nextLabel = isDark ? "Passer au thème clair" : "Passer au thème sombre";

  return (
    <button
      type="button"
      className="topbar-theme-btn"
      onClick={() => {
        saveInterfaceTheme(getOppositeModeTheme(selected));
      }}
      aria-label={nextLabel}
      title={nextLabel}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
