"use client";

import { Check, Pause, Play, Square, Volume2, VolumeX } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ToneOption, VoiceOption } from "@/lib/voice-api";

const DEFAULT_TONES: ToneOption[] = [
  { id: "natural", label: "Naturel" },
  { id: "warm", label: "Chaleureux" },
  { id: "enthusiastic", label: "Dynamique" },
  { id: "calm", label: "Calme" },
  { id: "teacher", label: "Pédagogue" },
  { id: "storyteller", label: "Conteur" },
  { id: "podcast", label: "Podcast" },
  { id: "whisper", label: "Chuchoté" },
];

export const VOICE_SPEED_OPTIONS = [0.85, 1, 1.15, 1.25, 1.5, 1.75, 2] as const;

export function formatSpeedLabel(rate: number): string {
  return `${Number.isInteger(rate) ? rate : rate}×`;
}

export interface VoiceSettingsMenuProps {
  disabled?: boolean;
  ttsEnabled: boolean;
  voices: VoiceOption[];
  tones?: ToneOption[];
  selectedVoice: string;
  selectedTone: string;
  playbackSpeed: number;
  autoReadEnabled: boolean;
  isSpeaking: boolean;
  isPaused: boolean;
  onSelectVoice: (voiceId: string) => void;
  onSelectTone: (tone: string) => void;
  onSelectSpeed: (speed: number) => void;
  onToggleAutoRead: () => void;
  onTogglePause: () => void;
  onStopSpeaking: () => void;
}

export function VoiceSettingsMenu({
  disabled = false,
  ttsEnabled,
  voices,
  tones,
  selectedVoice,
  selectedTone,
  playbackSpeed,
  autoReadEnabled,
  isSpeaking,
  isPaused,
  onSelectVoice,
  onSelectTone,
  onSelectSpeed,
  onToggleAutoRead,
  onTogglePause,
  onStopSpeaking,
}: VoiceSettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const [voiceFilter, setVoiceFilter] = useState("");
  const wrapperRef = useRef<HTMLDivElement>(null);

  const toneOptions = tones && tones.length > 0 ? tones : DEFAULT_TONES;
  const presetIds = new Set(toneOptions.map((t) => t.id));
  const isCustomTone = Boolean(selectedTone && !presetIds.has(selectedTone));
  const activeToneLabel =
    toneOptions.find((t) => t.id === selectedTone)?.label || (isCustomTone ? selectedTone : "Naturel");

  const filteredVoices = useMemo(() => {
    const q = voiceFilter.trim().toLowerCase();
    if (!q) return voices;
    return voices.filter(
      (v) => v.name.toLowerCase().includes(q) || v.tone.toLowerCase().includes(q),
    );
  }, [voices, voiceFilter]);

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

  function cycleSpeed() {
    const idx = VOICE_SPEED_OPTIONS.findIndex((s) => Math.abs(s - playbackSpeed) < 0.01);
    const next = VOICE_SPEED_OPTIONS[(idx + 1) % VOICE_SPEED_OPTIONS.length];
    onSelectSpeed(next);
  }

  return (
    <div className="voice-menu-wrapper" ref={wrapperRef}>
      {isSpeaking ? (
        <div className="voice-playback-bar" role="group" aria-label="Contrôles de lecture vocale">
          <button
            type="button"
            className="voice-playback-btn is-toggle"
            onClick={onTogglePause}
            title={isPaused ? "Reprendre la lecture" : "Mettre en pause"}
            aria-label={isPaused ? "Reprendre la lecture" : "Mettre en pause"}
          >
            {isPaused ? <Play size={13} fill="currentColor" /> : <Pause size={13} fill="currentColor" />}
          </button>
          <button
            type="button"
            className="voice-playback-speed"
            onClick={cycleSpeed}
            title="Changer la vitesse de lecture"
            aria-label={`Vitesse de lecture ${formatSpeedLabel(playbackSpeed)}`}
          >
            {formatSpeedLabel(playbackSpeed)}
          </button>
          <button
            type="button"
            className="voice-playback-btn is-stop"
            onClick={onStopSpeaking}
            title="Arrêter la lecture"
            aria-label="Arrêter la lecture"
          >
            <Square size={12} fill="currentColor" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          className={`voice-icon-btn ${autoReadEnabled ? "is-auto-on" : ""}`}
          disabled={disabled || !ttsEnabled}
          aria-expanded={open}
          aria-haspopup="menu"
          title={
            ttsEnabled
              ? autoReadEnabled
                ? `Voix Google (${selectedVoice} · ${activeToneLabel} · ${formatSpeedLabel(playbackSpeed)}) · Lecture auto active`
                : `Voix Google (${selectedVoice} · ${activeToneLabel} · ${formatSpeedLabel(playbackSpeed)})`
              : "Synthèse vocale indisponible : configurez GOOGLE_API_KEY"
          }
          aria-label="Réglages de la synthèse vocale"
          onClick={() => setOpen((prev) => !prev)}
        >
          {autoReadEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
        </button>
      )}

      {open && (
        <div className="voice-menu-popover" role="menu">
          <div className="voice-menu-header">
            <span className="voice-menu-title">Voix Google TTS</span>
            <span className="voice-menu-tag">{voices.length} voix</span>
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

          <div className="voice-menu-section-label">Vitesse de lecture</div>
          <div className="voice-tone-grid" role="group" aria-label="Vitesse de lecture">
            {VOICE_SPEED_OPTIONS.map((rate) => {
              const active = Math.abs(playbackSpeed - rate) < 0.01;
              return (
                <button
                  key={rate}
                  type="button"
                  className={`voice-tone-pill ${active ? "is-selected" : ""}`}
                  onClick={() => onSelectSpeed(rate)}
                >
                  {formatSpeedLabel(rate)}
                </button>
              );
            })}
          </div>

          <div className="voice-menu-section-label">Ton / Style</div>
          <div className="voice-tone-grid" role="group" aria-label="Ton de la voix">
            {toneOptions.map((t) => {
              const active = selectedTone === t.id || (!selectedTone && t.id === "natural");
              return (
                <button
                  key={t.id}
                  type="button"
                  className={`voice-tone-pill ${active ? "is-selected" : ""}`}
                  onClick={() => onSelectTone(t.id)}
                >
                  {t.label}
                </button>
              );
            })}
          </div>
          <input
            type="text"
            className="voice-tone-custom-input"
            value={isCustomTone ? selectedTone : ""}
            onChange={(e) => onSelectTone(e.target.value || "natural")}
            placeholder="Ou ton libre (ex. joyeux, radio, ironique…)"
            maxLength={120}
            aria-label="Ton libre personnalisé"
          />

          {voices.length > 0 && (
            <div>
              <div className="voice-menu-section-label">Timbre de la voix ({voices.length})</div>
              {voices.length > 8 && (
                <input
                  type="search"
                  className="voice-tone-custom-input"
                  value={voiceFilter}
                  onChange={(e) => setVoiceFilter(e.target.value)}
                  placeholder="Filtrer une voix (ex. Sulafat, grave, douce…)"
                  aria-label="Filtrer les voix"
                />
              )}
              <div className="voice-menu-list" role="group" aria-label="Choix de la voix">
                {filteredVoices.map((v) => {
                  const active = v.id === selectedVoice;
                  return (
                    <button
                      key={v.id}
                      type="button"
                      className={`voice-menu-option ${active ? "is-selected" : ""}`}
                      onClick={() => onSelectVoice(v.id)}
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
                {filteredVoices.length === 0 && (
                  <div className="voice-menu-empty">Aucune voix correspondante</div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
