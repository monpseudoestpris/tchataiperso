export type Model = { id: string; name: string; vision: boolean };
export type Config = {
  models: Model[];
  default_model: string;
  features: { chat: boolean; web_search: boolean; ocr: boolean; image_generation: boolean };
  demo_mode: boolean;
};
export type Attachment = { id: string; filename: string; mime_type: string; url: string; size?: number };
export type Source = { title: string; url: string; snippet?: string };
export type Message = { id: string; role: string; content: string; created_at: string; attachments: Attachment[]; sources: Source[] };
export type Conversation = { id: string; title: string; model: string; created_at: string; updated_at: string; summary?: string | null; messages?: Message[] };
export type Memory = { id: string; content: string; created_at: string };
export type StreamEvent =
  | { type: "meta"; data: { user_message: Message; assistant_message_id: string } }
  | { type: "status"; data: { message: string } }
  | { type: "delta"; data: { text: string } }
  | { type: "done"; data: { message: Message; conversation: Conversation } }
  | { type: "error"; data: { message: string } };

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Une erreur inattendue est survenue.";
}

async function responseError(response: Response): Promise<Error> {
  let detail = `Le serveur a renvoyé une erreur (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((item: { msg?: string }) => item.msg ?? "Valeur invalide").join(" · ");
    else if (typeof body.message === "string") detail = body.message;
  } catch { /* Keep the HTTP status for non-JSON gateway failures. */ }
  return new Error(detail);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw await responseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** Parses complete SSE frames while retaining partial UTF-8 and multiline data. */
export async function streamMessage(
  conversationId: string,
  body: { content: string; model: string; web_search: boolean; attachment_ids: string[] },
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body), signal,
  });
  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new Error("Le serveur ne fournit aucun flux de réponse.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  function consume(frame: string) {
    let event = "message";
    const lines: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) lines.push(line.slice(5).replace(/^ /, ""));
    }
    if (!lines.length) return;
    const data = JSON.parse(lines.join("\n"));
    if (["meta", "status", "delta", "done", "error"].includes(event)) {
      if (event === "done") completed = true;
      if (event === "error") throw new Error(data.message ?? "La génération a échoué.");
      onEvent({ type: event, data } as StreamEvent);
    }
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let match: RegExpMatchArray | null;
      while ((match = buffer.match(/\r?\n\r?\n/))) {
        const index = match.index!;
        consume(buffer.slice(0, index));
        buffer = buffer.slice(index + match[0].length);
      }
      if (done) break;
    }
    if (buffer.trim()) consume(buffer);
    if (!completed) throw new Error("La connexion a été interrompue avant la fin de la réponse. Votre message a peut-être été enregistré ; rechargez la conversation avant de le renvoyer.");
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
