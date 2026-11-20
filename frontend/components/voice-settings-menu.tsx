"use client";

import { Check, Square, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { VoiceOption } from "@/lib/voice-api";

export interface VoiceSettingsMenuProps {
  disabled?: boolean;
  ttsEnabled: boolean;
  voices: VoiceOption[];
  selectedVoice: string;
  autoReadEnabled: boolean;
  isSpeaking: boolean;
  onSelectVoice: (voiceId: string) => void;
  onToggleAutoRead: () => void;
  onStopSpeaking: () => void;
}

export function VoiceSettingsMenu({
  disabled = false,
  ttsEnabled,
  voices,
  selectedVoice,
  autoReadEnabled,
  isSpeaking,
  onSelectVoice,
  onToggleAutoRead,
  onStopSpeaking,
}: VoiceSettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (isSpeaking) {
    return (
      <button
        type="button"
        className="voice-icon-btn is-speaking"
        onClick={onStopSpeaking}
        title="Arrêter la lecture vocale"
        aria-label="Arrêter la lecture vocale"
      >
        <Square size={14} fill="currentColor" />
      </button>
    );
  }

  return (
    <div className="voice-menu-wrapper" ref={wrapperRef}>
      <button
        type="button"
        className={`voice-icon-btn ${autoReadEnabled ? "is-auto-on" : ""}`}
        disabled={disabled || !ttsEnabled}
        aria-expanded={open}
        aria-haspopup="menu"
        title={
          ttsEnabled
            ? autoReadEnabled
              ? `Voix Google (${selectedVoice}) · Lecture automatique active`
              : `Réglages de voix Google (${selectedVoice})`
            : "Synthèse vocale indisponible : configurez GOOGLE_API_KEY"
        }
        aria-label="Réglages de la synthèse vocale"
        onClick={() => setOpen((prev) => !prev)}
      >
        {autoReadEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
      </button>

      {open && (
        <div className="voice-menu-popover" role="menu">
          <div className="voice-menu-header">
            <span className="voice-menu-title">Voix Google TTS</span>
            <span className="voice-menu-tag">Filtre Markdown</span>
          </div>

          <button
            type="button"
            className={`voice-menu-toggle ${autoReadEnabled ? "is-active" : ""}`}
            onClick={onToggleAutoRead}
            role="menuitemcheckbox"
            aria-checked={autoReadEnabled}
          >
            <div className="voice-menu-toggle-text">
              <strong>Lecture automatique</strong>
              <span>Lire chaque nouvelle réponse à voix haute</span>
            </div>
            <span className={`voice-switch ${autoReadEnabled ? "is-on" : ""}`} aria-hidden="true" />
          </button>

          {voices.length > 0 && (
            <div className="voice-menu-list" role="group" aria-label="Choix de la voix">
              <div className="voice-menu-section-label">Timbre de la voix</div>
              {voices.map((v) => {
                const active = v.id === selectedVoice;
                return (
                  <button
                    key={v.id}
                    type="button"
                    className={`voice-menu-option ${active ? "is-selected" : ""}`}
                    onClick={() => {
                      onSelectVoice(v.id);
                      setOpen(false);
                    }}
                    role="menuitemradio"
                    aria-checked={active}
                  >
                    <div className="voice-menu-option-info">
                      <span className="voice-menu-option-name">{v.name}</span>
                      <span className="voice-menu-option-tone">{v.tone}</span>
                    </div>
                    {active && <Check size={14} />}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
