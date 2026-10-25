"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  AudioWaveform, Check, CircleAlert, Copy, Download, Languages, LoaderCircle,
  Pause, Play, RotateCcw, Search, Sparkles, Trash2, Volume2, VolumeX, WandSparkles, X
} from "lucide-react";
import {
  api, errorMessage, type Config, type GeneratedSound,
  createGeneratedSound, fetchGeneratedSounds, improveSoundPrompt, translateSoundPrompt, deleteGeneratedSound
} from "@/lib/api";

type SoundStudioModalProps = {
  config: Config | null;
  initialPrompt?: string;
  onClose: () => void;
  onSendToChat?: (sound: GeneratedSound) => void;
};

type SoundCategory = "all" | "cinema" | "scifi" | "nature" | "games" | "daily" | "horror";

const SOUND_CATEGORIES: { id: SoundCategory; label: string }[] = [
  { id: "all", label: "Tous les styles" },
  { id: "cinema", label: "🎬 Cinéma & Impacts" },
  { id: "scifi", label: "🛸 Science-Fiction" },
  { id: "nature", label: "🌧️ Nature & Éléments" },
  { id: "games", label: "🎮 Jeux vidéo & UI" },
  { id: "daily", label: "🚪 Quotidien & Objets" },
  { id: "horror", label: "👻 Frisson & Horreur" },
];

const SUGGESTED_SOUNDS: { label: string; prompt: string; category: SoundCategory; duration: number }[] = [
  {
    label: "⚡ Impact cinématique lourd",
    prompt: "Massive cinematic braam impact with deep sub bass rumble, metallic reverberation and dramatic tension",
    category: "cinema",
    duration: 4.0,
  },
  {
    label: "🌧️ Pluie battante & orage lointain",
    prompt: "Heavy pouring rain on wet concrete with distant thunder rolling across the dark stormy sky",
    category: "nature",
    duration: 6.0,
  },
  {
    label: "🛸 Téléportation & laser sci-fi",
    prompt: "Futuristic plasma blaster firing a sharp high-energy laser pulse followed by spatial recharging hum",
    category: "scifi",
    duration: 2.5,
  },
  {
    label: "🚪 Grincement de porte en bois",
    prompt: "Heavy old wooden dungeon door slowly creaking open in a vast silent stone corridor",
    category: "daily",
    duration: 3.0,
  },
  {
    label: "🎮 Level up & succès magique",
    prompt: "Retro 8-bit sparkling chime fanfare celebrating victory and level progression with bright melodic tones",
    category: "games",
    duration: 2.0,
  },
  {
    label: "🗡️ Dégainement d'épée métallique",
    prompt: "Sharp steel blade sword quickly drawn from a leather scabbard with metallic ringing chime",
    category: "cinema",
    duration: 1.5,
  },
  {
    label: "🔥 Feu de camp crépitant",
    prompt: "Cozy campfire burning gently with wood sparks snapping, crackling embers and warm air whoosh",
    category: "nature",
    duration: 5.0,
  },
  {
    label: "👣 Pas sur gravier la nuit",
    prompt: "Slow deliberate footsteps crunching on loose gravel pathway in the dead of cold night",
    category: "horror",
    duration: 3.5,
  },
  {
    label: "🕰️ Tic-tac d'horloge ancienne",
    prompt: "Rhythmic mechanical antique pendulum clock ticking steadily in a quiet empty room",
    category: "daily",
    duration: 4.0,
  },
  {
    label: "🌊 Vagues sur galets",
    prompt: "Rhythmic ocean waves crashing onto pebble beach with water receding through smooth stones",
    category: "nature",
    duration: 5.0,
  },
];

const SOUND_FORMATS = [
  { id: "mp3_44100_128", name: "MP3 44.1 kHz (128 kbps — Recommandé)", badge: "Standard" },
  { id: "mp3_44100_192", name: "MP3 44.1 kHz (192 kbps — Haute fidélité)", badge: "HD" },
  { id: "mp3_44100_96", name: "MP3 44.1 kHz (96 kbps — Léger)", badge: "Compact" },
  { id: "pcm_44100", name: "WAV / PCM 44.1 kHz (Non compressé)", badge: "Studio" },
];

const DURATION_PRESETS = [
  { value: 0, label: "Auto (IA)" },
  { value: 1.5, label: "1.5s" },
  { value: 3.0, label: "3s" },
  { value: 5.0, label: "5s" },
  { value: 10.0, label: "10s" },
  { value: 15.0, label: "15s" },
  { value: 20.0, label: "20s" },
];

function formatTime(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return "00:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} Mo`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/**
 * Custom Audio Player component with play/pause, time scrub, animated sound wave and volume.
 */
function SoundPlayer({
  url,
  filename,
  loop = false,
  autoPlay = false,
}: {
  url: string;
  filename?: string;
  loop?: boolean;
  autoPlay?: boolean;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;

    const onTimeUpdate = () => setCurrentTime(el.currentTime);
    const onLoadedMetadata = () => setDuration(el.duration || 0);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => {
      setIsPlaying(false);
      setCurrentTime(0);
    };

    el.addEventListener("timeupdate", onTimeUpdate);
    el.addEventListener("loadedmetadata", onLoadedMetadata);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);

    return () => {
      el.removeEventListener("timeupdate", onTimeUpdate);
      el.removeEventListener("loadedmetadata", onLoadedMetadata);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
    };
  }, [url]);

  function togglePlay() {
    const el = audioRef.current;
    if (!el) return;
    if (isPlaying) {
      el.pause();
    } else {
      void el.play();
    }
  }

  function handleSeek(e: React.ChangeEvent<HTMLInputElement>) {
    const el = audioRef.current;
    if (!el) return;
    const target = parseFloat(e.target.value);
    el.currentTime = target;
    setCurrentTime(target);
  }

  function toggleMute() {
    const el = audioRef.current;
    if (!el) return;
    el.muted = !el.muted;
    setIsMuted(el.muted);
  }

  return (
    <div className="sound-player-widget">
      <audio ref={audioRef} src={url} loop={loop} autoPlay={autoPlay} preload="metadata" />
      <button
        type="button"
        className={`sound-player-play-btn ${isPlaying ? "is-playing" : ""}`}
        onClick={togglePlay}
        aria-label={isPlaying ? "Mettre en pause" : "Écouter l'effet sonore"}
        title={isPlaying ? "Pause" : "Lecture"}
      >
        {isPlaying ? <Pause size={17} /> : <Play size={17} style={{ marginLeft: "2px" }} />}
      </button>

      {/* Animated Sound Wave Bars */}
      <div className={`sound-player-wave ${isPlaying ? "is-active" : ""}`} aria-hidden="true">
        <span className="wave-bar bar-1" />
        <span className="wave-bar bar-2" />
        <span className="wave-bar bar-3" />
        <span className="wave-bar bar-4" />
        <span className="wave-bar bar-5" />
        <span className="wave-bar bar-6" />
      </div>

      {/* Scrub bar & Time */}
      <div className="sound-player-scrub-wrap">
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.05}
          value={currentTime}
          onChange={handleSeek}
          className="sound-player-slider"
          aria-label="Position audio"
        />
        <div className="sound-player-times">
          <span>{formatTime(currentTime)}</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>

      <button
        type="button"
        className="sound-player-mute-btn"
        onClick={toggleMute}
        title={isMuted ? "Rétablir le son" : "Couper le son"}
      >
        {isMuted ? <VolumeX size={15} /> : <Volume2 size={15} />}
      </button>
    </div>
  );
}

export function SoundStudioModal({
  config,
  initialPrompt = "",
  onClose,
  onSendToChat,
}: SoundStudioModalProps) {
  const [tab, setTab] = useState<"studio" | "library">("studio");
  const [sounds, setSounds] = useState<GeneratedSound[]>([]);
  const [loadingSounds, setLoadingSounds] = useState(false);
  const [prompt, setPrompt] = useState(initialPrompt);
  const [previousPrompt, setPreviousPrompt] = useState<string | null>(null);
  const [styleCategory, setStyleCategory] = useState<SoundCategory>("all");
  const [styleKeywords, setStyleKeywords] = useState("");

  // Audio parameters
  const [durationMode, setDurationMode] = useState<"auto" | "manual">("auto");
  const [durationSeconds, setDurationSeconds] = useState(3.0);
  const [promptInfluence, setPromptInfluence] = useState(0.3);
  const [outputFormat, setOutputFormat] = useState("mp3_44100_128");
  const [loop, setLoop] = useState(false);

  // States
  const [busy, setBusy] = useState<"improve" | "translate" | "generate" | "delete" | null>(null);
  const [error, setError] = useState("");
  const [currentSound, setCurrentSound] = useState<GeneratedSound | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState("");

  const promptRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    void loadSounds();
  }, []);

  async function loadSounds() {
    setLoadingSounds(true);
    try {
      const data = await fetchGeneratedSounds();
      setSounds(data);
      if (data.length > 0 && !currentSound) {
        setCurrentSound(data[0]);
      }
    } catch {
      // silently ignore initial list load error
    } finally {
      setLoadingSounds(false);
    }
  }

  async function handleImprovePrompt() {
    if (!prompt.trim() || busy) return;
    setError("");
    setBusy("improve");
    try {
      const res = await improveSoundPrompt({
        prompt: prompt.trim(),
        style_keywords: styleKeywords.trim() || undefined,
        duration_hint: durationMode === "manual" ? durationSeconds : undefined,
        loop,
      });
      if (res.prompt && res.prompt.trim()) {
        setPreviousPrompt(prompt);
        setPrompt(res.prompt.trim());
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleTranslatePrompt() {
    if (!prompt.trim() || busy) return;
    setError("");
    setBusy("translate");
    try {
      const res = await translateSoundPrompt({
        prompt: prompt.trim(),
      });
      if (res.prompt && res.prompt.trim()) {
        setPreviousPrompt(prompt);
        setPrompt(res.prompt.trim());
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function handleRevertPrompt() {
    if (previousPrompt) {
      setPrompt(previousPrompt);
      setPreviousPrompt(null);
    }
  }

  async function handleGenerate(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!prompt.trim() || busy) return;

    setError("");
    setBusy("generate");
    try {
      const created = await createGeneratedSound({
        prompt: prompt.trim(),
        duration_seconds: durationMode === "manual" ? durationSeconds : null,
        prompt_influence: promptInfluence,
        output_format: outputFormat,
        loop,
      });
      setSounds(prev => [created, ...prev]);
      setCurrentSound(created);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleDelete(soundId: string) {
    if (busy) return;
    setError("");
    setBusy("delete");
    try {
      await deleteGeneratedSound(soundId);
      setSounds(prev => prev.filter(s => s.id !== soundId));
      if (currentSound?.id === soundId) {
        setCurrentSound(null);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function handleCopyPrompt(text: string, id: string) {
    void navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function applyPreset(item: typeof SUGGESTED_SOUNDS[number]) {
    setPrompt(item.prompt);
    setDurationMode("manual");
    setDurationSeconds(item.duration);
    promptRef.current?.focus();
  }

  const filteredPresets = styleCategory === "all"
    ? SUGGESTED_SOUNDS
    : SUGGESTED_SOUNDS.filter(s => s.category === styleCategory);

  const filteredLibrary = sounds.filter(s =>
    s.prompt.toLowerCase().includes(searchFilter.toLowerCase()) ||
    s.filename.toLowerCase().includes(searchFilter.toLowerCase())
  );

  return (
    <div className="sound-studio-backdrop" onClick={onClose}>
      <div
        className="sound-studio-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Studio Effets Sonores ElevenLabs"
        onClick={e => e.stopPropagation()}
      >
        {/* En-tête */}
        <header className="sound-studio-header">
          <div className="sound-studio-title-group">
            <div className="sound-studio-icon-badge">
              <AudioWaveform size={20} />
            </div>
            <div>
              <div className="sound-studio-title-row">
                <h2>Effets Sonores & Bruitages</h2>
                <span className="sound-studio-provider-badge">ElevenLabs API</span>
              </div>
              <p className="sound-studio-subtitle">
                Génération de bruitages sur-mesure de haute précision par intelligence artificielle
              </p>
            </div>
          </div>
          <div className="sound-studio-header-actions">
            <button
              type="button"
              className="sound-studio-close-btn"
              onClick={onClose}
              aria-label="Fermer le studio"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* Navigation Onglets */}
        <div className="sound-studio-tabs">
          <button
            type="button"
            className={`sound-studio-tab ${tab === "studio" ? "is-active" : ""}`}
            onClick={() => setTab("studio")}
          >
            <Sparkles size={16} />
            <span>Studio Bruitages</span>
          </button>
          <button
            type="button"
            className={`sound-studio-tab ${tab === "library" ? "is-active" : ""}`}
            onClick={() => setTab("library")}
          >
            <Volume2 size={16} />
            <span>Mes Bruitages</span>
            <span className="sound-studio-tab-count">{sounds.length}</span>
          </button>
        </div>

        {error && (
          <div className="sound-studio-alert error">
            <CircleAlert size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Corps modal : Onglet Studio */}
        {tab === "studio" && (
          <div className="sound-studio-body">
            <form onSubmit={handleGenerate} className="sound-studio-form">
              {/* Zone Prompt */}
              <div className="sound-studio-prompt-box">
                <div className="sound-studio-prompt-header">
                  <label htmlFor="sound-prompt-input" className="sound-studio-label">
                    Description du son ou bruitage
                  </label>
                  <div className="sound-studio-prompt-actions">
                    {previousPrompt && (
                      <button
                        type="button"
                        className="sound-studio-btn-revert"
                        onClick={handleRevertPrompt}
                        disabled={busy !== null}
                        title="Revenir à la formulation avant amélioration"
                      >
                        <RotateCcw size={12} />
                        <span>Revenir à l’original</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="sound-studio-btn-translate"
                      onClick={handleTranslatePrompt}
                      disabled={busy !== null || !prompt.trim()}
                      title="Traduire directement la description en anglais audio pour ElevenLabs"
                    >
                      {busy === "translate" ? (
                        <LoaderCircle size={13} className="spin" />
                      ) : (
                        <Languages size={13} />
                      )}
                      <span>Traduire en anglais</span>
                    </button>
                    <button
                      type="button"
                      className="sound-studio-btn-improve"
                      onClick={handleImprovePrompt}
                      disabled={busy !== null || !prompt.trim()}
                      title="Enrichir, sublimer et traduire le prompt sonore en anglais par IA pour ElevenLabs"
                    >
                      {busy === "improve" ? (
                        <LoaderCircle size={13} className="spin" />
                      ) : (
                        <WandSparkles size={13} />
                      )}
                      <span>Améliorer le prompt</span>
                    </button>
                    <span className={`sound-prompt-counter ${prompt.length > 400 ? "is-warning" : ""}`}>
                      {prompt.length} / 450
                    </span>
                  </div>
                </div>

                <textarea
                  id="sound-prompt-input"
                  ref={promptRef}
                  className="sound-studio-textarea"
                  rows={3}
                  maxLength={450}
                  placeholder="Ex : Épée laser s'allumant avec bourdonnement d'énergie pure, ou orage nocturne grondant au loin avec pluie battante..."
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  disabled={busy === "generate"}
                />

                <div className="sound-studio-lang-hint">
                  <Languages size={13} />
                  <span>
                    <strong>Optimisation anglaise :</strong> ElevenLabs exige l&apos;anglais pour une fidélité acoustique optimale. Vos prompts en français sont automatiquement traduits en anglais audio avant la génération.
                  </span>
                </div>

                {/* Suggestions rapides de styles */}
                <div className="sound-studio-suggestions-row">
                  <span className="sound-suggestions-title">Inspirations :</span>
                  <div className="sound-suggestions-scroll">
                    {filteredPresets.map(preset => (
                      <button
                        key={preset.label}
                        type="button"
                        className="sound-preset-chip"
                        onClick={() => applyPreset(preset)}
                        title={preset.prompt}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Paramètres Acoustiques */}
              <div className="sound-studio-settings-grid">
                {/* 1. Durée */}
                <div className="sound-setting-card">
                  <div className="sound-setting-header">
                    <span className="sound-setting-title">⏱️ Durée du bruitage</span>
                    <div className="sound-duration-toggle">
                      <button
                        type="button"
                        className={`sound-pill-btn ${durationMode === "auto" ? "is-active" : ""}`}
                        onClick={() => setDurationMode("auto")}
                      >
                        Auto (IA)
                      </button>
                      <button
                        type="button"
                        className={`sound-pill-btn ${durationMode === "manual" ? "is-active" : ""}`}
                        onClick={() => setDurationMode("manual")}
                      >
                        Manuelle
                      </button>
                    </div>
                  </div>

                  {durationMode === "manual" ? (
                    <div className="sound-duration-slider-wrap">
                      <div className="sound-slider-row">
                        <input
                          type="range"
                          min={0.5}
                          max={30.0}
                          step={0.5}
                          value={durationSeconds}
                          onChange={e => setDurationSeconds(parseFloat(e.target.value))}
                          className="sound-studio-slider"
                        />
                        <span className="sound-slider-value">{durationSeconds.toFixed(1)} s</span>
                      </div>
                      <div className="sound-preset-durations">
                        {DURATION_PRESETS.slice(1).map(p => (
                          <button
                            key={p.value}
                            type="button"
                            className={`sound-duration-chip ${durationSeconds === p.value ? "is-selected" : ""}`}
                            onClick={() => setDurationSeconds(p.value)}
                          >
                            {p.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="sound-setting-desc">
                      L&apos;IA ElevenLabs détermine automatiquement la durée idéale selon la nature de l&apos;action sonore décrite.
                    </p>
                  )}
                </div>

                {/* 2. Format & Qualité */}
                <div className="sound-setting-card">
                  <span className="sound-setting-title">🎵 Format & Qualité audio</span>
                  <select
                    className="sound-studio-select"
                    value={outputFormat}
                    onChange={e => setOutputFormat(e.target.value)}
                  >
                    {SOUND_FORMATS.map(f => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                  <p className="sound-setting-desc">
                    MP3 128 kbps offre un compromis optimal entre clarté audio et légèreté de chargement.
                  </p>
                </div>

                {/* 3. Fidélité au prompt */}
                <div className="sound-setting-card">
                  <div className="sound-setting-header">
                    <span className="sound-setting-title">🎯 Fidélité au prompt</span>
                    <span className="sound-slider-value">{promptInfluence.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={0.0}
                    max={1.0}
                    step={0.05}
                    value={promptInfluence}
                    onChange={e => setPromptInfluence(parseFloat(e.target.value))}
                    className="sound-studio-slider"
                  />
                  <div className="sound-slider-hints">
                    <span>Créatif (0.1)</span>
                    <span>Équilibré (0.3)</span>
                    <span>Strict (0.8)</span>
                  </div>
                </div>

                {/* 4. Boucle fluide (Loop) */}
                <div className="sound-setting-card sound-loop-card">
                  <label className="sound-loop-label">
                    <input
                      type="checkbox"
                      checked={loop}
                      onChange={e => setLoop(e.target.checked)}
                      className="sound-checkbox"
                    />
                    <div>
                      <span className="sound-loop-title">🔁 Boucle audio continue (Loop)</span>
                      <p className="sound-setting-desc">
                        Idéal pour ambiances immersives (pluie, vent, drones, rivières) qui tournent sans coupure.
                      </p>
                    </div>
                  </label>
                </div>
              </div>

              {/* Bouton Générer */}
              <div className="sound-studio-submit-bar">
                <button
                  type="submit"
                  className="sound-studio-generate-btn"
                  disabled={busy !== null || !prompt.trim()}
                >
                  {busy === "generate" ? (
                    <>
                      <LoaderCircle size={18} className="spin" />
                      <span>Synthèse audio ElevenLabs en cours…</span>
                    </>
                  ) : (
                    <>
                      <AudioWaveform size={18} />
                      <span>Générer l’effet sonore</span>
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Lecteur du dernier son généré */}
            {currentSound && (
              <div className="sound-result-card">
                <div className="sound-result-header">
                  <div className="sound-result-title-box">
                    <span className="sound-result-badge">Dernier son généré</span>
                    <h3 className="sound-result-prompt">{currentSound.prompt}</h3>
                    {currentSound.english_prompt && currentSound.english_prompt !== currentSound.prompt && (
                      <div className="sound-result-english-box">
                        <span className="sound-result-english-tag">Envoyé en anglais à ElevenLabs :</span>
                        <span className="sound-result-english-text">{currentSound.english_prompt}</span>
                      </div>
                    )}
                  </div>
                  <div className="sound-result-meta-chips">
                    {currentSound.duration_seconds && (
                      <span className="sound-meta-chip">⏱️ {currentSound.duration_seconds.toFixed(1)} s</span>
                    )}
                    <span className="sound-meta-chip">📦 {formatFileSize(currentSound.size)}</span>
                    <span className="sound-meta-chip">🎧 {currentSound.output_format}</span>
                  </div>
                </div>

                <SoundPlayer
                  url={currentSound.url}
                  filename={currentSound.filename}
                  loop={currentSound.loop}
                  autoPlay={false}
                />

                <div className="sound-result-actions">
                  <a
                    href={currentSound.download_url}
                    download={currentSound.filename}
                    className="sound-action-btn"
                    title="Télécharger le fichier audio"
                  >
                    <Download size={14} />
                    <span>Télécharger ({currentSound.filename.endsWith(".wav") ? ".wav" : ".mp3"})</span>
                  </a>
                  <button
                    type="button"
                    className="sound-action-btn"
                    onClick={() => handleCopyPrompt(currentSound.prompt, currentSound.id)}
                    title="Copier le prompt du son"
                  >
                    {copiedId === currentSound.id ? <Check size={14} /> : <Copy size={14} />}
                    <span>{copiedId === currentSound.id ? "Copié !" : "Copier la description"}</span>
                  </button>
                  {onSendToChat && (
                    <button
                      type="button"
                      className="sound-action-btn is-highlight"
                      onClick={() => onSendToChat(currentSound)}
                      title="Partager ce son dans la discussion en cours"
                    >
                      <Volume2 size={14} />
                      <span>Insérer dans le tchat</span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Corps modal : Onglet Bibliothèque */}
        {tab === "library" && (
          <div className="sound-library-body">
            <div className="sound-library-toolbar">
              <div className="sound-search-wrap">
                <Search size={15} className="sound-search-icon" />
                <input
                  type="text"
                  placeholder="Rechercher parmi vos effets sonores générés…"
                  value={searchFilter}
                  onChange={e => setSearchFilter(e.target.value)}
                  className="sound-search-input"
                />
                {searchFilter && (
                  <button
                    type="button"
                    className="sound-search-clear"
                    onClick={() => setSearchFilter("")}
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
              <span className="sound-library-count">
                {filteredLibrary.length} bruitage{filteredLibrary.length > 1 ? "s" : ""}
              </span>
            </div>

            {loadingSounds ? (
              <div className="sound-library-loading">
                <LoaderCircle size={24} className="spin" />
                <span>Chargement de votre audiothèque…</span>
              </div>
            ) : filteredLibrary.length === 0 ? (
              <div className="sound-library-empty">
                <div className="sound-empty-icon">
                  <Volume2 size={36} />
                </div>
                <h3>Aucun effet sonore {searchFilter ? "correspondant" : "pour le moment"}</h3>
                <p>
                  {searchFilter
                    ? "Essayez une autre recherche ou réinitialisez le filtre."
                    : "Créez votre premier bruitage personnalisé grâce au Studio ci-dessus !"}
                </p>
                {!searchFilter && (
                  <button
                    type="button"
                    className="sound-studio-btn-primary"
                    onClick={() => setTab("studio")}
                  >
                    <Sparkles size={15} />
                    <span>Créer un effet sonore</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="sound-library-grid">
                {filteredLibrary.map(sound => (
                  <div key={sound.id} className="sound-card">
                    <div className="sound-card-header">
                      <div className="sound-card-title-row">
                        <span className="sound-card-date">{formatDate(sound.created_at)}</span>
                        {sound.loop && <span className="sound-card-badge-loop">🔁 Boucle</span>}
                      </div>
                      <p className="sound-card-prompt" title={sound.prompt}>
                        {sound.prompt}
                      </p>
                    </div>

                    <SoundPlayer
                      url={sound.url}
                      filename={sound.filename}
                      loop={sound.loop}
                    />

                    <div className="sound-card-footer">
                      <div className="sound-card-meta">
                        {sound.duration_seconds && <span>⏱️ {sound.duration_seconds.toFixed(1)}s</span>}
                        <span>📦 {formatFileSize(sound.size)}</span>
                      </div>
                      <div className="sound-card-actions">
                        <a
                          href={sound.download_url}
                          download={sound.filename}
                          className="sound-card-btn"
                          title="Télécharger l'effet sonore"
                        >
                          <Download size={14} />
                        </a>
                        <button
                          type="button"
                          className="sound-card-btn"
                          onClick={() => handleCopyPrompt(sound.prompt, sound.id)}
                          title="Copier la description"
                        >
                          {copiedId === sound.id ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                        {onSendToChat && (
                          <button
                            type="button"
                            className="sound-card-btn is-highlight"
                            onClick={() => onSendToChat(sound)}
                            title="Insérer dans le tchat"
                          >
                            <Volume2 size={14} />
                          </button>
                        )}
                        <button
                          type="button"
                          className="sound-card-btn is-danger"
                          onClick={() => handleDelete(sound.id)}
                          title="Supprimer définitivement ce son"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

