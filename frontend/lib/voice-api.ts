import { ApiError } from "./api";

export type VoiceOption = {
  id: string;
  name: string;
  tone: string;
};

export type TranscribeResult = {
  text: string;
  provider: string;
  model: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export async function synthesizeSpeech(
  text: string,
  voice?: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(`${API_BASE}/voice/tts`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice: voice || undefined }),
    signal,
  });

  if (!response.ok) {
    let detail = `Erreur HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string" && payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Réponse non JSON
    }
    throw new ApiError(detail, response.status);
  }

  return await response.blob();
}

export async function transcribeAudio(
  audioBlob: Blob,
  filename = "dictation.webm",
  language?: string,
  signal?: AbortSignal,
): Promise<TranscribeResult> {
  const form = new FormData();
  form.append("file", audioBlob, filename);
  if (language) {
    form.append("language", language);
  }

  const response = await fetch(`${API_BASE}/voice/transcribe`, {
    method: "POST",
    credentials: "include",
    body: form,
    signal,
  });

  if (!response.ok) {
    let detail = `Erreur HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string" && payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Réponse non JSON
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as TranscribeResult;
}
