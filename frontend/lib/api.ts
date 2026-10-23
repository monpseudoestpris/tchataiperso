export type Model = { id: string; name: string; vision: boolean };
export type Config = {
  models: Model[];
  default_model: string;
  image_prompt_model?: string;
  themes?: string[];
  features: { chat: boolean; web_search: boolean; ocr: boolean; image_generation: boolean };
  search_providers?: string[];
  demo_mode: boolean;
};
export type Attachment = {
  id: string;
  filename: string;
  mime_type: string;
  url: string;
  size?: number;
  has_extraction?: boolean;
  page_count?: number;
  source_url?: string | null;
  finance_meta?: {
    symbol?: string;
    short_name?: string;
    long_name?: string;
    price?: number;
    currency?: string;
    change_percent?: number;
    exchange?: string;
    url?: string;
    provider?: string;
    source_label?: string;
  } | null;
};
export type GeneratedImage = {
  id: string;
  prompt: string;
  aspect_ratio: string;
  filename: string;
  mime_type: string;
  size: number;
  url: string;
  download_url: string;
  created_at: string;
};
export type DocumentExtraction = {
  version: 1;
  model: string;
  pages: {
    index: number;
    markdown: string;
    method: "ocr" | "vision" | "local";
    vision_description: string;
    images: {
      id: string;
      annotation: { image_type: string; description: string; visible_text: string } | null;
    }[];
  }[];
  annotations: { title: string; summary: string }[];
  warnings: string[];
};
export type Source = { title: string; url: string; snippet?: string; query?: string; provider?: string; search_notice?: string };
export type Message = { id: string; role: string; content: string; created_at: string; attachments: Attachment[]; sources: Source[] };
export type Skill = { id: string; name: string; prompt: string; created_at: string; updated_at: string };
export type BlogCard = {
  title: string;
  text: string;
  url: string;
  source_name: string;
  tag: string;
  color: "blue" | "emerald" | "purple" | "amber" | "rose" | "cyan" | string;
};
export type BlogPost = {
  id: string;
  blog_id: string;
  title: string;
  summary: string;
  content: string;
  cards?: BlogCard[];
  sources: Source[];
  created_at: string;
};
export type Blog = {
  id: string;
  title: string;
  prompt: string;
  auto_refresh: boolean;
  theme?: string;
  created_at: string;
  updated_at: string;
  posts_count: number;
  latest_post?: {
    id: string;
    title: string;
    summary: string;
    created_at: string;
  } | null;
  posts?: BlogPost[];
};
export type Conversation = {
  id: string;
  title: string;
  model: string;
  theme?: string;
  keywords?: string[];
  created_at: string;
  updated_at: string;
  summary?: string | null;
  messages?: Message[];
  skills?: Skill[];
};
export type Memory = { id: string; content: string; created_at: string };
export type AuthUser = { id: string; username: string; is_admin: boolean };
export type AdminUser = AuthUser & { active: boolean; created_at: string };
export type StreamEvent =
  | { type: "meta"; data: { user_message: Message; assistant_message_id: string } }
  | { type: "status"; data: { message: string } }
  | { type: "delta"; data: { text: string } }
  | { type: "done"; data: { message: Message; conversation: Conversation } }
  | { type: "error"; data: { message: string } };

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Une erreur inattendue est survenue.";
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function responseError(response: Response): Promise<ApiError> {
  let detail = `Le serveur a renvoyé une erreur (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((item: { msg?: string }) => item.msg ?? "Valeur invalide").join(" · ");
    else if (typeof body.message === "string") detail = body.message;
  } catch { /* Keep the HTTP status for non-JSON gateway failures. */ }
  return new ApiError(detail, response.status);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw await responseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function skillToSlug(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Parses complete SSE frames while retaining partial UTF-8 and multiline data. */
export async function streamMessage(
  conversationId: string,
  body: {
    content: string;
    model: string;
    web_search: boolean;
    deep_search?: boolean;
    code_mode?: boolean;
    finance_mode?: boolean;
    attachment_ids: string[];
    skill_ids?: string[];
  },
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

export async function attachUrl(url: string): Promise<Attachment> {
  return api<Attachment>("/attachments/url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function fetchBlogs(): Promise<Blog[]> {
  return api<Blog[]>("/blogs");
}

export async function fetchBlog(blogId: string): Promise<Blog> {
  return api<Blog>(`/blogs/${blogId}`);
}

export async function createBlog(body: { prompt: string; title?: string; auto_refresh?: boolean; theme?: string }): Promise<Blog> {
  return api<Blog>("/blogs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateBlog(
  blogId: string,
  body: { title?: string; prompt?: string; auto_refresh?: boolean; theme?: string },
): Promise<Blog> {
  return api<Blog>(`/blogs/${blogId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteBlog(blogId: string): Promise<void> {
  return api<void>(`/blogs/${blogId}`, {
    method: "DELETE",
  });
}

export async function refreshBlog(
  blogId: string,
): Promise<{ blog: Blog; new_post: BlogPost }> {
  return api<{ blog: Blog; new_post: BlogPost }>(`/blogs/${blogId}/refresh`, {
    method: "POST",
  });
}

export async function deleteBlogPost(blogId: string, postId: string): Promise<void> {
  return api<void>(`/blogs/${blogId}/posts/${postId}`, {
    method: "DELETE",
  });
}


