"use client";

import { Check, LoaderCircle, Mic, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/api";
import { transcribeAudio } from "@/lib/voice-api";

const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickSupportedMimeType(): string {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return "";
  }
  for (const mime of PREFERRED_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mime)) {
      return mime;
    }
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

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export interface VoiceRecorderButtonProps {
  disabled?: boolean;
  sttEnabled: boolean;
  sttProvider?: string | null;
  onTranscribed: (text: string) => void;
  onError: (message: string) => void;
}

export function VoiceRecorderButton({
  disabled = false,
  sttEnabled,
  sttProvider,
  onTranscribed,
  onError,
}: VoiceRecorderButtonProps) {
  const [phase, setPhase] = useState<"idle" | "recording" | "transcribing">("idle");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const cancelledRef = useRef(false);

  function cleanupMedia() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    recorderRef.current = null;
  }

  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try {
          recorderRef.current.stop();
        } catch {
          // Ignorer lors du démontage
        }
      }
      cleanupMedia();
    };
  }, []);

  async function startRecording() {
    if (disabled || !sttEnabled || phase !== "idle") return;
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      onError(
        "L'accès au micro nécessite un navigateur compatible et une connexion sécurisée (HTTPS ou localhost).",
      );
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      onError("L'enregistrement audio n'est pas pris en charge par ce navigateur.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      cancelledRef.current = false;

      const mimeType = pickSupportedMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const wasCancelled = cancelledRef.current;
        const recordedMime = recorder.mimeType || mimeType || "audio/webm";
        const recordedChunks = chunksRef.current;
        chunksRef.current = [];
        cleanupMedia();

        if (wasCancelled) {
          setPhase("idle");
          setElapsedSeconds(0);
          return;
        }

        const audioBlob = new Blob(recordedChunks, { type: recordedMime });
        if (audioBlob.size < 256) {
          setPhase("idle");
          setElapsedSeconds(0);
          onError("Enregistrement trop court ou silencieux.");
          return;
        }

        setPhase("transcribing");
        const ext = extensionForMime(recordedMime);
        void transcribeAudio(audioBlob, `dictation.${ext}`, "fr")
          .then((result) => {
            const text = (result.text || "").trim();
            if (text) {
              onTranscribed(text);
            } else {
              onError("Aucune parole détectée dans l'enregistrement.");
            }
          })
          .catch((err) => {
            onError(errorMessage(err));
          })
          .finally(() => {
            setPhase("idle");
            setElapsedSeconds(0);
          });
      };

      recorder.start(250);
      setElapsedSeconds(0);
      setPhase("recording");
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      cleanupMedia();
      setPhase("idle");
      if (err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "PermissionDeniedError")) {
        onError("Accès au micro refusé. Autorisez le microphone dans les réglages du navigateur.");
      } else {
        onError(errorMessage(err));
      }
    }
  }

  function finishRecording() {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      cancelledRef.current = false;
      recorderRef.current.stop();
    }
  }

  function cancelRecording() {
    cancelledRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    } else {
      cleanupMedia();
      setPhase("idle");
      setElapsedSeconds(0);
    }
  }

  const providerLabel =
    sttProvider === "mistral"
      ? "Mistral Voxtral"
      : sttProvider === "google"
        ? "Google Gemini Audio"
        : "Transcription vocale";

  if (phase === "recording") {
    return (
      <div className="voice-recorder-active" role="status" aria-live="polite">
        <span className="voice-rec-dot" aria-hidden="true" />
        <span className="voice-rec-timer">{formatDuration(elapsedSeconds)}</span>
        <button
          type="button"
          className="voice-rec-action is-cancel"
          onClick={cancelRecording}
          title="Annuler l'enregistrement"
          aria-label="Annuler l'enregistrement"
        >
          <X size={14} />
        </button>
        <button
          type="button"
          className="voice-rec-action is-confirm"
          onClick={finishRecording}
          title={`Terminer et transcrire (${providerLabel})`}
          aria-label="Terminer et transcrire"
        >
          <Check size={14} />
        </button>
      </div>
    );
  }

  if (phase === "transcribing") {
    return (
      <button
        type="button"
        className="voice-icon-btn is-busy"
        disabled
        title={`Transcription en cours (${providerLabel})…`}
        aria-label="Transcription vocale en cours"
      >
        <LoaderCircle size={17} className="spin" />
      </button>
    );
  }

  return (
    <button
      type="button"
      className="voice-icon-btn"
      disabled={disabled || !sttEnabled}
      onClick={() => void startRecording()}
      title={
        sttEnabled
          ? `Dicter au micro (${providerLabel})`
          : "Dictée vocale indisponible : configurez MISTRAL_API_KEY ou GOOGLE_API_KEY"
      }
      aria-label="Dicter un message au micro"
    >
      <Mic size={17} />
    </button>
  );
}
