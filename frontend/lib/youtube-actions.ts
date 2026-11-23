export type YoutubeTranscriptAction =
  | "summarize"
  | "analyze"
  | "key_points"
  | "study"
  | "translate_fr";

export type UrlImportAction = YoutubeTranscriptAction | "custom" | "attach_only";

export type UrlImportSubmitPayload = {
  url: string;
  action: UrlImportAction;
  customPrompt: string;
  openTranscriptAfterImport: boolean;
  saveToLibrary: boolean;
};

export type YoutubeActionMeta = {
  id: YoutubeTranscriptAction;
  label: string;
  shortLabel: string;
  description: string;
  submitLabel: string;
  toneClass: string;
};

export const YOUTUBE_TRANSCRIPT_ACTIONS: readonly YoutubeActionMeta[] = [
  {
    id: "summarize",
    label: "Résumer",
    shortLabel: "Résumer",
    description: "Synthèse structurée, points clés par thème et repères [MM:SS].",
    submitLabel: "Extraire et résumer",
    toneClass: "is-summarize",
  },
  {
    id: "analyze",
    label: "Analyser",
    shortLabel: "Analyser",
    description: "Analyse critique, thèse, preuves, nuances et angles morts.",
    submitLabel: "Extraire et analyser",
    toneClass: "is-analyze",
  },
  {
    id: "key_points",
    label: "Points clés & Chapitres",
    shortLabel: "Chapitres",
    description: "Plan chronologique chapitré [MM:SS], citations et actions.",
    submitLabel: "Extraire les chapitres",
    toneClass: "is-key-points",
  },
  {
    id: "study",
    label: "Fiche & Quiz",
    shortLabel: "Fiche & Quiz",
    description: "Fiche de révision structurée + 5 questions d'auto-test.",
    submitLabel: "Créer la fiche",
    toneClass: "is-study",
  },
  {
    id: "translate_fr",
    label: "Traduire en français",
    shortLabel: "Traduire FR",
    description: "Restitution intégrale et fluide en français avec [MM:SS].",
    submitLabel: "Extraire et traduire",
    toneClass: "is-translate",
  },
] as const;

const YOUTUBE_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtu.be",
]);

export function isYoutubeUrl(rawUrl: string): boolean {
  const trimmed = (rawUrl || "").trim();
  if (!trimmed) return false;
  try {
    const parsed = new URL(trimmed);
    const host = parsed.hostname.toLowerCase();
    if (!YOUTUBE_HOSTS.has(host)) return false;
    if (host === "youtu.be") {
      return parsed.pathname.replace(/^\/+|\/+$/g, "").length >= 11;
    }
    const vParam = parsed.searchParams.get("v");
    if (vParam && vParam.length >= 11) return true;
    return /\/(?:shorts|embed|live|v)\/[a-zA-Z0-9_-]{11}/.test(parsed.pathname);
  } catch {
    return false;
  }
}

export function cleanVideoAttachmentTitle(filename: string): string {
  return (filename || "la vidéo").replace(/^🎬\s*/, "").replace(/^🌐\s*/, "").trim() || "la vidéo";
}

export function buildYoutubeActionPrompt(
  action: YoutubeTranscriptAction | "custom",
  rawTitle: string,
  options?: { customPrompt?: string; isYoutube?: boolean },
): string {
  const title = cleanVideoAttachmentTitle(rawTitle);
  const isYoutube = options?.isYoutube ?? true;
  const targetLabel = isYoutube ? `la vidéo « ${title} »` : `le contenu « ${title} »`;
  const timingHint = isYoutube ? " et repères temporels [MM:SS]" : "";

  if (action === "custom") {
    const custom = (options?.customPrompt || "").trim();
    if (custom) {
      return `En t'appuyant sur l'intégralité de ${targetLabel} (du début à la toute fin) : ${custom}`;
    }
  }

  switch (action) {
    case "analyze":
      return `Fais une analyse approfondie et critique de l'intégralité de ${targetLabel} (du début à la toute fin) : thèse centrale et structure de l'argumentation, points forts et preuves avancées, nuances, limites ou angles morts, et enseignements concrets à retenir${timingHint ? " (avec repères temporels [MM:SS])" : ""}.`;
    case "key_points":
      return `Découpe l'intégralité de ${targetLabel} en chapitres chronologiques clairs${timingHint ? " avec repères [MM:SS]" : ""}, puis liste les citations ou idées marquantes et les actions / enseignements pratiques à retenir.`;
    case "study":
      return `Transforme l'intégralité de ${targetLabel} en fiche de révision structurée (concepts clés, définitions précises, pièges à éviter) suivie de 5 questions d'auto-évaluation avec leurs réponses.`;
    case "translate_fr":
      return `Restitue intégralement et fidèlement en français fluide le contenu complet de ${targetLabel}, organisé en sections claires${timingHint ? " avec les repères temporels [MM:SS]" : ""}, sans omettre la fin ni résumer à outrance.`;
    case "summarize":
    default:
      return `Résume de façon claire, structurée et fidèle l'intégralité de ${targetLabel} (du début à la toute fin, sans rien omettre) : synthèse globale, points clés organisés par thème, exemples ou chiffres marquants${timingHint}.`;
  }
}

export function getUrlSubmitLabel(action: UrlImportAction, isYoutube: boolean): string {
  if (action === "attach_only") {
    return isYoutube ? "Extraire le transcript" : "Extraire et joindre";
  }
  if (action === "custom") {
    return "Extraire et lancer";
  }
  const found = YOUTUBE_TRANSCRIPT_ACTIONS.find((item) => item.id === action);
  return found ? found.submitLabel : "Extraire et joindre";
}
