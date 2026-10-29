export type Model = {
  id: string;
  name: string;
  vision: boolean;
  description?: string;
  context_length?: number;
  pricing?: {
    prompt?: string;
    completion?: string;
    input_cache_read?: string;
    [key: string]: any;
  };
  prompt_price_1m?: number;
  completion_price_1m?: number;
  input_cache_read_price_1m?: number | null;
  provider?: string;
  reasoning?: boolean;
};
export type ImageModel = { id: string; name: string; provider: "ideogram" | "openrouter" };
export type Config = {
  models: Model[];
  default_model: string;
  image_prompt_model?: string;
  image_models?: ImageModel[];
  default_image_model?: string;
  themes?: string[];
  features: {
    chat: boolean;
    web_search: boolean;
    ocr: boolean;
    image_generation: boolean;
    sound_effects?: boolean;
    music_generation?: boolean;
  };
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
    eod_bars?: EodBar[];
    financial_stats?: FinancialStats;
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
export type GeneratedSound = {
  id: string;
  sound_type?: "sound_effect" | "music";
  prompt: string;
  english_prompt?: string;
  duration_seconds?: number | null;
  prompt_influence?: number | null;
  output_format: string;
  loop?: boolean;
  instrumental?: boolean | null;
  model_id?: string | null;
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
export interface StageModelsConfig {
  plan_model?: string;
  search_model?: string;
  expert_model?: string;
  synthesis_model?: string;
  audit_model?: string;
}

export type Source = {
  title: string;
  url: string;
  snippet?: string;
  query?: string;
  provider?: string;
  search_notice?: string;
  auto_search_reason?: string;
  img_src?: string;
  thumbnail_src?: string;
  image_source?: string;
  resolution?: string;
  media_type?: "web" | "image";
};
export type AgentPersonaConfig = {
  id?: string;
  name: string;
  role: string;
  model: string;
  prompt: string;
  avatar: string;
  color: string;
};

export type MultiAgentConfig = {
  mode: "synthesis" | "debate" | "dialectic" | "contradictory";
  agents: AgentPersonaConfig[];
  rounds: number;
};

export type AgentTeam = {
  id: string;
  name: string;
  description: string;
  mode: "synthesis" | "debate" | "dialectic" | "contradictory";
  agents: AgentPersonaConfig[];
  created_at?: string;
  updated_at?: string;
};

export type AgentTeamsResponse = {
  teams: AgentTeam[];
  templates: Array<{
    id: string;
    name: string;
    role: string;
    avatar: string;
    color: string;
    prompt: string;
  }>;
  preset_teams: Array<{
    id: string;
    name: string;
    description: string;
    mode: "synthesis" | "debate" | "dialectic" | "contradictory";
    agents: AgentPersonaConfig[];
  }>;
};

export type Message = { id: string; role: string; content: string; created_at: string; attachments: Attachment[]; sources: Source[]; deep_search_report_id?: string | null; learn_report_id?: string | null };
export type DeepSearchReport = {
  id: string;
  user_id: string;
  conversation_id?: string | null;
  message_id?: string | null;
  title: string;
  topic: string;
  markdown_content: string;
  html_content?: string;
  sources: Source[];
  sources_count: number;
  created_at: string;
  html_url: string;
  pdf_url?: string;
  download_url?: string;
};
export type Flashcard = {
  id: number;
  category: string;
  recto: string;
  verso: string;
};

export type QuizQuestion = {
  id: number;
  question: string;
  options: string[];
  answer: number;
  explanation: string;
};

export type LearnReport = {
  id: string;
  user_id: string;
  conversation_id?: string | null;
  message_id?: string | null;
  title: string;
  topic: string;
  markdown_content: string;
  html_content?: string;
  sources: Source[];
  sources_count: number;
  created_at: string;
  html_url: string;
  pdf_url?: string;
  download_url?: string;
  flashcards?: Flashcard[];
  quiz?: QuizQuestion[];
};
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
export type PromptPreset = {
  id: string;
  title: string;
  description: string;
  prompt: string;
};

export type UserSettings = {
  system_prompt: string;
  prompt_cache_enabled: boolean;
  auto_memory_enabled: boolean;
  default_system_prompt: string;
  prompt_presets: PromptPreset[];
};

export type UpdateUserSettings = {
  system_prompt?: string;
  prompt_cache_enabled?: boolean;
  auto_memory_enabled?: boolean;
};

export type AuthUser = {
  id: string;
  username: string;
  is_admin: boolean;
  family_group_id?: string | null;
  family_group_name?: string | null;
  system_prompt?: string;
  prompt_cache_enabled?: boolean;
  auto_memory_enabled?: boolean;
};
export type FamilyMember = {
  id: string;
  username: string;
  is_admin: boolean;
  active: boolean;
  is_current: boolean;
};
export type FamilyGroupInfo = {
  id: string | null;
  name: string | null;
  members: FamilyMember[];
};
export type AdminUser = AuthUser & { active: boolean; created_at: string };
export type StreamEvent =
  | { type: "meta"; data: { user_message: Message; assistant_message_id: string } }
  | { type: "status"; data: { message: string } }
  | { type: "delta"; data: { text: string } }
  | {
      type: "done";
      data: {
        message: Message;
        conversation: Conversation;
        deep_search_report_id?: string | null;
        learn_report_id?: string | null;
        memories?: Memory[];
        new_memories?: string[];
        deleted_memories?: string[];
      };
    }
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
    auto_web_search?: boolean;
    web_search_mode?: "auto" | "always" | "off";
    deep_search?: boolean;
    deep_search_queries?: string[];
    learn_mode?: boolean;
    learn_mode_queries?: string[];
    detail_level?: number;
    stage_models?: StageModelsConfig;
    code_mode?: boolean;
    finance_mode?: boolean;
    multi_agent?: boolean;
    multi_agent_config?: MultiAgentConfig;
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

export async function planDeepSearch(
  conversationId: string | null | undefined,
  content: string,
  stage_models?: StageModelsConfig,
): Promise<string[]> {
  const url = conversationId ? `/conversations/${conversationId}/deep-search/plan` : "/deep-search/plan";
  const res = await api<{ queries: string[] }>(url, {
    method: "POST",
    body: JSON.stringify({ content, stage_models }),
  });
  return res.queries || [];
}

export async function fetchDeepSearchReports(): Promise<DeepSearchReport[]> {
  return api<DeepSearchReport[]>("/deep-search/reports");
}

export async function fetchDeepSearchReport(id: string): Promise<DeepSearchReport> {
  return api<DeepSearchReport>(`/deep-search/reports/${id}`);
}

export async function deleteDeepSearchReport(id: string): Promise<void> {
  return api<void>(`/deep-search/reports/${id}`, {
    method: "DELETE",
  });
}

export async function createReportFromMessage(messageId: string): Promise<DeepSearchReport> {
  return api<DeepSearchReport>(`/deep-search/reports/from-message/${messageId}`, {
    method: "POST",
  });
}

export async function planLearnMode(
  conversationId: string | null | undefined,
  content: string,
  stage_models?: StageModelsConfig,
): Promise<string[]> {
  const url = conversationId ? `/conversations/${conversationId}/learn/plan` : "/learn/plan";
  const res = await api<{ queries: string[] }>(url, {
    method: "POST",
    body: JSON.stringify({ content, stage_models }),
  });
  return res.queries || [];
}

export async function fetchLearnReports(): Promise<LearnReport[]> {
  return api<LearnReport[]>("/learn/reports");
}

export async function fetchLearnReport(id: string): Promise<LearnReport> {
  return api<LearnReport>(`/learn/reports/${id}`);
}

export async function deleteLearnReport(id: string): Promise<void> {
  return api<void>(`/learn/reports/${id}`, {
    method: "DELETE",
  });
}

export async function createLearnReportFromMessage(messageId: string): Promise<LearnReport> {
  return api<LearnReport>(`/learn/reports/from-message/${messageId}`, {
    method: "POST",
  });
}

export async function fetchGeneratedSounds(type?: "sound_effect" | "music"): Promise<GeneratedSound[]> {
  const query = type ? `?type=${type}` : "";
  return api<GeneratedSound[]>(`/sounds${query}`);
}

export async function createGeneratedSound(payload: {
  prompt: string;
  sound_type?: "sound_effect" | "music";
  duration_seconds?: number | null;
  prompt_influence?: number | null;
  output_format?: string;
  loop?: boolean;
  instrumental?: boolean | null;
  model_id?: string | null;
}): Promise<GeneratedSound> {
  return api<GeneratedSound>("/sounds", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function improveSoundPrompt(payload: {
  prompt: string;
  sound_type?: "sound_effect" | "music";
  style_keywords?: string;
  duration_hint?: number | null;
  loop?: boolean;
  instrumental?: boolean | null;
  model?: string;
}): Promise<{ prompt: string }> {
  return api<{ prompt: string }>("/sounds/improve", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function translateSoundPrompt(payload: {
  prompt: string;
  sound_type?: "sound_effect" | "music";
}): Promise<{ prompt: string }> {
  return api<{ prompt: string }>("/sounds/translate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteGeneratedSound(id: string): Promise<void> {
  return api<void>(`/sounds/${id}`, {
    method: "DELETE",
  });
}

export type StudyMaterialRequest = {
  kind: "flashcards" | "quiz";
  count: number;
  difficulty: "easy" | "medium" | "hard";
  topic?: string;
};

export type StudyMaterialResponse = {
  kind: "flashcards" | "quiz";
  count: number;
  difficulty: "easy" | "medium" | "hard";
  topic: string;
  flashcards: Flashcard[];
  questions: QuizQuestion[];
};

export async function generateStudyMaterial(
  conversationId: string,
  payload: StudyMaterialRequest,
  init?: RequestInit
): Promise<StudyMaterialResponse> {
  return api<StudyMaterialResponse>(`/conversations/${conversationId}/study`, {
    method: "POST",
    body: JSON.stringify(payload),
    ...init,
  });
}

export type GeneratedPersona = {
  name: string;
  role: string;
  avatar: string;
  color: string;
  prompt: string;
  suggested_model?: string;
};

export async function generateAiPersona(payload: {
  name_or_concept: string;
  model?: string;
}): Promise<GeneratedPersona> {
  return api<GeneratedPersona>("/agent-teams/generate-persona", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type EodBar = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type FinancialStats = {
  valuation: {
    market_cap?: string;
    market_cap_raw?: number | null;
    pe_trailing?: string;
    pe_forward?: string;
    peg_ratio?: string;
    price_to_book?: string;
    enterprise_value?: string;
    ev_to_ebitda?: string;
    beta?: string;
    trailing_eps?: string;
    forward_eps?: string;
    dividend_rate?: string;
    dividend_yield?: string;
    payout_ratio?: string;
    w52_high?: string;
    w52_low?: string;
  };
  profitability: {
    total_revenue?: string;
    total_revenue_raw?: number | null;
    revenue_growth?: string;
    gross_margin?: string;
    operating_margin?: string;
    profit_margin?: string;
    ebitda?: string;
    ebitda_raw?: number | null;
    net_income?: string;
    free_cashflow?: string;
    operating_cashflow?: string;
    roe?: string;
    roa?: string;
  };
  balance_sheet: {
    total_cash?: string;
    total_debt?: string;
    debt_to_equity?: string;
    current_ratio?: string;
    quick_ratio?: string;
    book_value?: string;
  };
  analysts: {
    recommendation?: string;
    opinions_count?: number | null;
    target_mean?: string;
    target_high?: string;
    target_low?: string;
    upside_potential_pct?: number | null;
  };
  profile: {
    sector?: string;
    industry?: string;
    country?: string;
    employees?: string;
    website?: string;
    summary?: string;
  };
};

export type FinancialDashboardData = {
  symbol: string;
  eod_ticker: string;
  yahoo_symbol: string;
  short_name: string;
  long_name: string;
  price: number | null;
  currency: string;
  change: number | null;
  change_percent: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  previous_close: number | null;
  volume: number | null;
  exchange: string;
  country?: string | null;
  isin?: string | null;
  has_eod: boolean;
  has_yahoo: boolean;
  eod_bars: EodBar[];
  financial_stats: FinancialStats;
  url_eod: string;
  url_yahoo: string;
};

export async function fetchFinanceDetails(query: string): Promise<FinancialDashboardData> {
  return api<FinancialDashboardData>(`/finance/details?query=${encodeURIComponent(query)}`);
}






