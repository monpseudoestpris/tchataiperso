export const INTERFACE_THEMES = [
  { id: "light", label: "Clair", mode: "light", preview: "#f8fafc", accent: "#6366f1" },
  { id: "dark", label: "Sombre", mode: "dark", preview: "#0f172a", accent: "#a5b4fc" },
  { id: "ocean", label: "Océan", mode: "light", preview: "#eff8fb", accent: "#0369a1" },
  { id: "forest", label: "Forêt", mode: "light", preview: "#f1f8f2", accent: "#166534" },
  { id: "lavender", label: "Lavande", mode: "light", preview: "#f7f3fc", accent: "#7e22ce" },
  { id: "sand", label: "Sable", mode: "light", preview: "#faf6ed", accent: "#a16207" },
  { id: "rose", label: "Rose", mode: "light", preview: "#fcf3f5", accent: "#be185d" },
  { id: "midnight", label: "Nuit bleue", mode: "dark", preview: "#0b172b", accent: "#60a5fa" },
  { id: "graphite", label: "Graphite", mode: "dark", preview: "#17191d", accent: "#a1a1aa" },
  { id: "aubergine", label: "Aubergine", mode: "dark", preview: "#21142a", accent: "#c084fc" },
  { id: "emerald", label: "Émeraude", mode: "dark", preview: "#10231d", accent: "#6ee7b7" },
  { id: "cocoa", label: "Cacao", mode: "dark", preview: "#251a17", accent: "#fdba74" },
] as const;

export type InterfaceTheme = (typeof INTERFACE_THEMES)[number];
export const INTERFACE_THEME_KEY = "clair-interface-theme";
const INTERFACE_THEME_EVENT = "clair-interface-theme-change";

export function getInterfaceTheme(id: string | null): InterfaceTheme {
  return INTERFACE_THEMES.find((theme) => theme.id === id) ?? INTERFACE_THEMES[0];
}

export function applyInterfaceTheme(theme: InterfaceTheme): void {
  document.documentElement.dataset.theme = theme.mode;
  document.documentElement.dataset.palette = theme.id;
}

export function readInterfaceTheme(): InterfaceTheme {
  if (typeof window === "undefined") return INTERFACE_THEMES[0];
  // The active palette also survives a failed storage write for this page's lifetime.
  const active = document.documentElement.dataset.palette;
  if (active) return getInterfaceTheme(active);
  try {
    return getInterfaceTheme(window.localStorage.getItem(INTERFACE_THEME_KEY));
  } catch {
    return getInterfaceTheme(document.documentElement.dataset.palette ?? null);
  }
}

export function saveInterfaceTheme(theme: InterfaceTheme): boolean {
  applyInterfaceTheme(theme);
  window.dispatchEvent(new Event(INTERFACE_THEME_EVENT));
  try {
    window.localStorage.setItem(INTERFACE_THEME_KEY, theme.id);
    return true;
  } catch {
    return false;
  }
}

/** Subscribe to both this page's choices and changes from other tabs. */
export function subscribeInterfaceTheme(onChange: () => void): () => void {
  function onStorage(event: StorageEvent) {
    if (event.key !== INTERFACE_THEME_KEY && event.key !== null) return;
    if (event.storageArea && event.storageArea !== window.localStorage) return;
    applyInterfaceTheme(getInterfaceTheme(event.key === null ? null : event.newValue));
    onChange();
  }
  window.addEventListener("storage", onStorage);
  window.addEventListener(INTERFACE_THEME_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(INTERFACE_THEME_EVENT, onChange);
  };
}

// The same allowlist is used before hydration to prevent a flash of the default theme.
export const interfaceThemeBootstrap = `(()=>{const themes=${JSON.stringify(INTERFACE_THEMES)};let id;try{id=localStorage.getItem(${JSON.stringify(INTERFACE_THEME_KEY)})}catch{}const theme=themes.find(t=>t.id===id)||themes[0];document.documentElement.dataset.theme=theme.mode;document.documentElement.dataset.palette=theme.id})()`;
