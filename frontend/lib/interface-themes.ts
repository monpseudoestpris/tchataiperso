export const INTERFACE_THEMES = [
  { id: "light", label: "Clair", mode: "light", preview: "#faf9f6", accent: "#b4532a" },
  { id: "dark", label: "Sombre", mode: "dark", preview: "#141311", accent: "#de8a62" },
  { id: "ocean", label: "Océan", mode: "light", preview: "#f5f9fb", accent: "#0e5a7c" },
  { id: "forest", label: "Forêt", mode: "light", preview: "#f6f9f6", accent: "#1f5c3a" },
  { id: "lavender", label: "Lavande", mode: "light", preview: "#f9f7fc", accent: "#673ab7" },
  { id: "sand", label: "Sable", mode: "light", preview: "#fbf8f1", accent: "#8f5314" },
  { id: "rose", label: "Rose", mode: "light", preview: "#fcf7f8", accent: "#9f2d52" },
  { id: "midnight", label: "Nuit bleue", mode: "dark", preview: "#0d1624", accent: "#7cb3f5" },
  { id: "graphite", label: "Graphite", mode: "dark", preview: "#151619", accent: "#b8bec9" },
  { id: "aubergine", label: "Aubergine", mode: "dark", preview: "#1a1222", accent: "#cfa8f5" },
  { id: "emerald", label: "Émeraude", mode: "dark", preview: "#0f1d17", accent: "#74d9a6" },
  { id: "cocoa", label: "Cacao", mode: "dark", preview: "#1c1411", accent: "#e6a979" },
] as const;

export type InterfaceTheme = (typeof INTERFACE_THEMES)[number];
export const INTERFACE_THEME_KEY = "clair-interface-theme";
const INTERFACE_THEME_EVENT = "clair-interface-theme-change";

export function getInterfaceTheme(id: string | null): InterfaceTheme {
  return INTERFACE_THEMES.find((theme) => theme.id === id) ?? INTERFACE_THEMES[0];
}

export function getOppositeModeTheme(current: InterfaceTheme): InterfaceTheme {
  return getInterfaceTheme(current.mode === "dark" ? "light" : "dark");
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
