"use client";

import { Check, Moon, Palette, Sun } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  INTERFACE_THEMES,
  getInterfaceTheme,
  readInterfaceTheme,
  saveInterfaceTheme,
  subscribeInterfaceTheme,
  type InterfaceTheme,
} from "@/lib/interface-themes";

function getThemeIdSnapshot(): string {
  return readInterfaceTheme().id;
}

function getServerThemeId(): string {
  return INTERFACE_THEMES[0].id;
}

/** Abonnement réactif (hydration-safe) au thème & palette actifs de l'interface. */
export function useInterfaceTheme(): InterfaceTheme {
  const id = useSyncExternalStore(subscribeInterfaceTheme, getThemeIdSnapshot, getServerThemeId);
  return getInterfaceTheme(id);
}

const LIGHT_THEMES = INTERFACE_THEMES.filter(t => t.mode === "light");
const DARK_THEMES = INTERFACE_THEMES.filter(t => t.mode === "dark");

type FinanceThemeSwitcherProps = {
  compact?: boolean;
  onThemeChange?: (theme: InterfaceTheme) => void;
};

/** Sélecteur rapide Clair / Sombre + menu de palettes pour l'espace Marchés Financiers. */
export function FinanceThemeSwitcher({ compact = false, onThemeChange }: FinanceThemeSwitcherProps) {
  const theme = useInterfaceTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [lastPair, setLastPair] = useState<{ light: InterfaceTheme["id"]; dark: InterfaceTheme["id"] }>({
    light: "light",
    dark: "midnight",
  });
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!paletteOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setPaletteOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [paletteOpen]);

  function selectTheme(next: InterfaceTheme) {
    setLastPair(prev => ({
      ...prev,
      [next.mode]: next.id,
    }));
    saveInterfaceTheme(next);
    onThemeChange?.(next);
    setPaletteOpen(false);
  }

  function switchMode(targetMode: "light" | "dark") {
    if (theme.mode === targetMode) return;
    const candidateId = targetMode === "light" ? lastPair.light : lastPair.dark;
    const target = getInterfaceTheme(candidateId);
    const resolved = target.mode === targetMode ? target : (targetMode === "light" ? LIGHT_THEMES[0] : DARK_THEMES[0]);
    saveInterfaceTheme(resolved);
    onThemeChange?.(resolved);
  }

  return (
    <div className={`finance-theme-switcher ${compact ? "is-compact" : ""}`} ref={wrapRef}>
      <div className="finance-theme-mode-pill" role="group" aria-label="Mode d'affichage Clair ou Sombre">
        <button
          type="button"
          className={`finance-theme-mode-btn ${theme.mode === "light" ? "active" : ""}`}
          onClick={() => switchMode("light")}
          aria-pressed={theme.mode === "light"}
          title="Passer en thème clair"
        >
          <Sun size={13} />
          {!compact && <span>Clair</span>}
        </button>
        <button
          type="button"
          className={`finance-theme-mode-btn ${theme.mode === "dark" ? "active" : ""}`}
          onClick={() => switchMode("dark")}
          aria-pressed={theme.mode === "dark"}
          title="Passer en thème sombre"
        >
          <Moon size={13} />
          {!compact && <span>Sombre</span>}
        </button>
      </div>

      {!compact && (
        <div className="finance-palette-dropdown-wrap">
          <button
            type="button"
            className={`finance-palette-trigger ${paletteOpen ? "is-open" : ""}`}
            onClick={() => setPaletteOpen(prev => !prev)}
            aria-expanded={paletteOpen}
            aria-label="Choisir une palette de couleurs"
            title={`Palette active : ${theme.label}`}
          >
            <span
              className="finance-palette-swatch-dot"
              style={{ background: theme.accent, boxShadow: `0 0 0 2px ${theme.preview}` }}
            />
            <Palette size={13} />
            <span>{theme.label}</span>
          </button>

          {paletteOpen && (
            <div className="finance-palette-popover" role="menu" aria-label="Palettes d'interface">
              <div className="finance-palette-group-label">Thèmes clairs</div>
              <div className="finance-palette-grid">
                {LIGHT_THEMES.map(item => {
                  const isActive = item.id === theme.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={isActive}
                      className={`finance-palette-item ${isActive ? "is-active" : ""}`}
                      onClick={() => selectTheme(item)}
                    >
                      <span
                        className="finance-palette-chip"
                        style={{ background: item.preview, borderColor: item.accent }}
                      >
                        <span className="finance-palette-chip-dot" style={{ background: item.accent }} />
                      </span>
                      <span className="finance-palette-name">{item.label}</span>
                      {isActive && <Check size={12} className="finance-palette-check" />}
                    </button>
                  );
                })}
              </div>

              <div className="finance-palette-group-label">Thèmes sombres</div>
              <div className="finance-palette-grid">
                {DARK_THEMES.map(item => {
                  const isActive = item.id === theme.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={isActive}
                      className={`finance-palette-item ${isActive ? "is-active" : ""}`}
                      onClick={() => selectTheme(item)}
                    >
                      <span
                        className="finance-palette-chip"
                        style={{ background: item.preview, borderColor: item.accent }}
                      >
                        <span className="finance-palette-chip-dot" style={{ background: item.accent }} />
                      </span>
                      <span className="finance-palette-name">{item.label}</span>
                      {isActive && <Check size={12} className="finance-palette-check" />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
