"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  AudioWaveform, Check, CircleAlert, Copy, Download, ExternalLink, Languages,
  LoaderCircle, Mic, Music, Music2, Pause, Play, Radio, RotateCcw, Search,
  Sparkles, Trash2, Volume2, VolumeX, WandSparkles, X
} from "lucide-react";
import {
  api, errorMessage, type Config, type GeneratedSound,
  createGeneratedSound, fetchGeneratedSounds, improveSoundPrompt, translateSoundPrompt, deleteGeneratedSound
} from "@/lib/api";

type SoundStudioModalProps = {
  config: Config | null;
  initialPrompt?: string;
  initialTab?: "effects" | "music" | "library";
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

type MusicCategory = "all" | "cinema" | "lofi" | "synthwave" | "jazz" | "rock" | "electro" | "zen" | "classical" | "hiphop";

const MUSIC_CATEGORIES: { id: MusicCategory; label: string }[] = [
  { id: "all", label: "Tous les genres" },
  { id: "cinema", label: "🎬 Bande originale & Épique" },
  { id: "lofi", label: "🎧 Lo-Fi Chill & Détente" },
  { id: "synthwave", label: "🕹️ Synthwave & Rétro 80s" },
  { id: "jazz", label: "🎹 Jazz Lounge & Piano" },
  { id: "rock", label: "🎸 Rock & Guitares" },
  { id: "electro", label: "⚡ Électro & Dance" },
  { id: "zen", label: "🌿 Méditation & Ambiant" },
  { id: "classical", label: "🎻 Néoclassique & Cordes" },
  { id: "hiphop", label: "🥁 Hip-Hop & Trap" },
];

const SUGGESTED_MUSIC: { label: string; prompt: string; category: MusicCategory; duration: number; instrumental: boolean }[] = [
  {
    label: "🎬 Épopée symphonique de film",
    prompt: "Epic cinematic orchestral track with dramatic ostinato strings, brass swells, heavy taiko drums and soaring French horn melody",
    category: "cinema",
    duration: 60,
    instrumental: true,
  },
  {
    label: "🎧 Lo-Fi Chillhop d'étude",
    prompt: "Mellow lo-fi chillhop beat with dusty Rhodes electric piano chords, soft warm sub bass, crackling vinyl atmosphere and relaxed jazzy groove",
    category: "lofi",
    duration: 45,
    instrumental: true,
  },
  {
    label: "🕹️ Cyberpunk Synthwave 80s",
    prompt: "High-energy 80s retro synthwave with pulsing analog bassline, neon synth arpeggios, gated reverb drums and futuristic driving pace",
    category: "synthwave",
    duration: 45,
    instrumental: true,
  },
  {
    label: "🎹 Jazz Lounge feutré",
    prompt: "Smooth midnight jazz lounge ballad featuring delicate acoustic grand piano improvisation, gentle brushed drums and warm upright double bass",
    category: "jazz",
    duration: 60,
    instrumental: true,
  },
  {
    label: "🎸 Folk acoustique & Guitare",
    prompt: "Warm acoustic indie folk track with fingerpicked steel-string guitars, rustic cello accompaniment and gentle stomping wooden percussion",
    category: "rock",
    duration: 45,
    instrumental: true,
  },
  {
    label: "⚡ Deep House mélodique",
    prompt: "Euphoric melodic deep house groove at 124 BPM with bouncy sub bass, atmospheric vocal chops, shimmering synth plucks and punchy four-on-the-floor kick",
    category: "electro",
    duration: 60,
    instrumental: true,
  },
  {
    label: "🌿 Méditation & Bols tibétains",
    prompt: "Tranquil ambient meditation soundscape with singing bowls, soft ethereal drone pads, gentle bamboo wind chimes and distant mountain breeze",
    category: "zen",
    duration: 60,
    instrumental: true,
  },
  {
    label: "🎻 Adagio néoclassique poignant",
    prompt: "Deeply emotional neoclassical adagio with expressive solo cello, minimalist grand piano chords and tender soaring string quartet swell",
    category: "classical",
    duration: 60,
    instrumental: true,
  },
  {
    label: "🥁 Trap atmosphérique moderne",
    prompt: "Dark ambient trap instrumental featuring heavy gliding 808 sub bass, crisp rolling hi-hats, mysterious bell melodies and spaced-out reverb",
    category: "hiphop",
    duration: 45,
    instrumental: true,
  },
  {
    label: "🎤 Pop Indie lumineuse (Avec chant)",
    prompt: "Catchy indie pop song with uplifting acoustic guitar, bright melodic synth hooks, punchy drums and sweet expressive female vocals singing about summer road trips",
    category: "rock",
    duration: 60,
    instrumental: false,
  },
];

const SOUND_FORMATS = [
  { id: "mp3_44100_128", name: "MP3 44.1 kHz (128 kbps — Recommandé)", badge: "Standard" },
  { id: "mp3_44100_192", name: "MP3 44.1 kHz (192 kbps — Haute fidélité)", badge: "HD" },
  { id: "mp3_44100_96", name: "MP3 44.1 kHz (96 kbps — Léger)", badge: "Compact" },
  { id: "pcm_44100", name: "WAV / PCM 44.1 kHz (Non compressé)", badge: "Studio" },
];

const MUSIC_MODELS = [
  { id: "music_v1", name: "Eleven Music v1 (Standard — Recommandé)", badge: "v1", desc: "Polyvalent, rapide et équilibré" },
  { id: "music_v2_5", name: "Eleven Music v2.5 (Studio — Haute fidélité)", badge: "v2.5", desc: "Arrangement dynamique et acoustique studio avancée" },
];

const SFX_DURATION_PRESETS = [
  { value: 0, label: "Auto (IA)" },
  { value: 1.5, label: "1.5s" },
  { value: 3.0, label: "3s" },
  { value: 5.0, label: "5s" },
  { value: 10.0, label: "10s" },
  { value: 15.0, label: "15s" },
  { value: 20.0, label: "20s" },
];

const MUSIC_DURATION_PRESETS = [
  { value: 0, label: "Auto (IA)" },
  { value: 15, label: "15s" },
  { value: 30, label: "30s" },
  { value: 45, label: "45s" },
  { value: 60, label: "1 min" },
  { value: 90, label: "1:30" },
  { value: 120, label: "2 min" },
  { value: 180, label: "3 min" },
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
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// Mini-lecteur audio réactif avec onde visuelle
function SoundPlayer({
  url,
  filename,
  loop = false,
  autoPlay = false,
}: {
  url: string;
  filename: string;
  loop?: boolean;
  autoPlay?: boolean;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.85);
  const [isMuted, setIsMuted] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onTimeUpdate = () => setCurrentTime(audio.currentTime);
    const onLoadedMetadata = () => {
      setDuration(audio.duration || 0);
      if (autoPlay) {
        audio.play().catch(() => {});
      }
    };
    const onEnded = () => {
      if (!loop) {
        setIsPlaying(false);
        setCurrentTime(0);
      }
    };

    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("ended", onEnded);

    return () => {
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("ended", onEnded);
    };
  }, [autoPlay, loop]);

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
    } else {
      audio.play().catch(() => {});
    }
  }

  function handleSeek(e: React.ChangeEvent<HTMLInputElement>) {
    const audio = audioRef.current;
    if (!audio) return;
    const time = parseFloat(e.target.value);
    audio.currentTime = time;
    setCurrentTime(time);
  }

  function handleVolume(e: React.ChangeEvent<HTMLInputElement>) {
    const audio = audioRef.current;
    if (!audio) return;
    const vol = parseFloat(e.target.value);
    audio.volume = vol;
    setVolume(vol);
    setIsMuted(vol === 0);
  }

  function toggleMute() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isMuted) {
      audio.volume = volume > 0 ? volume : 0.85;
      setIsMuted(false);
    } else {
      audio.volume = 0;
      setIsMuted(true);
    }
  }

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="sound-player-wrap">
      <audio ref={audioRef} src={url} loop={loop} preload="metadata" />

      <button
        type="button"
        className={`sound-player-toggle ${isPlaying ? "is-playing" : ""}`}
        onClick={togglePlay}
        aria-label={isPlaying ? "Mettre en pause" : "Écouter l'extrait audio"}
        title={isPlaying ? "Pause" : "Lecture"}
      >
        {isPlaying ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" className="ml-0.5" />}
      </button>

      {/* Visualiseur ondes animées */}
      <div className="sound-wave-bars" aria-hidden="true">
        {[40, 75, 55, 95, 60, 85, 30, 90, 65, 45, 80, 50, 70, 90, 35, 60].map((h, i) => (
          <span
            key={i}
            className={`sound-wave-bar ${isPlaying ? "is-animating" : ""}`}
            style={{
              height: isPlaying ? `${Math.max(15, h)}%` : "20%",
              animationDelay: `${(i * 0.08).toFixed(2)}s`,
            }}
          />
        ))}
      </div>

      {/* Curseur temporel */}
      <div className="sound-player-progress-area">
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={currentTime}
          onChange={handleSeek}
          className="sound-player-slider"
          aria-label="Position de lecture"
        />
        <div className="sound-player-time">
          <span>{formatTime(currentTime)}</span>
          <span>/</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>

      {/* Volume */}
      <div className="sound-player-volume-wrap">
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={isMuted ? 0 : volume}
          onChange={handleVolume}
          className="sound-volume-slider"
          aria-label="Volume audio"
          title={`Volume : ${Math.round((isMuted ? 0 : volume) * 100)}%`}
        />
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
  initialTab = "effects",
  onClose,
  onSendToChat,
}: SoundStudioModalProps) {
  const [tab, setTab] = useState<"effects" | "music" | "library">(initialTab);
  const [sounds, setSounds] = useState<GeneratedSound[]>([]);
  const [loadingSounds, setLoadingSounds] = useState(false);

  // Sound Effects state
  const [sfxPrompt, setSfxPrompt] = useState(initialPrompt);
  const [sfxPreviousPrompt, setSfxPreviousPrompt] = useState<string | null>(null);
  const [sfxCategory, setSfxCategory] = useState<SoundCategory>("all");
  const [sfxDurationMode, setSfxDurationMode] = useState<"auto" | "manual">("auto");
  const [sfxDurationSeconds, setSfxDurationSeconds] = useState(3.0);
  const [sfxPromptInfluence, setSfxPromptInfluence] = useState(0.3);
  const [sfxOutputFormat, setSfxOutputFormat] = useState("mp3_44100_128");
  const [sfxLoop, setSfxLoop] = useState(false);

  // Music state
  const [musicPrompt, setMusicPrompt] = useState(initialPrompt);
  const [musicPreviousPrompt, setMusicPreviousPrompt] = useState<string | null>(null);
  const [musicCategory, setMusicCategory] = useState<MusicCategory>("all");
  const [musicInstrumental, setMusicInstrumental] = useState(true);
  const [musicModelId, setMusicModelId] = useState("music_v1");
  const [musicDurationMode, setMusicDurationMode] = useState<"auto" | "manual">("manual");
  const [musicDurationSeconds, setMusicDurationSeconds] = useState(45);
  const [musicOutputFormat, setMusicOutputFormat] = useState("mp3_44100_128");

  // Global states
  const [busy, setBusy] = useState<"improve" | "translate" | "generate" | "delete" | null>(null);
  const [error, setError] = useState("");
  const [currentSound, setCurrentSound] = useState<GeneratedSound | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [libraryFilter, setLibraryFilter] = useState<"all" | "effects" | "music">("all");
  const [searchFilter, setSearchFilter] = useState("");

  const sfxPromptRef = useRef<HTMLTextAreaElement>(null);
  const musicPromptRef = useRef<HTMLTextAreaElement>(null);

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

  // --- Sound Effects Actions ---
  async function handleImproveSfxPrompt() {
    if (!sfxPrompt.trim() || busy) return;
    setError("");
    setBusy("improve");
    try {
      const res = await improveSoundPrompt({
        prompt: sfxPrompt.trim(),
        sound_type: "sound_effect",
        duration_hint: sfxDurationMode === "manual" ? sfxDurationSeconds : undefined,
        loop: sfxLoop,
      });
      if (res.prompt && res.prompt.trim()) {
        setSfxPreviousPrompt(sfxPrompt);
        setSfxPrompt(res.prompt.trim());
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleTranslateSfxPrompt() {
    if (!sfxPrompt.trim() || busy) return;
    setError("");
    setBusy("translate");
    try {
      const res = await translateSoundPrompt({
        prompt: sfxPrompt.trim(),
        sound_type: "sound_effect",
      });
      if (res.prompt && res.prompt.trim()) {
        setSfxPreviousPrompt(sfxPrompt);
        setSfxPrompt(res.prompt.trim());
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function handleRevertSfxPrompt() {
    if (sfxPreviousPrompt) {
      setSfxPrompt(sfxPreviousPrompt);
      setSfxPreviousPrompt(null);
    }
  }

  async function handleGenerateSfx(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!sfxPrompt.trim() || busy) return;

    setError("");
    setBusy("generate");
    try {
      const created = await createGeneratedSound({
        prompt: sfxPrompt.trim(),
        sound_type: "sound_effect",
        duration_seconds: sfxDurationMode === "manual" ? sfxDurationSeconds : null,
        prompt_influence: sfxPromptInfluence,
        output_format: sfxOutputFormat,
        loop: sfxLoop,
      });
      setSounds(prev => [created, ...prev]);
      setCurrentSound(created);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function applySfxPreset(item: typeof SUGGESTED_SOUNDS[number]) {
    setSfxPrompt(item.prompt);
    setSfxDurationMode("manual");
    setSfxDurationSeconds(item.duration);
    sfxPromptRef.current?.focus();
  }

  // --- Music Actions ---
  async function handleImproveMusicPrompt() {
    if (!musicPrompt.trim() || busy) return;
    setError("");
    setBusy("improve");
    try {
      const res = await improveSoundPrompt({
        prompt: musicPrompt.trim(),
        sound_type: "music",
        instrumental: musicInstrumental,
        duration_hint: musicDurationMode === "manual" ? musicDurationSeconds : undefined,
      });
      if (res.prompt && res.prompt.trim()) {
        setMusicPreviousPrompt(musicPrompt);
        setMusicPrompt(res.prompt.trim());
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleTranslateMusicPrompt() {
    if (!musicPrompt.trim() || busy) return;
    setError("");
    setBusy("translate");
    try {
      const res = await translateSoundPrompt({
        prompt: musicPrompt.trim(),
        sound_type: "music",
      });
      if (res.prompt && res.prompt.trim()) {
        setMusicPreviousPrompt(musicPrompt);
        setMusicPrompt(res.prompt.trim());
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function handleRevertMusicPrompt() {
    if (musicPreviousPrompt) {
      setMusicPrompt(musicPreviousPrompt);
      setMusicPreviousPrompt(null);
    }
  }

  async function handleGenerateMusic(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!musicPrompt.trim() || busy) return;

    setError("");
    setBusy("generate");
    try {
      const created = await createGeneratedSound({
        prompt: musicPrompt.trim(),
        sound_type: "music",
        duration_seconds: musicDurationMode === "manual" ? musicDurationSeconds : null,
        instrumental: musicInstrumental,
        model_id: musicModelId,
        output_format: musicOutputFormat,
      });
      setSounds(prev => [created, ...prev]);
      setCurrentSound(created);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function applyMusicPreset(item: typeof SUGGESTED_MUSIC[number]) {
    setMusicPrompt(item.prompt);
    setMusicDurationMode("manual");
    setMusicDurationSeconds(item.duration);
    setMusicInstrumental(item.instrumental);
    musicPromptRef.current?.focus();
  }

  // --- Common Actions ---
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

  const filteredSfxPresets = sfxCategory === "all"
    ? SUGGESTED_SOUNDS
    : SUGGESTED_SOUNDS.filter(s => s.category === sfxCategory);

  const filteredMusicPresets = musicCategory === "all"
    ? SUGGESTED_MUSIC
    : SUGGESTED_MUSIC.filter(s => s.category === musicCategory);

  const filteredLibrary = sounds.filter(s => {
    if (libraryFilter === "effects" && s.sound_type === "music") return false;
    if (libraryFilter === "music" && s.sound_type !== "music") return false;
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return s.prompt.toLowerCase().includes(q) || s.filename.toLowerCase().includes(q);
  });

  const effectsCount = sounds.filter(s => s.sound_type !== "music").length;
  const musicCount = sounds.filter(s => s.sound_type === "music").length;

  return (
    <div className="sound-studio-backdrop" onClick={onClose}>
      <div
        className="sound-studio-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Studio Audio & Musique ElevenLabs"
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
                <h2>Studio Audio & Musique IA</h2>
                <span className="sound-studio-provider-badge">ElevenLabs API</span>
                <a
                  href="https://elevenlabs.io/app/music"
                  target="_blank"
                  rel="noreferrer"
                  className="sound-studio-official-link"
                  title="Consulter l'application officielle ElevenLabs Music (ouvre dans un nouvel onglet)"
                >
                  <Music size={12} />
                  <span>ElevenLabs Music</span>
                  <ExternalLink size={11} />
                </a>
              </div>
              <p className="sound-studio-subtitle">
                Génération de bruitages réalistes et composition de musique originale assistée par IA
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
            className={`sound-studio-tab ${tab === "effects" ? "is-active" : ""}`}
            onClick={() => setTab("effects")}
          >
            <Volume2 size={16} />
            <span>Effets Sonores & Bruitages</span>
          </button>
          <button
            type="button"
            className={`sound-studio-tab sound-studio-tab-music ${tab === "music" ? "is-active" : ""}`}
            onClick={() => setTab("music")}
          >
            <Music size={16} />
            <span>Génération de Musique</span>
            <span className="sound-studio-badge-new">Eleven Music</span>
          </button>
          <button
            type="button"
            className={`sound-studio-tab ${tab === "library" ? "is-active" : ""}`}
            onClick={() => setTab("library")}
          >
            <Sparkles size={16} />
            <span>Audiothèque</span>
            <span className="sound-studio-tab-count">{sounds.length}</span>
          </button>
        </div>

        {error && (
          <div className="sound-studio-alert error">
            <CircleAlert size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* -------------------- ONGLET 1 : BRUITAGES & EFFETS SONORES -------------------- */}
        {tab === "effects" && (
          <div className="sound-studio-body">
            <form onSubmit={handleGenerateSfx} className="sound-studio-form">
              {/* Zone Prompt */}
              <div className="sound-studio-prompt-box">
                <div className="sound-studio-prompt-header">
                  <label htmlFor="sfx-prompt-input" className="sound-studio-label">
                    Description du bruitage ou effet sonore
                  </label>
                  <div className="sound-studio-prompt-actions">
                    {sfxPreviousPrompt && (
                      <button
                        type="button"
                        className="sound-studio-btn-revert"
                        onClick={handleRevertSfxPrompt}
                        disabled={busy !== null}
                        title="Revenir à la formulation avant amélioration"
                      >
                        <RotateCcw size={12} />
                        <span>Original</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="sound-studio-btn-translate"
                      onClick={handleTranslateSfxPrompt}
                      disabled={busy !== null || !sfxPrompt.trim()}
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
                      onClick={handleImproveSfxPrompt}
                      disabled={busy !== null || !sfxPrompt.trim()}
                      title="Enrichir et traduire le prompt sonore en anglais acoustique par IA"
                    >
                      {busy === "improve" ? (
                        <LoaderCircle size={13} className="spin" />
                      ) : (
                        <WandSparkles size={13} />
                      )}
                      <span>Améliorer le prompt</span>
                    </button>
                    <span className={`sound-prompt-counter ${sfxPrompt.length > 400 ? "is-warning" : ""}`}>
                      {sfxPrompt.length} / 450
                    </span>
                  </div>
                </div>

                <textarea
                  id="sfx-prompt-input"
                  ref={sfxPromptRef}
                  className="sound-studio-textarea"
                  rows={3}
                  maxLength={450}
                  placeholder="Ex : Épée laser s'allumant avec bourdonnement d'énergie pure, ou orage nocturne grondant au loin avec pluie battante..."
                  value={sfxPrompt}
                  onChange={e => setSfxPrompt(e.target.value)}
                  disabled={busy === "generate"}
                />

                <div className="sound-studio-lang-hint">
                  <Languages size={13} />
                  <span>
                    <strong>Optimisation anglaise :</strong> Le modèle Sound Effects a été entraîné en anglais. Vos demandes en français sont traduites avec précision avant l&apos;envoi.
                  </span>
                </div>

                {/* Suggestions rapides de styles */}
                <div className="sound-studio-suggestions-row">
                  <span className="sound-suggestions-title">Inspirations :</span>
                  <div className="sound-suggestions-scroll">
                    {filteredSfxPresets.map(preset => (
                      <button
                        key={preset.label}
                        type="button"
                        className="sound-preset-chip"
                        onClick={() => applySfxPreset(preset)}
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
                        className={`sound-pill-btn ${sfxDurationMode === "auto" ? "is-active" : ""}`}
                        onClick={() => setSfxDurationMode("auto")}
                      >
                        Auto (IA)
                      </button>
                      <button
                        type="button"
                        className={`sound-pill-btn ${sfxDurationMode === "manual" ? "is-active" : ""}`}
                        onClick={() => setSfxDurationMode("manual")}
                      >
                        Manuelle
                      </button>
                    </div>
                  </div>

                  {sfxDurationMode === "manual" ? (
                    <div className="sound-duration-slider-wrap">
                      <div className="sound-slider-row">
                        <input
                          type="range"
                          min={0.5}
                          max={30.0}
                          step={0.5}
                          value={sfxDurationSeconds}
                          onChange={e => setSfxDurationSeconds(parseFloat(e.target.value))}
                          className="sound-studio-slider"
                        />
                        <span className="sound-slider-value">{sfxDurationSeconds.toFixed(1)} s</span>
                      </div>
                      <div className="sound-preset-durations">
                        {SFX_DURATION_PRESETS.slice(1).map(p => (
                          <button
                            key={p.value}
                            type="button"
                            className={`sound-duration-chip ${sfxDurationSeconds === p.value ? "is-selected" : ""}`}
                            onClick={() => setSfxDurationSeconds(p.value)}
                          >
                            {p.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="sound-setting-desc">
                      L&apos;IA ElevenLabs détermine automatiquement la durée idéale selon l&apos;action sonore décrite.
                    </p>
                  )}
                </div>

                {/* 2. Format & Qualité */}
                <div className="sound-setting-card">
                  <span className="sound-setting-title">🎧 Format & Qualité audio</span>
                  <select
                    className="sound-studio-select"
                    value={sfxOutputFormat}
                    onChange={e => setSfxOutputFormat(e.target.value)}
                  >
                    {SOUND_FORMATS.map(f => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                  <p className="sound-setting-desc">
                    MP3 128 kbps offre un compromis optimal entre clarté audio et rapidité.
                  </p>
                </div>

                {/* 3. Fidélité au prompt */}
                <div className="sound-setting-card">
                  <div className="sound-setting-header">
                    <span className="sound-setting-title">🎯 Fidélité au prompt</span>
                    <span className="sound-slider-value">{sfxPromptInfluence.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={0.0}
                    max={1.0}
                    step={0.05}
                    value={sfxPromptInfluence}
                    onChange={e => setSfxPromptInfluence(parseFloat(e.target.value))}
                    className="sound-studio-slider"
                  />
                  <div className="sound-slider-hints">
                    <span>Créatif (0.1)</span>
                    <span>Équilibré (0.3)</span>
                    <span>Strict (0.8)</span>
                  </div>
                </div>

                {/* 4. Boucle fluide */}
                <div className="sound-setting-card sound-loop-card">
                  <label className="sound-loop-label">
                    <input
                      type="checkbox"
                      checked={sfxLoop}
                      onChange={e => setSfxLoop(e.target.checked)}
                      className="sound-checkbox"
                    />
                    <div>
                      <span className="sound-loop-title">🔁 Boucle audio continue (Loop)</span>
                      <p className="sound-setting-desc">
                        Idéal pour ambiances immersives (pluie, vent, drones, cascades) sans coupure.
                      </p>
                    </div>
                  </label>
                </div>
              </div>

              {/* Bouton Générer Bruitage */}
              <div className="sound-studio-submit-bar">
                <button
                  type="submit"
                  className="sound-studio-generate-btn"
                  disabled={busy !== null || !sfxPrompt.trim()}
                >
                  {busy === "generate" ? (
                    <>
                      <LoaderCircle size={18} className="spin" />
                      <span>Synthèse sonore ElevenLabs en cours…</span>
                    </>
                  ) : (
                    <>
                      <Volume2 size={18} />
                      <span>Générer l’effet sonore</span>
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Lecteur du dernier son généré */}
            {currentSound && currentSound.sound_type !== "music" && (
              <div className="sound-result-card">
                <div className="sound-result-header">
                  <div className="sound-result-title-box">
                    <span className="sound-result-badge">Dernier bruitage généré</span>
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

        {/* -------------------- ONGLET 2 : GÉNÉRATION DE MUSIQUE (ELEVEN MUSIC) -------------------- */}
        {tab === "music" && (
          <div className="sound-studio-body sound-music-body">
            {/* Bannière didactique ElevenLabs Music */}
            <div className="sound-music-banner">
              <div className="sound-music-banner-icon">
                <Music size={22} />
              </div>
              <div className="sound-music-banner-content">
                <div className="sound-music-banner-heading">
                  <h3>Composition Musicale ElevenLabs Music</h3>
                  <a
                    href="https://elevenlabs.io/app/music"
                    target="_blank"
                    rel="noreferrer"
                    className="sound-music-banner-link"
                    title="Ouvrir le studio officiel ElevenLabs Music"
                  >
                    <span>https://elevenlabs.io/app/music</span>
                    <ExternalLink size={13} />
                  </a>
                </div>
                <p>
                  Générez des morceaux de musique studio complets, avec voix mélodiques ou en pur instrumental, à partir d&apos;une description de style, instruments, rythme et ambiance.
                </p>
              </div>
            </div>

            <form onSubmit={handleGenerateMusic} className="sound-studio-form">
              {/* Zone Prompt Musique */}
              <div className="sound-studio-prompt-box sound-music-prompt-box">
                <div className="sound-studio-prompt-header">
                  <label htmlFor="music-prompt-input" className="sound-studio-label">
                    Idée musicale, genre, instruments & ambiance
                  </label>
                  <div className="sound-studio-prompt-actions">
                    {musicPreviousPrompt && (
                      <button
                        type="button"
                        className="sound-studio-btn-revert"
                        onClick={handleRevertMusicPrompt}
                        disabled={busy !== null}
                        title="Revenir à la formulation avant amélioration"
                      >
                        <RotateCcw size={12} />
                        <span>Original</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="sound-studio-btn-translate"
                      onClick={handleTranslateMusicPrompt}
                      disabled={busy !== null || !musicPrompt.trim()}
                      title="Traduire votre idée en anglais musical pour le modèle ElevenLabs"
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
                      className="sound-studio-btn-improve is-music-improve"
                      onClick={handleImproveMusicPrompt}
                      disabled={busy !== null || !musicPrompt.trim()}
                      title="Enrichir le prompt par IA avec tempo BPM, instrumentation, ambiance et structure"
                    >
                      {busy === "improve" ? (
                        <LoaderCircle size={13} className="spin" />
                      ) : (
                        <WandSparkles size={13} />
                      )}
                      <span>Améliorer le prompt musique</span>
                    </button>
                    <span className={`sound-prompt-counter ${musicPrompt.length > 3500 ? "is-warning" : ""}`}>
                      {musicPrompt.length} / 4000
                    </span>
                  </div>
                </div>

                <textarea
                  id="music-prompt-input"
                  ref={musicPromptRef}
                  className="sound-studio-textarea sound-music-textarea"
                  rows={4}
                  maxLength={4000}
                  placeholder="Ex : Bande originale épique pour bande-annonce spatiale avec cordes montantes, cors puissants, percussions lourdes et progression héroïque, 110 BPM..."
                  value={musicPrompt}
                  onChange={e => setMusicPrompt(e.target.value)}
                  disabled={busy === "generate"}
                />

                <div className="sound-studio-lang-hint">
                  <Sparkles size={13} />
                  <span>
                    <strong>Astuce composition :</strong> Précisez le genre, les instruments clés, le tempo (BPM) et l&apos;émotion. Évitez les noms d&apos;artistes protégés qu&apos;ElevenLabs bloque par sécurité.
                  </span>
                </div>

                {/* Suggestions musicales */}
                <div className="sound-studio-suggestions-row">
                  <span className="sound-suggestions-title">Styles & Inspirations :</span>
                  <div className="sound-suggestions-scroll">
                    {filteredMusicPresets.map(preset => (
                      <button
                        key={preset.label}
                        type="button"
                        className="sound-preset-chip sound-preset-chip-music"
                        onClick={() => applyMusicPreset(preset)}
                        title={preset.prompt}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Paramètres Musicaux */}
              <div className="sound-studio-settings-grid">
                {/* 1. Instrumental vs Vocal */}
                <div className="sound-setting-card sound-music-card-highlight">
                  <span className="sound-setting-title">🎤 Orientation vocale</span>
                  <div className="sound-instrumental-toggle">
                    <button
                      type="button"
                      className={`sound-instrumental-btn ${musicInstrumental ? "is-active" : ""}`}
                      onClick={() => setMusicInstrumental(true)}
                    >
                      <Radio size={15} />
                      <div className="text-left">
                        <strong>Instrumental pur</strong>
                        <small>Strictement sans voix ni paroles</small>
                      </div>
                    </button>
                    <button
                      type="button"
                      className={`sound-instrumental-btn ${!musicInstrumental ? "is-active" : ""}`}
                      onClick={() => setMusicInstrumental(false)}
                    >
                      <Mic size={15} />
                      <div className="text-left">
                        <strong>Avec voix / chant</strong>
                        <small>Chanson avec lignes vocales expressives</small>
                      </div>
                    </button>
                  </div>
                </div>

                {/* 2. Modèle ElevenLabs Music */}
                <div className="sound-setting-card">
                  <span className="sound-setting-title">🧠 Modèle Eleven Music</span>
                  <select
                    className="sound-studio-select"
                    value={musicModelId}
                    onChange={e => setMusicModelId(e.target.value)}
                  >
                    {MUSIC_MODELS.map(m => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                  <p className="sound-setting-desc">
                    {MUSIC_MODELS.find(m => m.id === musicModelId)?.desc || "Modèle IA d'orchestration ElevenLabs"}
                  </p>
                </div>

                {/* 3. Durée du morceau */}
                <div className="sound-setting-card">
                  <div className="sound-setting-header">
                    <span className="sound-setting-title">⏱️ Durée du morceau</span>
                    <div className="sound-duration-toggle">
                      <button
                        type="button"
                        className={`sound-pill-btn ${musicDurationMode === "auto" ? "is-active" : ""}`}
                        onClick={() => setMusicDurationMode("auto")}
                      >
                        Auto
                      </button>
                      <button
                        type="button"
                        className={`sound-pill-btn ${musicDurationMode === "manual" ? "is-active" : ""}`}
                        onClick={() => setMusicDurationMode("manual")}
                      >
                        {musicDurationSeconds} s
                      </button>
                    </div>
                  </div>

                  {musicDurationMode === "manual" ? (
                    <div className="sound-duration-slider-wrap">
                      <div className="sound-slider-row">
                        <input
                          type="range"
                          min={10}
                          max={300}
                          step={5}
                          value={musicDurationSeconds}
                          onChange={e => setMusicDurationSeconds(parseInt(e.target.value, 10))}
                          className="sound-studio-slider sound-music-slider"
                        />
                        <span className="sound-slider-value">
                          {musicDurationSeconds >= 60
                            ? `${Math.floor(musicDurationSeconds / 60)}m ${musicDurationSeconds % 60 ? (musicDurationSeconds % 60) + "s" : ""}`
                            : `${musicDurationSeconds} s`}
                        </span>
                      </div>
                      <div className="sound-preset-durations">
                        {MUSIC_DURATION_PRESETS.slice(1).map(p => (
                          <button
                            key={p.value}
                            type="button"
                            className={`sound-duration-chip sound-duration-chip-music ${musicDurationSeconds === p.value ? "is-selected" : ""}`}
                            onClick={() => setMusicDurationSeconds(p.value)}
                          >
                            {p.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="sound-setting-desc">
                      ElevenLabs compose automatiquement un extrait d&apos;une durée adaptée à la structure du morceau.
                    </p>
                  )}
                </div>

                {/* 4. Format & Qualité */}
                <div className="sound-setting-card">
                  <span className="sound-setting-title">🎵 Format & Résolution audio</span>
                  <select
                    className="sound-studio-select"
                    value={musicOutputFormat}
                    onChange={e => setMusicOutputFormat(e.target.value)}
                  >
                    {SOUND_FORMATS.map(f => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                  <p className="sound-setting-desc">
                    MP3 128 kbps ou 192 kbps garantissent une restitution acoustique haute fidélité.
                  </p>
                </div>
              </div>

              {/* Bouton Composer Musique */}
              <div className="sound-studio-submit-bar">
                <button
                  type="submit"
                  className="sound-studio-generate-btn sound-music-generate-btn"
                  disabled={busy !== null || !musicPrompt.trim()}
                >
                  {busy === "generate" ? (
                    <>
                      <LoaderCircle size={18} className="spin" />
                      <span>Composition musicale ElevenLabs en cours (~15-30s)…</span>
                    </>
                  ) : (
                    <>
                      <Music size={18} />
                      <span>Composer le morceau (Eleven Music)</span>
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Lecteur de la dernière musique générée */}
            {currentSound && currentSound.sound_type === "music" && (
              <div className="sound-result-card sound-music-result-card">
                <div className="sound-result-header">
                  <div className="sound-result-title-box">
                    <span className="sound-result-badge sound-result-badge-music">
                      🎵 Morceau composé avec ElevenLabs Music
                    </span>
                    <h3 className="sound-result-prompt">{currentSound.prompt}</h3>
                    {currentSound.english_prompt && currentSound.english_prompt !== currentSound.prompt && (
                      <div className="sound-result-english-box">
                        <span className="sound-result-english-tag">Prompt musical envoyé à ElevenLabs :</span>
                        <span className="sound-result-english-text">{currentSound.english_prompt}</span>
                      </div>
                    )}
                  </div>
                  <div className="sound-result-meta-chips">
                    {currentSound.duration_seconds && (
                      <span className="sound-meta-chip">⏱️ {formatTime(currentSound.duration_seconds)}</span>
                    )}
                    <span className="sound-meta-chip">
                      {currentSound.instrumental ? "🎷 Instrumental" : "🎤 Vocal / Chant"}
                    </span>
                    {currentSound.model_id && (
                      <span className="sound-meta-chip">🧠 {currentSound.model_id}</span>
                    )}
                    <span className="sound-meta-chip">📦 {formatFileSize(currentSound.size)}</span>
                  </div>
                </div>

                <SoundPlayer
                  url={currentSound.url}
                  filename={currentSound.filename}
                  loop={false}
                  autoPlay={false}
                />

                <div className="sound-result-actions">
                  <a
                    href={currentSound.download_url}
                    download={currentSound.filename}
                    className="sound-action-btn sound-music-action-btn"
                    title="Télécharger le fichier musical"
                  >
                    <Download size={14} />
                    <span>Télécharger le morceau ({currentSound.filename.endsWith(".wav") ? ".wav" : ".mp3"})</span>
                  </a>
                  <button
                    type="button"
                    className="sound-action-btn"
                    onClick={() => handleCopyPrompt(currentSound.prompt, currentSound.id)}
                    title="Copier le prompt musical"
                  >
                    {copiedId === currentSound.id ? <Check size={14} /> : <Copy size={14} />}
                    <span>{copiedId === currentSound.id ? "Copié !" : "Copier le prompt"}</span>
                  </button>
                  {onSendToChat && (
                    <button
                      type="button"
                      className="sound-action-btn is-highlight sound-music-highlight-btn"
                      onClick={() => onSendToChat(currentSound)}
                      title="Partager ce morceau dans la discussion en cours"
                    >
                      <Music size={14} />
                      <span>Insérer dans le tchat</span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* -------------------- ONGLET 3 : AUDIOTHÈQUE (BIBLIOTHÈQUE) -------------------- */}
        {tab === "library" && (
          <div className="sound-library-body">
            <div className="sound-library-toolbar">
              <div className="sound-library-filter-pills">
                <button
                  type="button"
                  className={`sound-lib-pill ${libraryFilter === "all" ? "is-active" : ""}`}
                  onClick={() => setLibraryFilter("all")}
                >
                  Tous ({sounds.length})
                </button>
                <button
                  type="button"
                  className={`sound-lib-pill ${libraryFilter === "effects" ? "is-active" : ""}`}
                  onClick={() => setLibraryFilter("effects")}
                >
                  <Volume2 size={13} />
                  <span>Bruitages ({effectsCount})</span>
                </button>
                <button
                  type="button"
                  className={`sound-lib-pill sound-lib-pill-music ${libraryFilter === "music" ? "is-active" : ""}`}
                  onClick={() => setLibraryFilter("music")}
                >
                  <Music size={13} />
                  <span>Musiques ({musicCount})</span>
                </button>
              </div>

              <div className="sound-search-wrap">
                <Search size={15} className="sound-search-icon" />
                <input
                  type="text"
                  placeholder="Rechercher parmi vos créations audio…"
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
            </div>

            {loadingSounds ? (
              <div className="sound-library-loading">
                <LoaderCircle size={24} className="spin" />
                <span>Chargement de votre audiothèque ElevenLabs…</span>
              </div>
            ) : filteredLibrary.length === 0 ? (
              <div className="sound-library-empty">
                <div className="sound-empty-icon">
                  {libraryFilter === "music" ? <Music size={36} /> : <Volume2 size={36} />}
                </div>
                <h3>
                  {searchFilter
                    ? "Aucun résultat pour cette recherche"
                    : libraryFilter === "music"
                    ? "Aucun morceau de musique pour l'instant"
                    : "Aucun son généré pour l'instant"}
                </h3>
                <p>
                  {searchFilter
                    ? "Essayez une autre recherche ou réinitialisez le filtre ci-dessus."
                    : libraryFilter === "music"
                    ? "Composez votre premier morceau musical grâce à ElevenLabs Music !"
                    : "Créez votre premier bruitage ou composition grâce aux onglets ci-dessus !"}
                </p>
                {!searchFilter && (
                  <div className="flex gap-2 justify-center mt-3">
                    <button
                      type="button"
                      className="sound-studio-btn-primary"
                      onClick={() => setTab("music")}
                    >
                      <Music size={15} />
                      <span>Composer une musique</span>
                    </button>
                    <button
                      type="button"
                      className="sound-studio-btn-primary"
                      onClick={() => setTab("effects")}
                    >
                      <Volume2 size={15} />
                      <span>Créer un effet sonore</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="sound-library-grid">
                {filteredLibrary.map(sound => {
                  const isMusic = sound.sound_type === "music";
                  return (
                    <div key={sound.id} className={`sound-card ${isMusic ? "sound-card-music" : ""}`}>
                      <div className="sound-card-header">
                        <div className="sound-card-title-row">
                          <span className={`sound-card-type-badge ${isMusic ? "is-music" : "is-sfx"}`}>
                            {isMusic ? "🎵 Musique" : "🔊 Bruitage"}
                          </span>
                          <span className="sound-card-date">{formatDate(sound.created_at)}</span>
                          {sound.loop && <span className="sound-card-badge-loop">🔁 Boucle</span>}
                          {isMusic && sound.instrumental && (
                            <span className="sound-card-badge-inst">🎷 Instrumental</span>
                          )}
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
                          {sound.duration_seconds && (
                            <span>⏱️ {isMusic ? formatTime(sound.duration_seconds) : `${sound.duration_seconds.toFixed(1)}s`}</span>
                          )}
                          <span>📦 {formatFileSize(sound.size)}</span>
                        </div>
                        <div className="sound-card-actions">
                          <a
                            href={sound.download_url}
                            download={sound.filename}
                            className="sound-card-btn"
                            title="Télécharger le fichier audio"
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
                              {isMusic ? <Music size={14} /> : <Volume2 size={14} />}
                            </button>
                          )}
                          <button
                            type="button"
                            className="sound-card-btn is-danger"
                            onClick={() => handleDelete(sound.id)}
                            title="Supprimer définitivement ce fichier"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
