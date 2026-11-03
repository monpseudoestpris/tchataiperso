"use client";

import { useState, useSyncExternalStore } from "react";
import { Palette } from "lucide-react";
import { INTERFACE_THEMES, readInterfaceTheme, saveInterfaceTheme, subscribeInterfaceTheme } from "@/lib/interface-themes";

const serverTheme = () => INTERFACE_THEMES[0];

export function InterfaceThemePicker() {
  const selected = useSyncExternalStore(subscribeInterfaceTheme, readInterfaceTheme, serverTheme);
  const [storageUnavailable, setStorageUnavailable] = useState(false);

  return (
    <section className="settings-section interface-theme-section" aria-labelledby="interface-theme-title">
      <div className="settings-section-header">
        <div className="settings-section-title-wrap">
          <span className="settings-section-icon"><Palette size={18} /></span>
          <div>
            <h3 id="interface-theme-title">Apparence de l’application</h3>
            <p>Le thème s’applique immédiatement et est mémorisé dans ce navigateur.</p>
          </div>
        </div>
      </div>
      <div className="interface-theme-grid" role="group" aria-label="Choisir le thème de l’interface">
        {INTERFACE_THEMES.map((theme) => (
          <button key={theme.id} type="button" className="interface-theme-option" aria-pressed={selected.id === theme.id} onClick={() => {
            setStorageUnavailable(!saveInterfaceTheme(theme));
          }}>
            <span className="interface-theme-preview" style={{ backgroundColor: theme.preview, color: theme.accent }} aria-hidden="true">●</span>
            <span>{theme.label}</span>
          </button>
        ))}
      </div>
      {storageUnavailable && <p role="status">Le thème est actif, mais ce navigateur ne permet pas de mémoriser la préférence.</p>}
    </section>
  );
}
