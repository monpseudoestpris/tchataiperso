import type { ResearchActivity } from "./research-activity";

export type SamplingParameters = {
  temperature?: number | null;
  top_p?: number | null;
  top_k?: number | null;
  min_p?: number | null;
  top_a?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  repetition_penalty?: number | null;
  logit_bias?: Record<string, number> | string | null;
  seed?: number | null;
  reasoning?: "none" | "minimal" | "low" | "medium" | "high" | null;
  reasoning_effort?: "none" | "minimal" | "low" | "medium" | "high" | null;
  verbosity?: "low" | "medium" | "high" | null;
};

export type ModelParameterSpec = {
  name: keyof SamplingParameters;
  label: string;
  role?: string;
  description: string;
  hint: string;
  unavailable_label?: string;
  min?: number;
  max?: number;
  step?: number;
  default: number | string | null;
  type: "float" | "int" | "select" | "json";
  options?: { value: string; label: string }[];
  available: boolean;
};

export type ModelParametersResponse = {
  model: string;
  supported_parameters: string[];
  parameters: ModelParameterSpec[];
};

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
  supported_parameters?: string[];
};
export type ImageModel = {
  id: string;
  name: string;
  provider: "ideogram" | "openrouter";
  pricing_text?: string;
  description?: string;
  supported_aspect_ratios?: string[];
  supported_resolutions?: string[];
  is_top?: boolean;
};
export type Config = {
  models: Model[];
  default_model: string;
  image_prompt_model?: string;
  skill_prompt_model?: string;
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
  analysis_mode?: "ocr" | "vision" | "local" | "finance";
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

export type Message = { id: string; role: string; content: string; thought?: string; created_at: string; attachments: Attachment[]; sources: Source[]; deep_search_report_id?: string | null; learn_report_id?: string | null };
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
export type Skill = {
  id: string;
  name: string;
  prompt: string;
  creativity?: number | null;
  sampling_params?: SamplingParameters | null;
  created_at: string;
  updated_at: string;
};
export type BlogCard = {
  title: string;
  text: string;
  url: string;
  source_name: string;
  tag: string;
  color: "blue" | "emerald" | "purple" | "amber" | "rose" | "cyan" | string;
  category?: "news" | "facts" | "images" | "videos" | "tips" | "stats" | "quotes" | "concepts" | string;
  image_url?: string;
  video_url?: string;
  video_embed_url?: string;
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
  categories?: string[];
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

export type PageTopicItem = {
  id: string;
  title: string;
  description: string;
  category: string;
  recommended: boolean;
  detail_level?: number;
  output_format?: "auto" | "text" | "list" | "table" | "cards" | "timeline";
};

export type ProposePageTopicsResponse = {
  suggested_title: string;
  summary: string;
  topics: PageTopicItem[];
};

export type WebPageVersion = {
  id: string;
  page_id: string;
  version_number: number;
  prompt_used: string;
  html_content?: string;
  created_at: string;
};

export type WebPage = {
  id: string;
  user_id: string;
  title: string;
  slug: string;
  public_token: string;
  is_published: boolean;
  created_at: string;
  updated_at: string;
  versions_count: number;
  latest_version_number: number;
  latest_html?: string;
  latest_prompt?: string;
  versions?: WebPageVersion[];
};

export type Conversation = {
  id: string;
  title: string;
  model: string;
  theme?: string;
  keywords?: string[];
  topic_space_id?: string | null;
  creativity?: number | null;
  sampling_params?: SamplingParameters | null;
  created_at: string;
  updated_at: string;
  summary?: string | null;
  messages?: Message[];
  skills?: Skill[];
};
export type TopicType = "learning" | "project" | "interest" | "personal";
export type TopicMemoryStatus = "discussed" | "in_progress" | "needs_review" | "provisional_mastery" | "validated";

export type TopicMemory = {
  id: string;
  topic_space_id: string;
  fact: string;
  category: string;
  status: TopicMemoryStatus;
  confidence: number;
  source_message_id?: string | null;
  user_verified: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

export type TopicEvent = {
  id: string;
  topic_space_id: string;
  event_type: string;
  title: string;
  details: Record<string, any>;
  created_at: string;
};

export type TopicResourceType = "link" | "document" | "note";

export type TopicResource = {
  id: string;
  topic_space_id: string;
  title: string;
  resource_type: TopicResourceType;
  url?: string | null;
  content: string;
  created_at: string;
  updated_at: string;
};

export type TopicSpace = {
  id: string;
  user_id: string;
  title: string;
  icon: string;
  topic_type: TopicType;
  objective: string;
  current_resume_context: string;
  suggested_next_step: string;
  created_at: string;
  updated_at: string;
  conversations_count: number;
  memories_count: number;
  resources_count?: number;
  conversations?: Conversation[];
  memories?: TopicMemory[];
  events?: TopicEvent[];
  resources?: TopicResource[];
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
  | { type: "thought"; data: { text: string } }
  | { type: "research_activity"; data: ResearchActivity }
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
        topic_space_update?: {
          topic_id?: string | null;
          title?: string | null;
          icon?: string | null;
          new_memories?: Array<{ fact: string; status: string; category?: string }>;
          resume_context?: string | null;
          suggested_next_step?: string | null;
        } | null;
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
    interaction_id?: string;
    plan_feedback?: string;
    auto_memory_enabled?: boolean;
    creativity?: number | null;
    sampling_params?: SamplingParameters | null;
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
    if (["meta", "status", "thought", "research_activity", "delta", "done", "error"].includes(event)) {
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

export async function createBlog(body: {
  prompt: string;
  title?: string;
  auto_refresh?: boolean;
  theme?: string;
  categories?: string[];
}): Promise<Blog> {
  return api<Blog>("/blogs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateBlog(
  blogId: string,
  body: { title?: string; prompt?: string; auto_refresh?: boolean; theme?: string; categories?: string[] },
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

export type SearxngImageResult = {
  title: string;
  img_src: string;
  thumbnail_src: string;
  url: string;
  source: string;
};

export async function searchBlogImages(query: string): Promise<SearxngImageResult[]> {
  return api<SearxngImageResult[]>(`/blogs/search-images?q=${encodeURIComponent(query)}`);
}

export type SearxngVideoResult = {
  title: string;
  url: string;
  video_url: string;
  video_embed_url: string;
  thumbnail_url: string;
  image_url: string;
  content: string;
  source: string;
};

export async function searchBlogVideos(query: string): Promise<SearxngVideoResult[]> {
  return api<SearxngVideoResult[]>(`/blogs/search-videos?q=${encodeURIComponent(query)}`);
}

export async function updateBlogPostCards(blogId: string, postId: string, cards: BlogCard[]): Promise<BlogPost> {
  return api<BlogPost>(`/blogs/${blogId}/posts/${postId}`, {
    method: "PATCH",
    body: JSON.stringify({ cards }),
  });
}

export async function fetchWebPages(): Promise<WebPage[]> {
  return api<WebPage[]>("/pages");
}

export async function fetchWebPage(pageId: string): Promise<WebPage> {
  return api<WebPage>(`/pages/${pageId}`);
}

export async function proposeWebPageTopics(payload: {
  prompt: string;
  title?: string;
  conversation_id?: string;
  page_type?: string;
  target_audience?: string;
  author_persona?: string;
  visual_description?: string;
  model?: string;
}): Promise<ProposePageTopicsResponse> {
  return api<ProposePageTopicsResponse>("/pages/propose-topics", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createWebPage(payload: {
  prompt: string;
  title?: string;
  conversation_id?: string;
  model?: string;
  page_type?: string;
  target_audience?: string;
  author_persona?: string;
  visual_description?: string;
  creative_freedom?: "low" | "medium" | "high";
  orientation?: "portrait" | "landscape";
  layout_style?: "tabs" | "single_page" | "print_sheet" | "auto";
  text_density?: number;
  interactivity?: "auto" | "high" | "none";
  include_quiz?: boolean;
  include_svg?: boolean;
  theme_palette?: string;
  visual_style?: string;
  animation_engine?: "auto" | "both" | "aos" | "gsap" | "none";
  font_family?: string;
  text_effects?: string[];
  selected_topics?: PageTopicItem[];
}): Promise<WebPage> {
  return api<WebPage>("/pages", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateWebPage(
  pageId: string,
  payload: { title?: string; is_published?: boolean }
): Promise<WebPage> {
  return api<WebPage>(`/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteWebPage(pageId: string): Promise<void> {
  return api<void>(`/pages/${pageId}`, {
    method: "DELETE",
  });
}

export async function refineWebPage(
  pageId: string,
  payload: { instruction: string; model?: string }
): Promise<WebPage> {
  return api<WebPage>(`/pages/${pageId}/refine`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function restoreWebPageVersion(
  pageId: string,
  versionId: string
): Promise<WebPage> {
  return api<WebPage>(`/pages/${pageId}/versions/${versionId}/restore`, {
    method: "POST",
  });
}


export type PlanResearchResponse = {
  queries: string[];
  plan_text?: string;
  interaction_id?: string;
};

export async function planDeepSearch(
  conversationId: string | null | undefined,
  content: string,
  stage_models?: StageModelsConfig,
  model?: string,
  interaction_id?: string,
): Promise<PlanResearchResponse> {
  const url = conversationId ? `/conversations/${conversationId}/deep-search/plan` : "/deep-search/plan";
  const res = await api<PlanResearchResponse>(url, {
    method: "POST",
    body: JSON.stringify({ content, stage_models, model, interaction_id }),
  });
  return {
    queries: res.queries || [],
    plan_text: res.plan_text,
    interaction_id: res.interaction_id,
  };
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
  model?: string,
  interaction_id?: string,
): Promise<PlanResearchResponse> {
  const url = conversationId ? `/conversations/${conversationId}/learn/plan` : "/learn/plan";
  const res = await api<PlanResearchResponse>(url, {
    method: "POST",
    body: JSON.stringify({ content, stage_models, model, interaction_id }),
  });
  return {
    queries: res.queries || [],
    plan_text: res.plan_text,
    interaction_id: res.interaction_id,
  };
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

export type ClozeTestItem = {
  id: number;
  sentence: string;
  text_with_blanks: string;
  missing_words: string[];
  hints?: string[];
  options?: string[];
  explanation?: string;
};

export type StudyMaterialRequest = {
  kind: "flashcards" | "quiz" | "cloze" | "all";
  count: number;
  difficulty: "easy" | "medium" | "hard";
  topic?: string;
  course_text?: string;
  conversation_id?: string;
};

export type StudyMaterialResponse = {
  kind: "flashcards" | "quiz" | "cloze" | "all";
  count: number;
  difficulty: "easy" | "medium" | "hard";
  topic: string;
  flashcards: Flashcard[];
  questions: QuizQuestion[];
  cloze_items?: ClozeTestItem[];
};

export async function generateStudyMaterial(
  conversationId: string | null | undefined,
  payload: StudyMaterialRequest,
  init?: RequestInit
): Promise<StudyMaterialResponse> {
  const url = conversationId ? `/conversations/${conversationId}/study` : "/study/generate";
  return api<StudyMaterialResponse>(url, {
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

export type StatementRow = { key: string; label: string; values: (number | null)[] };
export type StatementRatio = StatementRow & { format: "pct" | "x" };
export type StatementPeriod = {
  dates: string[];
  income: StatementRow[];
  balance: StatementRow[];
  cashflow: StatementRow[];
  ratios: StatementRatio[];
};
export type FinancialStatements = { symbol: string; annual: StatementPeriod; quarterly: StatementPeriod };

export async function fetchFinanceStatements(symbol: string): Promise<FinancialStatements> {
  return api<FinancialStatements>(`/finance/statements?symbol=${encodeURIComponent(symbol)}`);
}

export type FinanceRange = "1d" | "1w" | "1m" | "3m" | "6m" | "1y" | "2y" | "5y" | "max";

export async function fetchFinanceDetails(
  query: string,
  range: FinanceRange = "1m",
): Promise<FinancialDashboardData> {
  return api<FinancialDashboardData>(
    `/finance/details?query=${encodeURIComponent(query)}&range=${range}`,
  );
}

export async function fetchTopics(): Promise<TopicSpace[]> {
  return api<TopicSpace[]>("/topics");
}

export async function createTopic(data: {
  title: string;
  icon?: string;
  topic_type?: TopicType;
  objective?: string;
}): Promise<TopicSpace> {
  return api<TopicSpace>("/topics", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function fetchTopic(id: string): Promise<TopicSpace> {
  return api<TopicSpace>(`/topics/${id}`);
}

export async function updateTopic(id: string, data: {
  title?: string;
  icon?: string;
  topic_type?: TopicType;
  objective?: string;
  current_resume_context?: string;
  suggested_next_step?: string;
}): Promise<TopicSpace> {
  return api<TopicSpace>(`/topics/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteTopic(id: string): Promise<void> {
  return api<void>(`/topics/${id}`, { method: "DELETE" });
}

export async function linkConversationToTopic(topicId: string, conversationId: string): Promise<TopicSpace> {
  return api<TopicSpace>(`/topics/${topicId}/conversations/${conversationId}`, { method: "POST" });
}

export async function unlinkConversationFromTopic(topicId: string, conversationId: string): Promise<TopicSpace> {
  return api<TopicSpace>(`/topics/${topicId}/conversations/${conversationId}`, { method: "DELETE" });
}

export async function createTopicMemory(topicId: string, data: {
  fact: string;
  category?: string;
  status?: TopicMemoryStatus;
}): Promise<TopicMemory> {
  return api<TopicMemory>(`/topics/${topicId}/memories`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTopicMemory(topicId: string, memoryId: string, data: {
  fact?: string;
  category?: string;
  status?: TopicMemoryStatus;
  user_verified?: boolean;
  is_archived?: boolean;
}): Promise<TopicMemory> {
  return api<TopicMemory>(`/topics/${topicId}/memories/${memoryId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteTopicMemory(topicId: string, memoryId: string): Promise<void> {
  return api<void>(`/topics/${topicId}/memories/${memoryId}`, { method: "DELETE" });
}

export async function createTopicEvent(topicId: string, data: {
  event_type: string;
  title: string;
  details?: Record<string, any>;
}): Promise<TopicEvent> {
  return api<TopicEvent>(`/topics/${topicId}/events`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function fetchTopicResources(topicId: string): Promise<TopicResource[]> {
  return api<TopicResource[]>(`/topics/${topicId}/resources`);
}

export async function createTopicResource(topicId: string, data: {
  title: string;
  resource_type: TopicResourceType;
  url?: string;
  content?: string;
}): Promise<TopicResource> {
  return api<TopicResource>(`/topics/${topicId}/resources`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTopicResource(topicId: string, resourceId: string, data: Partial<TopicResource>): Promise<TopicResource> {
  return api<TopicResource>(`/topics/${topicId}/resources/${resourceId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteTopicResource(topicId: string, resourceId: string): Promise<void> {
  return api<void>(`/topics/${topicId}/resources/${resourceId}`, { method: "DELETE" });
}







