"use client";

import {
  ArrowUp,
  AudioLines,
  BookOpen,
  Check,
  LoaderCircle,
  Mic,
  Pause,
  Play,
  Plus,
  Square,
  TrendingUp,
  Volume2,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import {
  ensureVisualDocFromFinanceReport,
  errorMessage,
  fetchQuarterlyReports,
  listVisualDocs,
  type Message,
  type QuarterlyReport,
  type VisualDocSummary,
} from "@/lib/api";
import {
  linkifyPageCitations,
  parsePageCitationHref,
  prepareStreamingVisualMarkdown,
} from "@/lib/visual-doc-markdown";
import { transcribeAudio, type ToneOption, type VoiceOption } from "@/lib/voice-api";
import {
  formatSpeedLabel,
  VOICE_SPEED_OPTIONS,
  VoiceSettingsMenu,
} from "@/components/voice-settings-menu";
import styles from "./voice-fullscreen-modal.module.css";

const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

const SPEECH_START_RMS = 0.022;
const SILENCE_RMS = 0.015;
const SILENCE_AUTO_STOP_MS = 1800;
const NO_SPEECH_TIMEOUT_MS = 25000;
const MAX_RECORD_MS = 90000;

function pickSupportedMimeType(): string {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return "";
  }
  for (const mime of PREFERRED_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return "";
}

function extensionForMime(mime: string): string {
  const base = mime.split(";")[0].toLowerCase();
  if (base.includes("ogg")) return "ogg";
  if (base.includes("mp4") || base.includes("m4a")) return "m4a";
  if (base.includes("wav")) return "wav";
  return "webm";
}

function stripThinkBlock(text: string): string {
  if (!text) return "";
  return text.replace(/^<think>[\s\S]*?<\/think>\s*/, "");
}

function formatTimer(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export interface VoiceFullscreenModalProps {
  isOpen: boolean;
  onClose: () => void;
  conversationTitle: string;
  messages: Message[];
  streamingMessageId: string | null;
  working: boolean;
  activeVisualDocs: VisualDocSummary[];
  onAttachVisualDoc: (doc: VisualDocSummary) => Promise<void>;
  onDetachVisualDoc: (docId: string) => Promise<void>;
  onSendText: (text: string) => Promise<void>;
  onStopStream: () => void;
  // TTS / STT
  ttsEnabled: boolean;
  sttEnabled: boolean;
  sttProvider?: string | null;
  voices: VoiceOption[];
  tones?: ToneOption[];
  selectedVoice: string;
  selectedTone: string;
  playbackSpeed: number;
  autoReadEnabled: boolean;
  speakingMessageId: string | null;
  isSpeechPaused: boolean;
  loadingTtsMessageId: string | null;
  speechEndTick: number;
  onSelectVoice: (voiceId: string) => void;
  onSelectTone: (tone: string) => void;
  onSelectSpeed: (speed: number) => void;
  onToggleAutoRead: () => void;
  onTogglePauseSpeech: () => void;
  onStopSpeech: () => void;
  onSpeakMessage: (msg: Message) => void;
}

export function VoiceFullscreenModal(props: VoiceFullscreenModalProps) {
  if (!props.isOpen) return null;
  return <VoiceFullscreenSession {...props} />;
}

function VoiceFullscreenSession({
  onClose,
  conversationTitle,
  messages,
  streamingMessageId,
  working,
  activeVisualDocs,
  onAttachVisualDoc,
  onDetachVisualDoc,
  onSendText,
  onStopStream,
  ttsEnabled,
  sttEnabled,
  sttProvider,
  voices,
  tones,
  selectedVoice,
  selectedTone,
  playbackSpeed,
  autoReadEnabled,
  speakingMessageId,
  isSpeechPaused,
  loadingTtsMessageId,
  speechEndTick,
  onSelectVoice,
  onSelectTone,
  onSelectSpeed,
  onToggleAutoRead,
  onTogglePauseSpeech,
  onStopSpeech,
  onSpeakMessage,
}: VoiceFullscreenModalProps) {
  const [handsFree, setHandsFree] = useState(true);
  const [micPhase, setMicPhase] = useState<"idle" | "listening" | "transcribing">("idle");
  const [micLevel, setMicLevel] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [speechDetected, setSpeechDetected] = useState(false);
  const [keyboardDraft, setKeyboardDraft] = useState("");
  const [localError, setLocalError] = useState("");
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [availableVisualDocs, setAvailableVisualDocs] = useState<VisualDocSummary[]>([]);
  const [availableFinanceReports, setAvailableFinanceReports] = useState<QuarterlyReport[]>([]);
  const [loadingDocsList, setLoadingDocsList] = useState(false);
  const [attachingId, setAttachingId] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<{ src: string; title: string } | null>(null);

  const transcriptRef = useRef<HTMLDivElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const cancelledRef = useRef(false);
  const lastHandledSpeechEndRef = useRef(speechEndTick);
  const handsFreeRef = useRef(handsFree);
  const mountedRef = useRef(true);

  useEffect(() => {
    handsFreeRef.current = handsFree;
  }, [handsFree]);

  const isStreaming = Boolean(streamingMessageId);
  const isSpeaking = Boolean(speakingMessageId);
  const isLoadingTts = Boolean(loadingTtsMessageId);

  const cleanupAudio = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (audioCtxRef.current) {
      void audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    recorderRef.current = null;
    setMicLevel(0);
    setSpeechDetected(false);
  }, []);

  const cancelListening = useCallback(() => {
    cancelledRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try {
        recorderRef.current.stop();
      } catch {
        // Ignorer
      }
    }
    cleanupAudio();
    setMicPhase("idle");
    setElapsedSec(0);
  }, [cleanupAudio]);

  const finishListening = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      cancelledRef.current = false;
      try {
        recorderRef.current.stop();
      } catch {
        cleanupAudio();
        setMicPhase("idle");
      }
    }
  }, [cleanupAudio]);

  const startListening = useCallback(async () => {
    if (!mountedRef.current || !sttEnabled) return;
    if (recorderRef.current && recorderRef.current.state !== "inactive") return;
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setLocalError(
        "L'accès au micro nécessite une connexion sécurisée (HTTPS ou localhost).",
      );
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      setLocalError("Enregistrement audio non pris en charge par ce navigateur.");
      return;
    }

    setLocalError("");
    // Couper la voix de l'assistant si elle parle encore (barge-in)
    if (isSpeaking || isLoadingTts) {
      onStopSpeech();
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      chunksRef.current = [];
      cancelledRef.current = false;

      const mimeType = pickSupportedMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
      };

      recorder.onstop = () => {
        const wasCancelled = cancelledRef.current;
        const recMime = recorder.mimeType || mimeType || "audio/webm";
        const recordedChunks = chunksRef.current;
        chunksRef.current = [];
        cleanupAudio();

        if (wasCancelled || !mountedRef.current) {
          if (mountedRef.current) {
            setMicPhase("idle");
            setElapsedSec(0);
          }
          return;
        }

        const blob = new Blob(recordedChunks, { type: recMime });
        if (blob.size < 300) {
          setMicPhase("idle");
          setElapsedSec(0);
          return;
        }

        setMicPhase("transcribing");
        const ext = extensionForMime(recMime);
        void transcribeAudio(blob, `live.${ext}`, "fr")
          .then(async (res) => {
            const text = (res.text || "").trim();
            setMicPhase("idle");
            setElapsedSec(0);
            if (!text) {
              setLocalError("Aucune parole détectée. Parlez ou cliquez sur le micro pour réessayer.");
              return;
            }
            await onSendText(text);
          })
          .catch((err) => {
            setMicPhase("idle");
            setElapsedSec(0);
            setLocalError(errorMessage(err));
          });
      };

      recorder.start(250);
      setElapsedSec(0);
      setMicPhase("listening");
      const startedAt = Date.now();
      timerRef.current = window.setInterval(() => {
        setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
      }, 500);

      // Détection de niveau sonore et fin de parole automatique (Web Audio API)
      try {
        const AudioContextCtor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (AudioContextCtor) {
          const ctx = new AudioContextCtor();
          audioCtxRef.current = ctx;
          const source = ctx.createMediaStreamSource(stream);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 512;
          source.connect(analyser);
          const dataArray = new Uint8Array(analyser.fftSize);

          let hasSpoken = false;
          let silenceSince: number | null = null;

          const tick = () => {
            if (!recorderRef.current || recorderRef.current.state !== "recording") return;
            analyser.getByteTimeDomainData(dataArray);
            let sumSq = 0;
            for (let i = 0; i < dataArray.length; i += 1) {
              const norm = (dataArray[i] - 128) / 128;
              sumSq += norm * norm;
            }
            const rms = Math.sqrt(sumSq / dataArray.length);
            setMicLevel(Math.min(1, rms * 9));

            const nowMs = Date.now();
            if (rms >= SPEECH_START_RMS) {
              if (!hasSpoken) {
                hasSpoken = true;
                setSpeechDetected(true);
              }
              silenceSince = null;
            } else if (hasSpoken && rms < SILENCE_RMS) {
              if (silenceSince === null) {
                silenceSince = nowMs;
              } else if (nowMs - silenceSince >= SILENCE_AUTO_STOP_MS) {
                finishListening();
                return;
              }
            }

            if (!hasSpoken && nowMs - startedAt >= NO_SPEECH_TIMEOUT_MS) {
              cancelListening();
              return;
            }
            if (nowMs - startedAt >= MAX_RECORD_MS) {
              finishListening();
              return;
            }

            rafRef.current = requestAnimationFrame(tick);
          };
          rafRef.current = requestAnimationFrame(tick);
        }
      } catch {
        // Repli manuel si AudioContext indisponible
      }
    } catch (err) {
      cleanupAudio();
      setMicPhase("idle");
      if (err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "PermissionDeniedError")) {
        setLocalError("Accès au micro refusé. Autorisez le microphone dans le navigateur.");
      } else {
        setLocalError(errorMessage(err));
      }
    }
  }, [cancelListening, cleanupAudio, finishListening, isLoadingTts, isSpeaking, onSendText, onStopSpeech, sttEnabled]);

  // Nettoyage complet du micro au démontage de la session plein écran
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cancelledRef.current = true;
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try {
          recorderRef.current.stop();
        } catch {
          // Ignorer lors du démontage
        }
      }
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      if (audioCtxRef.current) void audioCtxRef.current.close().catch(() => {});
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // Boucle Mains-Libres : réarmer automatiquement le micro quand la lecture TTS se termine
  useEffect(() => {
    if (speechEndTick === lastHandledSpeechEndRef.current) return;
    lastHandledSpeechEndRef.current = speechEndTick;
    if (!handsFreeRef.current || !sttEnabled || working || isStreaming) return;
    const timeoutId = window.setTimeout(() => {
      if (mountedRef.current && handsFreeRef.current) {
        void startListening();
      }
    }, 450);
    return () => window.clearTimeout(timeoutId);
  }, [speechEndTick, sttEnabled, working, isStreaming, startListening]);

  // Scroll automatique vers le bas lors des nouveaux tokens
  useEffect(() => {
    const el = transcriptRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, streamingMessageId]);

  // Raccourcis clavier (Escape pour fermer, Espace hors saisie pour parler/couper)
  useEffect(() => {
    function onKeyDown(ev: globalThis.KeyboardEvent) {
      if (ev.key === "Escape") {
        if (lightbox) {
          setLightbox(null);
        } else if (docPickerOpen) {
          setDocPickerOpen(false);
        } else {
          onClose();
        }
        return;
      }
      const target = ev.target as HTMLElement | null;
      const isTyping =
        target &&
        (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable);
      if (ev.code === "Space" && !isTyping) {
        ev.preventDefault();
        if (micPhase === "listening") {
          finishListening();
        } else if (isStreaming) {
          onStopStream();
        } else if (isSpeaking || isLoadingTts) {
          onStopSpeech();
          void startListening();
        } else if (micPhase === "idle" && !working) {
          void startListening();
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    docPickerOpen,
    finishListening,
    isLoadingTts,
    isSpeaking,
    isStreaming,
    lightbox,
    micPhase,
    onClose,
    onStopSpeech,
    onStopStream,
    startListening,
    working,
  ]);

  // Fermer le picker de documents sur clic extérieur
  useEffect(() => {
    if (!docPickerOpen) return;
    function onDown(ev: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(ev.target as Node)) {
        setDocPickerOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [docPickerOpen]);

  async function openDocPicker() {
    if (docPickerOpen) {
      setDocPickerOpen(false);
      return;
    }
    setDocPickerOpen(true);
    setLoadingDocsList(true);
    try {
      const [vdocs, finReports] = await Promise.all([
        listVisualDocs().catch(() => [] as VisualDocSummary[]),
        fetchQuarterlyReports().catch(() => [] as QuarterlyReport[]),
      ]);
      setAvailableVisualDocs(vdocs);
      setAvailableFinanceReports(finReports);
    } finally {
      setLoadingDocsList(false);
    }
  }

  async function handleAttachFinanceReport(report: QuarterlyReport) {
    setAttachingId(report.id);
    setLocalError("");
    try {
      const vdoc = await ensureVisualDocFromFinanceReport(report.id);
      await onAttachVisualDoc(vdoc);
      setDocPickerOpen(false);
    } catch (err) {
      setLocalError(errorMessage(err));
    } finally {
      setAttachingId(null);
    }
  }

  async function handleKeyboardSubmit(ev: FormEvent) {
    ev.preventDefault();
    const text = keyboardDraft.trim();
    if (!text || working || isStreaming) return;
    if (micPhase === "listening") cancelListening();
    if (isSpeaking) onStopSpeech();
    setKeyboardDraft("");
    await onSendText(text);
  }

  function handleKeyboardKeyDown(ev: KeyboardEvent<HTMLTextAreaElement>) {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      void handleKeyboardSubmit(ev as unknown as FormEvent);
    }
  }

  function handleOrbClick() {
    if (micPhase === "listening") {
      finishListening();
    } else if (isStreaming) {
      onStopStream();
    } else if (isSpeaking || isLoadingTts) {
      onStopSpeech();
      void startListening();
    } else if (micPhase === "idle" && !working) {
      void startListening();
    }
  }

  function cycleSpeed() {
    const idx = VOICE_SPEED_OPTIONS.findIndex((s) => Math.abs(s - playbackSpeed) < 0.01);
    const next = VOICE_SPEED_OPTIONS[(idx + 1) % VOICE_SPEED_OPTIONS.length];
    onSelectSpeed(next);
  }

  const attachedIds = new Set(activeVisualDocs.map((d) => d.id));
  const lastAssistantIdx = messages.reduce(
    (acc, msg, idx) => (msg.role === "assistant" ? idx : acc),
    -1,
  );

  let orbClass = styles.orbButton;
  let statusTitle = "Prêt à écouter";
  let statusSub = "Cliquez sur le micro ou appuyez sur Espace pour parler (ou tapez ci-dessous).";

  if (micPhase === "listening") {
    orbClass = `${styles.orbButton} ${styles.orbListening}`;
    statusTitle = speechDetected
      ? `Je vous écoute… (${formatTimer(elapsedSec)})`
      : `Micro actif — parlez maintenant (${formatTimer(elapsedSec)})`;
    statusSub = speechDetected
      ? "Envoi automatique après ~1,8 s de silence (ou cliquez sur le micro pour envoyer de suite)."
      : "Détection automatique de votre voix active · Espace ou clic pour valider.";
  } else if (micPhase === "transcribing") {
    orbClass = `${styles.orbButton} ${styles.orbThinking}`;
    statusTitle = "Transcription en cours…";
    statusSub = sttProvider === "mistral" ? "Mistral Voxtral analyse votre voix." : "Analyse vocale en cours.";
  } else if (isStreaming) {
    orbClass = `${styles.orbButton} ${styles.orbThinking}`;
    statusTitle = "cLAIr réfléchit et répond…";
    statusSub = "La lecture vocale démarrera automatiquement à la fin de la réponse.";
  } else if (isLoadingTts) {
    orbClass = `${styles.orbButton} ${styles.orbThinking}`;
    statusTitle = "Préparation de la voix…";
    statusSub = `Synthèse Google (${selectedVoice}) en cours…`;
  } else if (isSpeaking) {
    orbClass = `${styles.orbButton} ${styles.orbSpeaking}`;
    statusTitle = isSpeechPaused ? "Lecture en pause" : `cLAIr parle (${selectedVoice})`;
    statusSub = handsFree
      ? "Cliquez sur le micro ou Espace pour couper la parole · Le micro se réactivera ensuite."
      : "Cliquez sur le micro ou Espace pour interrompre et poser une question.";
  }

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label="Mode Vocal Plein Écran"
    >
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.badgeLive}>
            <AudioLines size={15} />
            <span>Mode Vocal Plein Écran</span>
          </span>
          <span className={styles.convTitle} title={conversationTitle}>
            {conversationTitle || "Nouvelle discussion"}
          </span>

          <div className={styles.docsRow}>
            {activeVisualDocs.map((doc) => (
              <span key={doc.id} className={styles.docChip}>
                <BookOpen size={12} />
                <span>
                  {doc.title} ({doc.page_count} p.)
                </span>
                <button
                  type="button"
                  className={styles.docChipRemove}
                  onClick={() => void onDetachVisualDoc(doc.id)}
                  title={`Détacher ${doc.title}`}
                  aria-label={`Détacher ${doc.title}`}
                >
                  <X size={12} />
                </button>
              </span>
            ))}

            <div className={styles.docPickerWrap} ref={pickerRef}>
              <button
                type="button"
                className={styles.headerBtn}
                onClick={() => void openDocPicker()}
                title="Attacher un Document Illustré ou un Rapport Financier à cette discussion vocale"
              >
                <Plus size={14} />
                <span>Document / Finance</span>
              </button>

              {docPickerOpen && (
                <div className={styles.docPickerPopover} role="menu">
                  {loadingDocsList ? (
                    <div className={styles.docPickerSection}>
                      <LoaderCircle size={13} className="spin" /> Chargement…
                    </div>
                  ) : (
                    <>
                      <div className={styles.docPickerSection}>
                        Documents Illustrés ({availableVisualDocs.length})
                      </div>
                      {availableVisualDocs.length === 0 ? (
                        <div className={styles.docPickerItem}>
                          <small>Aucun document illustré ingéré</small>
                        </div>
                      ) : (
                        availableVisualDocs.map((doc) => {
                          const attached = attachedIds.has(doc.id);
                          return (
                            <button
                              key={doc.id}
                              type="button"
                              className={styles.docPickerItem}
                              disabled={attached}
                              onClick={async () => {
                                await onAttachVisualDoc(doc);
                                setDocPickerOpen(false);
                              }}
                            >
                              <div className={styles.docPickerItemMain}>
                                <strong>{doc.title}</strong>
                                <small>
                                  {doc.page_count} p. · {doc.figure_count} fig.
                                </small>
                              </div>
                              {attached ? <Check size={14} /> : <BookOpen size={14} />}
                            </button>
                          );
                        })
                      )}

                      <div className={styles.docPickerSection}>
                        Rapports Financiers ({availableFinanceReports.length})
                      </div>
                      {availableFinanceReports.length === 0 ? (
                        <div className={styles.docPickerItem}>
                          <small>Aucun rapport financier archivé</small>
                        </div>
                      ) : (
                        availableFinanceReports.map((rep) => (
                          <button
                            key={rep.id}
                            type="button"
                            className={styles.docPickerItem}
                            disabled={attachingId === rep.id}
                            onClick={() => void handleAttachFinanceReport(rep)}
                          >
                            <div className={styles.docPickerItemMain}>
                              <strong>
                                {rep.company_name || rep.symbol}
                                {rep.period_label ? ` — ${rep.period_label}` : ""}
                              </strong>
                              <small>
                                {rep.title}
                                {rep.page_count ? ` · ${rep.page_count} p.` : ""}
                              </small>
                            </div>
                            {attachingId === rep.id ? (
                              <LoaderCircle size={14} className="spin" />
                            ) : (
                              <TrendingUp size={14} />
                            )}
                          </button>
                        ))
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className={styles.headerRight}>
          <button
            type="button"
            className={`${styles.headerBtn} ${handsFree ? styles.headerBtnActive : ""}`}
            onClick={() => setHandsFree((prev) => !prev)}
            title="Mode Mains-Libres : réactive automatiquement le micro dès que cLAIr a fini de parler"
          >
            <Mic size={14} />
            <span>Mains-libres {handsFree ? "ON" : "OFF"}</span>
          </button>

          <VoiceSettingsMenu
            ttsEnabled={ttsEnabled}
            voices={voices}
            tones={tones}
            selectedVoice={selectedVoice}
            selectedTone={selectedTone}
            playbackSpeed={playbackSpeed}
            autoReadEnabled={autoReadEnabled}
            isSpeaking={false}
            isPaused={false}
            onSelectVoice={onSelectVoice}
            onSelectTone={onSelectTone}
            onSelectSpeed={onSelectSpeed}
            onToggleAutoRead={onToggleAutoRead}
            onTogglePause={onTogglePauseSpeech}
            onStopSpeaking={onStopSpeech}
          />

          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            title="Quitter le mode plein écran (Échap)"
          >
            <X size={15} />
            <span>Quitter</span>
          </button>
        </div>
      </header>

      <main className={styles.main}>
        <div className={styles.transcriptArea} ref={transcriptRef}>
          {messages.length === 0 ? (
            <div className={styles.emptyStage}>
              <h2>
                {activeVisualDocs.length > 0
                  ? `Prêt à échanger sur « ${activeVisualDocs[0].title} »`
                  : "Conversation vocale plein écran"}
              </h2>
              <p>
                Appuyez sur le micro (ou la barre <strong>Espace</strong>) pour poser votre question à voix haute.
                En mode <strong>Mains-libres</strong>, la question part automatiquement après un court silence et
                la réponse est lue à voix haute avec ses schémas et tableaux à l&apos;écran.
              </p>
            </div>
          ) : (
            messages.map((msg, idx) => {
              if (msg.role === "user") {
                return (
                  <div key={msg.id} className={styles.turnUser}>
                    {msg.content}
                  </div>
                );
              }
              const isLatest = idx === lastAssistantIdx;
              const isMsgStreaming = streamingMessageId === msg.id;
              const rawBody = stripThinkBlock(msg.content);
              const prepared = prepareStreamingVisualMarkdown(rawBody, isMsgStreaming);
              const renderedMd =
                activeVisualDocs.length > 0
                  ? linkifyPageCitations(prepared, activeVisualDocs)
                  : prepared;

              return (
                <article
                  key={msg.id}
                  className={`${styles.turnAssistant} ${isLatest ? styles.turnAssistantLatest : ""}`}
                >
                  <div className={styles.turnAssistantHeader}>
                    <span>
                      cLAIr {isMsgStreaming ? "· en train de répondre…" : ""}
                    </span>
                    {!isMsgStreaming && ttsEnabled && rawBody.trim() && (
                      <button
                        type="button"
                        className={styles.headerBtn}
                        onClick={() => onSpeakMessage(msg)}
                      >
                        {speakingMessageId === msg.id ? (
                          isSpeechPaused ? <Play size={13} /> : <Pause size={13} />
                        ) : (
                          <Volume2 size={13} />
                        )}
                        <span>
                          {speakingMessageId === msg.id
                            ? (isSpeechPaused ? "Reprendre" : "Pause")
                            : "Réécouter"}
                        </span>
                      </button>
                    )}
                  </div>
                  <div className={styles.turnAssistantBody}>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        a: ({ href, children }) => {
                          const citation = parsePageCitationHref(href);
                          if (citation) {
                            const doc =
                              activeVisualDocs.find((d) => d.slug === citation.slug) ??
                              activeVisualDocs[0];
                            return (
                              <button
                                type="button"
                                className={styles.pageLinkBtn}
                                onClick={() =>
                                  setLightbox({
                                    src: `/api/docs/${citation.slug}/page_${citation.page}.webp`,
                                    title: `${doc?.title || "Document"} — Page ${citation.page}`,
                                  })
                                }
                              >
                                {children}
                              </button>
                            );
                          }
                          return (
                            <a href={href} target="_blank" rel="noopener noreferrer">
                              {children}
                            </a>
                          );
                        },
                        img: ({ src, alt }) => {
                          const strSrc = typeof src === "string" ? src : "";
                          if (!strSrc) return null;
                          return (
                            <img
                              src={strSrc}
                              alt={alt || "Illustration"}
                              onClick={() =>
                                setLightbox({ src: strSrc, title: alt || "Schéma" })
                              }
                            />
                          );
                        },
                      }}
                    >
                      {renderedMd}
                    </ReactMarkdown>
                  </div>
                </article>
              );
            })
          )}
        </div>

        <section className={styles.dock}>
          {localError && (
            <div className={styles.errorBanner} role="alert">
              <span>{localError}</span>
              <button
                type="button"
                className={styles.docChipRemove}
                onClick={() => setLocalError("")}
                aria-label="Fermer l'alerte"
              >
                <X size={14} />
              </button>
            </div>
          )}

          <div className={styles.voiceStageRow}>
            <div className={styles.orbArea}>
              <button
                type="button"
                className={orbClass}
                style={{ "--mic-level": micLevel } as CSSProperties}
                disabled={!sttEnabled && micPhase === "idle" && !isSpeaking && !isStreaming}
                onClick={handleOrbClick}
                aria-label={statusTitle}
                title={statusTitle}
              >
                {micPhase === "transcribing" || isLoadingTts ? (
                  <LoaderCircle size={28} className="spin" />
                ) : isStreaming ? (
                  <Square size={22} fill="currentColor" />
                ) : (
                  <Mic size={28} />
                )}
              </button>
              <div className={styles.statusText}>
                <span className={styles.statusTitle}>{statusTitle}</span>
                <span className={styles.statusSub}>{statusSub}</span>
              </div>
            </div>

            <div className={styles.liveControls}>
              {micPhase === "listening" && (
                <>
                  <button
                    type="button"
                    className={styles.headerBtn}
                    onClick={cancelListening}
                  >
                    <X size={14} />
                    <span>Annuler</span>
                  </button>
                  <button
                    type="button"
                    className={`${styles.headerBtn} ${styles.headerBtnActive}`}
                    onClick={finishListening}
                  >
                    <Check size={14} />
                    <span>Envoyer maintenant</span>
                  </button>
                </>
              )}

              {isSpeaking && (
                <>
                  <button
                    type="button"
                    className={`${styles.headerBtn} ${styles.headerBtnActive}`}
                    onClick={onTogglePauseSpeech}
                  >
                    {isSpeechPaused ? <Play size={14} /> : <Pause size={14} />}
                    <span>{isSpeechPaused ? "Reprendre" : "Pause"}</span>
                  </button>
                  <button
                    type="button"
                    className={styles.headerBtn}
                    onClick={cycleSpeed}
                    title="Changer la vitesse de lecture"
                  >
                    <span>{formatSpeedLabel(playbackSpeed)}</span>
                  </button>
                  <button
                    type="button"
                    className={styles.headerBtn}
                    onClick={onStopSpeech}
                  >
                    <Square size={12} fill="currentColor" />
                    <span>Arrêter</span>
                  </button>
                </>
              )}
            </div>
          </div>

          <form className={styles.keyboardForm} onSubmit={(e) => void handleKeyboardSubmit(e)}>
            <textarea
              className={styles.keyboardInput}
              rows={1}
              value={keyboardDraft}
              onChange={(e) => setKeyboardDraft(e.target.value)}
              onKeyDown={handleKeyboardKeyDown}
              placeholder={
                activeVisualDocs.length > 0
                  ? `Ou tapez une question au clavier sur « ${activeVisualDocs[0].title} »…`
                  : "Ou tapez votre message au clavier (Entrée pour envoyer)…"
              }
              disabled={working || isStreaming}
            />
            <button
              type="submit"
              className={styles.sendBtn}
              disabled={!keyboardDraft.trim() || working || isStreaming}
            >
              <ArrowUp size={16} />
              <span>Envoyer</span>
            </button>
          </form>
        </section>
      </main>

      {lightbox && (
        <div
          className={styles.lightbox}
          role="dialog"
          aria-modal="true"
          onClick={() => setLightbox(null)}
        >
          <div className={styles.lightboxCard} onClick={(e) => e.stopPropagation()}>
            <div className={styles.lightboxHead}>
              <strong>{lightbox.title}</strong>
              <button
                type="button"
                className={styles.closeBtn}
                onClick={() => setLightbox(null)}
              >
                <X size={15} />
                <span>Fermer</span>
              </button>
            </div>
            <div className={styles.lightboxBody}>
              <img src={lightbox.src} alt={lightbox.title} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
