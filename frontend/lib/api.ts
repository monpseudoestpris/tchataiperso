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
  supports_image_editing?: boolean;
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
export type LayerizeTextBlock = {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  angle?: number;
  font_name?: string;
  font_alternatives?: string[];
  font_size?: number;
  line_height?: number;
  color?: string;
  alignment?: string;
  formatting?: string[];
  role?: string;
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
  edit_action?: string;
  text_blocks?: LayerizeTextBlock[];
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
  use_selected_model?: boolean;
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

export type SavedAgentPersona = {
  id: string;
  name: string;
  role: string;
  category: string;
  avatar: string;
  color: string;
  prompt: string;
  model?: string;
  created_at?: string;
  updated_at?: string;
};

export type AgentTeamsResponse = {
  teams: AgentTeam[];
  personas?: SavedAgentPersona[];
  templates: Array<{
    id: string;
    name: string;
    role: string;
    category?: string;
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
  trends?: string[];
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

import type { BrickExecutionResult, PageBrick } from "./canvas-bricks";
import type { AppDiagram } from "./canvas-diagram";

export type { AppDiagram, BrickExecutionResult, PageBrick };

export type WebPageCanvasFile = {
  path: string;
  language: string;
  content: string;
};

export type WebPageVersion = {
  id: string;
  page_id: string;
  version_number: number;
  prompt_used: string;
  html_content?: string;
  canvas_files?: WebPageCanvasFile[];
  created_at: string;
};

export type WebPage = {
  id: string;
  user_id: string;
  title: string;
  slug: string;
  kind?: "page" | "app";
  bricks?: PageBrick[];
  public_token: string;
  is_published: boolean;
  created_at: string;
  updated_at: string;
  versions_count: number;
  latest_version_number: number;
  latest_html?: string;
  latest_prompt?: string;
  latest_canvas_files?: WebPageCanvasFile[];
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
    followup_questions?: boolean;
    creativity?: number | null;
    sampling_params?: SamplingParameters | null;
    canvas_files?: { path: string; language: string; content: string }[];
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
  layout_style?: string;
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
  kind?: "page" | "app";
  page_type?: string;
  target_audience?: string;
  author_persona?: string;
  visual_description?: string;
  creative_freedom?: "low" | "medium" | "high";
  orientation?: "portrait" | "landscape";
  layout_style?: "tabs" | "single_page" | "print_sheet" | "a4_1p" | "a4_2p" | "cheat_sheet" | "auto";
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
  html_content?: string;
  canvas_files?: WebPageCanvasFile[];
  bricks?: PageBrick[];
}): Promise<WebPage> {
  return api<WebPage>("/pages", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateWebPage(
  pageId: string,
  payload: {
    title?: string;
    is_published?: boolean;
    kind?: "page" | "app";
    bricks?: PageBrick[];
    html_content?: string;
    canvas_files?: WebPageCanvasFile[];
    prompt_used?: string;
  }
): Promise<WebPage> {
  return api<WebPage>(`/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function executePageBrick(payload: {
  page_id?: string;
  brick_id?: string;
  brick?: PageBrick;
  inputs: Record<string, unknown>;
  model?: string;
}): Promise<BrickExecutionResult> {
  return api<BrickExecutionResult>("/pages/bricks/execute", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function proposeAppDiagram(payload: {
  prompt: string;
  title?: string;
  model?: string;
}): Promise<AppDiagram> {
  return api<AppDiagram>("/pages/diagram/propose", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type DiagramInterviewQuestion = {
  id: string;
  question: string;
  options: string[];
};

export type DiagramInterviewResponse = {
  status: "questions" | "ready";
  assistant_message: string;
  selected_brick_ids: string[];
  questions: DiagramInterviewQuestion[];
  diagram: AppDiagram | null;
};

export async function interviewAppDiagram(payload: {
  messages: { role: "user" | "assistant"; content: string }[];
  available_templates?: { templateId: string; name: string; tagline: string }[];
  model?: string;
  force_finalize?: boolean;
}): Promise<DiagramInterviewResponse> {
  return api<DiagramInterviewResponse>("/pages/diagram/interview", {
    method: "POST",
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
  adjusted_close?: number | null;
  raw_close?: number | null;
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

export type WarehouseStats = {
  eod_bars_count?: number;
  annual_periods_count?: number;
  quarterly_periods_count?: number;
  db_size_bytes?: number;
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
  fundamentals_source?: string;
  warehouse_stats?: WarehouseStats;
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
export type EarningsHistoryRow = {
  date: string;
  report_date?: string | null;
  currency?: string | null;
  eps_actual: number | null;
  eps_estimate: number | null;
  eps_difference: number | null;
  surprise_pct: number | null;
};
export type FinancialStatements = {
  symbol: string;
  canonical_symbol?: string;
  currency?: string;
  source_provider?: string;
  source_label?: string;
  cached?: boolean;
  updated_at?: string | null;
  warehouse_stats?: WarehouseStats;
  annual: StatementPeriod;
  quarterly: StatementPeriod;
  earnings_history?: EarningsHistoryRow[];
  highlights?: Record<string, string | number | null>;
};

export async function fetchFinanceStatements(
  symbol: string,
  refresh = false,
): Promise<FinancialStatements> {
  const qs = new URLSearchParams({ symbol });
  if (refresh) qs.set("refresh", "true");
  return api<FinancialStatements>(`/finance/statements?${qs.toString()}`);
}

export type FinanceRange = "1d" | "1w" | "1m" | "3m" | "6m" | "1y" | "2y" | "5y" | "10y" | "max";

export async function fetchFinanceDetails(
  query: string,
  range: FinanceRange = "1m",
  refresh = false,
): Promise<FinancialDashboardData> {
  const qs = new URLSearchParams({ query, range });
  if (refresh) qs.set("refresh", "true");
  return api<FinancialDashboardData>(`/finance/details?${qs.toString()}`);
}

export type DossierMetricRow = {
  key: string;
  label: string;
  format: string;
  values: (number | null)[];
  yoy: (number | null)[];
};

export type DossierScoreCriteria = {
  key: string;
  label: string;
  values: (number | null)[];
  avg?: number;
};

export type FinancialDossier = {
  symbol: string;
  currency: string;
  source_provider: string;
  source_label: string;
  warehouse_stats?: WarehouseStats;
  header: {
    name: string;
    logo_url?: string | null;
    cap_category: string;
    market_cap: number | null;
    dividend_yield_pct: number | null;
    beta: number | null;
    ih_score: number | null;
    ih_quality: string;
    ih_trend: string;
    price_dynamics: string;
    sector?: string | null;
    industry?: string | null;
    employees?: number | null;
    website?: string;
    address?: string;
    isin?: string | null;
    description?: string;
  };
  capital_valuation: {
    shares_outstanding: number | null;
    float_pct: number | null;
    insiders_pct: number | null;
    institutions_pct: number | null;
    short_ratio: number | null;
    short_pct_float: number | null;
    pe_ttm: number | null;
    pe_forward: number | null;
    peg: number | null;
    pb: number | null;
    ev_ebitda: number | null;
    ev_revenue: number | null;
    op_margin_ttm: number | null;
    net_margin_ttm: number | null;
    gross_margin_ttm: number | null;
    roe_ttm: number | null;
    roa_ttm: number | null;
    rev_growth_q_yoy: number | null;
    eps_growth_q_yoy: number | null;
    price: number | null;
    target_price: number | null;
    mma50: number | null;
    mma200: number | null;
    low_52w: number | null;
    high_52w: number | null;
  };
  performance: {
    horizons: { key: string; label: string; pct: number | null }[];
  };
  performance_chart: { date: string; price: number; adj_price: number; index_100: number }[];
  risk: {
    horizons: string[];
    rf_rates_pct?: number[];
    metrics: { key: string; label: string; format: string; group: string; values: (number | null)[] }[];
  };
  stakeholders: {
    analysts: {
      total: number;
      strong_buy: number;
      buy: number;
      hold: number;
      sell: number;
      strong_sell: number;
      target_price: number | null;
      rating: number | null;
    };
    officers: { name: string; title: string; age: number | null }[];
    insiders: {
      date: string;
      name: string;
      relation: string;
      action: string;
      shares: number | null;
      price: number | null;
      amount: number | null;
      signed_amount: number | null;
    }[];
    insiders_net_amount: number | null;
    funds: { name: string; date: string; shares: number | null; weight_pct: number | null; change_pct: number | null }[];
    institutions: { name: string; date: string; shares: number | null; weight_pct: number | null; change_pct: number | null }[];
  };
  annual_tables: {
    years: string[];
    dates: string[];
    summary: DossierMetricRow[];
    profitability: DossierMetricRow[];
    solvency: DossierMetricRow[];
    distribution: DossierMetricRow[];
    efficiency: DossierMetricRow[];
    ih_score: {
      years: string[];
      criteria: DossierScoreCriteria[];
      trend_criteria: DossierScoreCriteria[];
      latest_score: number | null;
      quality_label?: string;
      trend: string;
    };
    piotroski: {
      years: string[];
      criteria: DossierScoreCriteria[];
      scores: number[];
      latest_score: number | null;
    };
    altman: {
      years: string[];
      criteria: DossierScoreCriteria[];
      scores: (number | null)[];
      latest_score: number | null;
    };
  };
  dividends_matrix: {
    years: number[];
    rows: { year: number; months: (number | null)[]; total: number | null }[];
  };
  statements: {
    annual: StatementPeriod;
    quarterly: StatementPeriod;
    earnings_history: EarningsHistoryRow[];
  };
  news?: {
    source: string;
    provider: string;
    updated_at?: string | null;
    items: DossierNewsItem[];
    sentiment_summary?: {
      avg_normalized: number;
      latest_normalized: number;
      latest_date: string;
      article_count: number;
      days_covered: number;
      series: { date: string; normalized: number; count: number }[];
    } | null;
  };
  historical_market_cap?: {
    latest_value: number;
    latest_date: string;
    min_value: number;
    max_value: number;
    points: { date: string; value: number }[];
  } | null;
  earnings_calendar?: {
    report_date: string;
    fiscal_date: string;
    timing: string;
    currency: string;
    estimate: number | null;
    actual: number | null;
    difference: number | null;
    surprise_pct: number | null;
  }[];
  macro_context?: {
    country_iso3: string;
    country_name: string;
    gdp_growth_pct?: { value: number; date: string } | null;
    inflation_pct?: { value: number; date: string } | null;
    unemployment_pct?: { value: number; date: string } | null;
    us_treasury?: {
      date: string;
      rate_52w_pct: number | null;
      rate_13w_pct: number | null;
      rate_4wk_pct: number | null;
      risk_free_pct: number;
    } | null;
  } | null;
  intrinsic_valuation?: IntrinsicValuationPayload | null;
  uncle_stock_scores?: UncleStockScoresPayload | null;
  uncle_stock_catalog?: UncleStockCatalogPayload | null;
  fund_profile?: FundProfileData | null;
  ai_analysis: FinanceAiAnalysisRecord | null;
  ai_history?: FinanceAiAnalysisRecord[];
};

export type FundWeightedEntry = {
  name: string;
  code?: string;
  weight_pct: number | null;
  sector?: string;
  country?: string;
};

export type FundProfileData = {
  is_fund: boolean;
  name: string;
  isin: string | null;
  exchange: string;
  fund_type: string;
  category: string | null;
  fund_family: string | null;
  currency: string | null;
  country: string | null;
  inception_date: string | null;
  expense_ratio_pct: number | null;
  net_assets: number | null;
  yield_pct: number | null;
  morningstar_rating: number | null;
  morningstar_category: string | null;
  beta: number | null;
  description: string | null;
  website: string | null;
  asset_allocation: FundWeightedEntry[];
  sector_weights: FundWeightedEntry[];
  world_regions: FundWeightedEntry[];
  top_holdings: FundWeightedEntry[];
};

export interface UncleStockScoreComponent {
  name: string;
  input: number | string | boolean | null;
  transformed_input: number | string | null;
  weight: number | null;
  contribution: number | null;
}

export interface UncleStockScoreResult {
  id: string;
  name: string;
  category: string;
  unit: string;
  available: boolean;
  raw_score: number | string | null;
  clamped_score: number | string | null;
  normalized_score: number | null;
  final_score: number | string | null;
  display_value: string;
  components: UncleStockScoreComponent[];
  warnings: string[];
  summary: string;
  source_version: string;
}

export interface UncleStockScoreItem {
  id: string;
  name: string;
  category: string;
  unit: string;
  available: boolean;
  verified: UncleStockScoreResult;
  documented: UncleStockScoreResult;
}

export interface UncleStockScoresPayload {
  available: boolean;
  source_version: string;
  summary: {
    advice_verified: string;
    advice_documented: string;
    categories: string;
    uncle_stock_score_verified: number | null;
    uncle_stock_score_documented: number | null;
    quality_score: number | null;
    value_score: number | null;
    financial_health_score: number | null;
    trap_score: number | null;
  };
  items: UncleStockScoreItem[];
}

export interface IntrinsicAggregate {
  intrinsic_value: number;
  price_to_iv: number | null;
  margin_of_safety_pct: number | null;
  weight_used: number;
  weight_max: number;
  methods_used: number;
  methods_total: number;
}

export interface IntrinsicMethodResult {
  id: string;
  name: string;
  category: "weighted" | "complementary";
  weight: number;
  unclestock_value: number | null;
  corrected_value: number | null;
  status_unclestock: "valid" | "excluded" | "unavailable";
  status_corrected: "valid" | "excluded" | "unavailable";
  price_to_iv_unclestock: number | null;
  margin_of_safety_unclestock_pct: number | null;
  price_to_iv_corrected: number | null;
  margin_of_safety_corrected_pct: number | null;
  exclusion_reason?: string | null;
  warnings: string[];
  assumptions: string[];
  intermediates: Record<string, number | string | null>;
}

export interface IntrinsicValuationPayload {
  available: boolean;
  reason?: string;
  currency?: string;
  country_iso3?: string;
  current_price?: number | null;
  shares?: number | null;
  cost_of_capital: Record<string, number | null>;
  growth_inputs?: Record<string, number | null>;
  owner_returns: Record<string, number | null>;
  summary: {
    unclestock: IntrinsicAggregate | null;
    corrected: IntrinsicAggregate | null;
  };
  methods: IntrinsicMethodResult[];
  scenarios: {
    key: string;
    label: string;
    growth_pct: number;
    wacc_pct: number;
    intrinsic_value: number | null;
    margin_of_safety_pct: number | null;
  }[];
  sensitivity: {
    growth_headers_pct: number[];
    rows: {
      wacc_pct: number;
      cells: { growth_pct: number; wacc_pct: number; value: number | null; undervalued: boolean }[];
    }[];
  } | null;
}

export interface UncleStockCatalogSubmetrics {
  yr_avg?: string | null;
  avg_5y?: string | null;
  wavg_5y?: string | null;
  growth_1y?: string | null;
  rcagr_67?: string | null;
  sd_5y?: string | null;
  cv_5y?: string | null;
}

export interface UncleStockCatalogItem {
  id: string;
  category: string;
  section: string;
  name: string;
  formula: string;
  description: string;
  method?: string;
  notes?: string;
  example?: string;
  unit: string;
  available: boolean;
  latest_value: number | null;
  formatted_value: string;
  values_by_year: (number | null)[];
  submetrics?: UncleStockCatalogSubmetrics | null;
  substitution?: string | null;
}

export interface UncleStockCatalogCategory {
  name: string;
  total: number;
  computed: number;
}

export interface UncleStockCatalogPayload {
  total_count: number;
  computed_count: number;
  years: string[];
  categories: UncleStockCatalogCategory[];
  items: UncleStockCatalogItem[];
}

export interface DossierNewsItem {
  title: string;
  url: string;
  source: string;
  published_at: string;
  snippet?: string;
  tags?: string[];
  sentiment?: {
    polarity?: number;
    pos?: number;
    neu?: number;
    neg?: number;
  } | null;
}

export async function fetchFinanceDossier(symbol: string, refresh = false): Promise<FinancialDossier> {
  const qs = new URLSearchParams({ symbol });
  if (refresh) qs.set("refresh", "true");
  return api<FinancialDossier>(`/finance/dossier?${qs.toString()}`);
}

export type FinanceAiAnalysisKind = "expert" | "dossier" | "moat" | "news" | "report";

export type FinanceAiAnalysisRecord = {
  id?: string;
  symbol?: string;
  company_name?: string;
  kind?: FinanceAiAnalysisKind;
  expert_id?: string;
  expert_name?: string;
  model?: string | null;
  question?: string | null;
  verdict?: string;
  conviction?: string;
  horizon?: string;
  markdown: string;
  content_html?: string;
  news_sources?: string[];
  news_articles?: { title: string; url: string; source: string; published_at: string }[];
  created_at?: string | null;
  updated_at?: string | null;
};

export async function analyzeFinanceDossier(
  symbol: string,
  modelId?: string,
): Promise<FinanceAiAnalysisRecord> {
  return api<FinanceAiAnalysisRecord>("/finance/dossier/analyze", {
    method: "POST",
    body: JSON.stringify({ symbol, model_id: modelId || null }),
  });
}

export type FinanceExpertPersona = {
  id: string;
  name: string;
  monogram: string;
  accent: string;
  era_firm: string;
  style: string;
  tagline: string;
  favorite_metrics: string[];
};

export type FinanceExpertOpinion = FinanceAiAnalysisRecord & {
  expert_id: string;
  expert_name: string;
  model: string;
};

export type FinanceExpertsResponse = {
  experts: FinanceExpertPersona[];
  cached_opinions: Record<string, FinanceExpertOpinion>;
  history?: FinanceExpertOpinion[];
};

export async function fetchFinanceExperts(symbol?: string | null): Promise<FinanceExpertsResponse> {
  const qs = new URLSearchParams();
  if (symbol && symbol.trim()) qs.set("symbol", symbol.trim());
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return api<FinanceExpertsResponse>(`/finance/experts${suffix}`);
}

export async function fetchFinanceAiHistory(params?: {
  symbol?: string | null;
  kind?: FinanceAiAnalysisKind | null;
  expertId?: string | null;
  limit?: number;
}): Promise<{ items: FinanceAiAnalysisRecord[] }> {
  const qs = new URLSearchParams();
  if (params?.symbol?.trim()) qs.set("symbol", params.symbol.trim());
  if (params?.kind) qs.set("kind", params.kind);
  if (params?.expertId?.trim()) qs.set("expert_id", params.expertId.trim());
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return api<{ items: FinanceAiAnalysisRecord[] }>(`/finance/ai-history${suffix}`);
}

export async function deleteFinanceAiHistoryItem(analysisId: string): Promise<void> {
  await api<void>(`/finance/ai-history/${encodeURIComponent(analysisId)}`, { method: "DELETE" });
}

export async function requestFinanceExpertOpinion(payload: {
  symbol: string;
  expertId: string;
  modelId?: string | null;
  question?: string | null;
}): Promise<FinanceExpertOpinion> {
  return api<FinanceExpertOpinion>("/finance/dossier/expert", {
    method: "POST",
    body: JSON.stringify({
      symbol: payload.symbol,
      expert_id: payload.expertId,
      model_id: payload.modelId || null,
      question: payload.question?.trim() || null,
    }),
  });
}

export type PrincipalIndexInfo = {
  code: string;
  tier?: "major" | "minor";
  name: string;
  region: string;
  flag: string;
  currency: string;
  eod_ticker: string;
  yahoo_symbol: string;
  description: string;
  constituents_count: number;
  last_price: number | null;
  change_pct: number | null;
  as_of: string | null;
};

export type WarehouseOverview = {
  instruments_count: number;
  eod_bars_count: number;
  fundamental_facts_count: number;
  snapshots_count: number;
  index_constituents_count: number;
  db_size_bytes: number;
};

export type IndexConstituent = {
  symbol: string;
  eod_ticker: string;
  yahoo_symbol: string;
  name: string;
  sector: string;
  industry: string;
  exchange: string;
  weight_pct: number | null;
  position: number;
  cached_in_warehouse: boolean;
  currency?: string | null;
  price?: number | null;
  change_1d_pct?: number | null;
  sparkline?: number[];
};

export type IndexCompositionResponse = {
  index: PrincipalIndexInfo & {
    cached_count: number;
    synced_today_count?: number;
    source: string;
    sectors: string[];
  };
  constituents: IndexConstituent[];
};

export type CatalogSearchItem = {
  symbol: string;
  eod_ticker: string;
  yahoo_symbol: string;
  name: string;
  exchange: string;
  sector: string;
  index_code: string | null;
  cached: boolean;
};

export async function fetchPrincipalIndices(
  includeQuotes = true,
  tier: "major" | "minor" | "all" = "major",
): Promise<{ indices: PrincipalIndexInfo[]; warehouse: WarehouseOverview }> {
  const qs = new URLSearchParams();
  if (!includeQuotes) qs.set("include_quotes", "false");
  if (tier !== "major") qs.set("tier", tier);
  const suffix = qs.toString();
  return api<{ indices: PrincipalIndexInfo[]; warehouse: WarehouseOverview }>(
    `/finance/indices${suffix ? `?${suffix}` : ""}`,
  );
}

export type EodhdIndxCatalogItem = {
  code: string;
  eod_ticker: string;
  name: string;
  country: string;
  currency: string;
  type: string;
};

export type EodhdIndxCatalogResponse = {
  total: number;
  matched: number;
  source: string;
  items: EodhdIndxCatalogItem[];
};

export async function fetchEodhdIndxCatalog(
  query = "",
  limit = 120,
  refresh = false,
): Promise<EodhdIndxCatalogResponse> {
  const qs = new URLSearchParams();
  if (query.trim()) qs.set("q", query.trim());
  if (limit !== 120) qs.set("limit", String(limit));
  if (refresh) qs.set("refresh", "true");
  const suffix = qs.toString();
  return api<EodhdIndxCatalogResponse>(`/finance/indices/eodhd-catalog${suffix ? `?${suffix}` : ""}`);
}

export async function fetchIndexComposition(
  indexCode: string,
  refresh = false,
): Promise<IndexCompositionResponse> {
  const qs = new URLSearchParams();
  if (refresh) qs.set("refresh", "true");
  const suffix = qs.toString();
  return api<IndexCompositionResponse>(
    `/finance/indices/${encodeURIComponent(indexCode)}${suffix ? `?${suffix}` : ""}`,
  );
}

export async function searchFinanceCatalog(
  query: string,
  limit = 25,
): Promise<CatalogSearchItem[]> {
  const qs = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await api<{ items: CatalogSearchItem[] }>(`/finance/catalog/search?${qs.toString()}`);
  return res.items || [];
}

export type IndexPerformanceItem = IndexConstituent & {
  currency: string;
  price: number | null;
  change_1d_pct: number | null;
  change_1w_pct: number | null;
  change_1m_pct: number | null;
  change_3m_pct: number | null;
  change_ytd_pct: number | null;
  change_1y_pct: number | null;
  as_of: string | null;
  bars_count: number;
  eod_synced_date?: string | null;
  eod_synced_at?: string | null;
  loaded_from_cache?: boolean;
};

export type IndexPerformancesSummary = {
  total_count: number;
  loaded_count: number;
  from_cache_count?: number;
  fetched_count?: number;
  synced_today_count?: number;
  last_synced_at?: string | null;
  avg_1d_pct: number | null;
  avg_1w_pct: number | null;
  avg_1m_pct: number | null;
  avg_3m_pct: number | null;
  avg_ytd_pct: number | null;
  avg_1y_pct: number | null;
  gainers_1d: number;
  losers_1d: number;
  gainers_1y: number;
  losers_1y: number;
};

export type IndexPerformancesResponse = {
  index: PrincipalIndexInfo & {
    cached_count: number;
    synced_today_count?: number;
    source?: string;
    sectors?: string[];
  };
  summary: IndexPerformancesSummary;
  items: IndexPerformanceItem[];
  warehouse: WarehouseOverview;
};

export type ImportIndexWatchlistResponse = {
  list: FinanceWatchlistMeta;
  added_count: number;
  total_constituents: number;
};

export async function fetchCachedIndexPerformances(
  indexCode: string,
): Promise<IndexPerformancesResponse> {
  return api<IndexPerformancesResponse>(
    `/finance/indices/${encodeURIComponent(indexCode)}/performances`,
  );
}

export async function loadIndexPerformances(
  indexCode: string,
  refresh = false,
): Promise<IndexPerformancesResponse> {
  const qs = refresh ? "?refresh=true" : "";
  return api<IndexPerformancesResponse>(
    `/finance/indices/${encodeURIComponent(indexCode)}/performances${qs}`,
    { method: "POST" },
  );
}

export async function importIndexToWatchlist(
  indexCode: string,
  options?: { listId?: string | null; listName?: string | null },
): Promise<ImportIndexWatchlistResponse> {
  return api<ImportIndexWatchlistResponse>(
    `/finance/indices/${encodeURIComponent(indexCode)}/watchlist`,
    {
      method: "POST",
      body: JSON.stringify({
        list_id: options?.listId || null,
        list_name: options?.listName || null,
      }),
    },
  );
}

export type EodhdEufundItem = {
  symbol: string;
  eod_ticker: string;
  name: string;
  isin: string | null;
  fund_family?: string | null;
  country: string;
  currency: string;
  type: string;
  exchange: string;
  previous_close?: number | null;
  cached_in_warehouse: boolean;
};

export type ExchangeCatalogItem = EodhdEufundItem;

export type SupportedExchangeInfo = {
  code: string;
  label: string;
  description: string;
  total: number;
  synced_at: string | null;
};

export type EodhdEufundCatalogResponse = {
  exchange: string;
  supported_exchanges?: SupportedExchangeInfo[];
  total: number;
  matched: number;
  offset: number;
  limit: number;
  source: string;
  synced_at: string | null;
  currencies: string[];
  countries: string[];
  types?: string[];
  fund_families?: string[];
  items: EodhdEufundItem[];
};

export type EodhdFundSearchResponse = {
  query: string;
  source: string;
  items: EodhdEufundItem[];
};

export async function fetchExchangeCatalog(params?: {
  exchange?: string;
  q?: string;
  currency?: string;
  country?: string;
  type?: string;
  fundFamily?: string;
  limit?: number;
  offset?: number;
  refresh?: boolean;
}): Promise<EodhdEufundCatalogResponse> {
  const qs = new URLSearchParams();
  if (params?.exchange?.trim()) qs.set("exchange", params.exchange.trim());
  if (params?.q?.trim()) qs.set("q", params.q.trim());
  if (params?.currency?.trim()) qs.set("currency", params.currency.trim());
  if (params?.country?.trim()) qs.set("country", params.country.trim());
  if (params?.type?.trim()) qs.set("type", params.type.trim());
  if (params?.fundFamily?.trim()) qs.set("fund_family", params.fundFamily.trim());
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null && params.offset > 0) qs.set("offset", String(params.offset));
  if (params?.refresh) qs.set("refresh", "true");
  const suffix = qs.toString();
  return api<EodhdEufundCatalogResponse>(`/finance/catalog/exchanges${suffix ? `?${suffix}` : ""}`);
}

export async function syncExchangeCatalog(
  exchange = "ALL",
  refresh = true,
): Promise<{
  codes: string[];
  fetched_exchanges: number;
  exchanges: Record<string, { total: number; source: string; synced_at: string | number | null }>;
}> {
  const qs = new URLSearchParams({ exchange, refresh: String(refresh) });
  return api(`/finance/catalog/exchanges/sync?${qs.toString()}`, { method: "POST" });
}

export type FinanceSyncRunSummary = {
  skipped?: boolean;
  reason?: string;
  principal_indices_count?: number;
  indx_catalog_total?: number;
  indices?: Record<string, { loaded_count: number; from_cache_count: number; fetched_count: number }>;
  watchlist_items_count?: number;
  exchanges?: Record<string, { total: number; source: string; synced_at: string | null }>;
  errors?: string[];
};

export type FinanceSyncPreferences = {
  enabled: boolean;
  principal_indices: boolean;
  indx_catalog: boolean;
  index_codes: string[];
  watchlists: boolean;
  exchanges: string[];
  last_run_at: string | null;
  last_status: FinanceSyncRunSummary | null;
  updated_at: string | null;
};

export type FinanceSyncAvailableIndex = {
  code: string;
  name: string;
  flag: string;
  tier: "major" | "minor";
  region: string;
  constituents_count: number;
};

export type FinanceSyncStateResponse = {
  preferences: FinanceSyncPreferences;
  available_indices: FinanceSyncAvailableIndex[];
  available_exchanges: SupportedExchangeInfo[];
  summary?: FinanceSyncRunSummary;
};

export async function fetchFinanceSyncPreferences(): Promise<FinanceSyncStateResponse> {
  return api<FinanceSyncStateResponse>("/finance/sync-preferences");
}

export async function updateFinanceSyncPreferences(
  prefs: Pick<
    FinanceSyncPreferences,
    "enabled" | "principal_indices" | "indx_catalog" | "index_codes" | "watchlists" | "exchanges"
  >,
): Promise<FinanceSyncStateResponse> {
  return api<FinanceSyncStateResponse>("/finance/sync-preferences", {
    method: "PUT",
    body: JSON.stringify(prefs),
  });
}

export async function runFinanceSyncNow(refresh = false): Promise<FinanceSyncStateResponse> {
  const qs = refresh ? "?refresh=true" : "";
  return api<FinanceSyncStateResponse>(`/finance/sync-preferences/run${qs}`, {
    method: "POST",
  });
}

export async function fetchEodhdEufundCatalog(params?: {
  q?: string;
  currency?: string;
  country?: string;
  limit?: number;
  offset?: number;
  refresh?: boolean;
}): Promise<EodhdEufundCatalogResponse> {
  const qs = new URLSearchParams();
  if (params?.q?.trim()) qs.set("q", params.q.trim());
  if (params?.currency?.trim()) qs.set("currency", params.currency.trim());
  if (params?.country?.trim()) qs.set("country", params.country.trim());
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null && params.offset > 0) qs.set("offset", String(params.offset));
  if (params?.refresh) qs.set("refresh", "true");
  const suffix = qs.toString();
  return api<EodhdEufundCatalogResponse>(`/finance/funds/eufund${suffix ? `?${suffix}` : ""}`);
}

export async function searchEodhdFundsLive(
  query: string,
  limit = 25,
): Promise<EodhdFundSearchResponse> {
  const qs = new URLSearchParams({ q: query.trim(), limit: String(limit) });
  return api<EodhdFundSearchResponse>(`/finance/funds/search?${qs.toString()}`);
}

export type FinanceWatchlistMeta = {
  id: string;
  name: string;
  position: number;
  items_count: number;
  created_at?: string;
  updated_at?: string;
};

export type WatchlistItem = {
  id: string;
  list_id?: string | null;
  symbol: string;
  yahoo_symbol: string;
  eod_ticker: string;
  name: string;
  exchange: string;
  currency: string;
  note?: string;
  position: number;
  price: number | null;
  change_1d_pct: number | null;
  change_1w_pct: number | null;
  change_1m_pct: number | null;
  change_3m_pct: number | null;
  change_ytd_pct?: number | null;
  change_1y_pct: number | null;
  eod_synced_date?: string | null;
  loaded_from_cache?: boolean;
};

export type WatchlistStateResponse = {
  active_list_id: string;
  lists: FinanceWatchlistMeta[];
  items: WatchlistItem[];
};

export async function fetchWatchlistState(
  seedDefaults = false,
  includeQuotes = true,
  listId?: string | null,
  refresh = false,
): Promise<WatchlistStateResponse> {
  const qs = new URLSearchParams({
    seed_defaults: String(seedDefaults),
    include_quotes: String(includeQuotes),
  });
  if (listId) qs.set("list_id", listId);
  if (refresh) qs.set("refresh", "true");
  return api<WatchlistStateResponse>(`/finance/watchlist?${qs.toString()}`);
}

export async function fetchWatchlist(seedDefaults = false, includeQuotes = true): Promise<WatchlistItem[]> {
  const res = await fetchWatchlistState(seedDefaults, includeQuotes);
  return res.items || [];
}

export async function createWatchlist(name: string): Promise<FinanceWatchlistMeta> {
  return api<FinanceWatchlistMeta>("/finance/watchlists", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renameWatchlist(listId: string, name: string): Promise<FinanceWatchlistMeta> {
  return api<FinanceWatchlistMeta>(`/finance/watchlists/${encodeURIComponent(listId)}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteWatchlist(listId: string): Promise<void> {
  return api<void>(`/finance/watchlists/${encodeURIComponent(listId)}`, { method: "DELETE" });
}

export async function addWatchlistItem(query: string, listId?: string | null): Promise<WatchlistItem> {
  return api<WatchlistItem>("/finance/watchlist", {
    method: "POST",
    body: JSON.stringify({ query, list_id: listId || null }),
  });
}

export async function seedDefaultWatchlist(listId?: string | null): Promise<WatchlistItem[]> {
  const qs = listId ? `?list_id=${encodeURIComponent(listId)}` : "";
  const res = await api<{ items: WatchlistItem[] }>(`/finance/watchlist/seed-defaults${qs}`, {
    method: "POST",
  });
  return res.items || [];
}

export async function deleteWatchlistItem(itemId: string): Promise<void> {
  return api<void>(`/finance/watchlist/${itemId}`, { method: "DELETE" });
}

export async function updateWatchlistItemNote(itemId: string, note: string): Promise<WatchlistItem> {
  return api<WatchlistItem>(`/finance/watchlist/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    body: JSON.stringify({ note }),
  });
}

export type CustomIndicatorGuideLine = {
  value: number;
  color: string;
};

export type CustomIndicator = {
  id: string;
  name: string;
  formula: string;
  pane: "overlay" | "oscillator";
  series_type: "line" | "histogram" | "dots";
  color: string;
  guide_lines: CustomIndicatorGuideLine[];
  enabled_by_default: boolean;
  created_at: string;
  updated_at: string;
};

export async function fetchCustomIndicators(): Promise<CustomIndicator[]> {
  const res = await api<{ items: CustomIndicator[] }>("/finance/indicators");
  return res.items || [];
}

export async function createCustomIndicator(payload: {
  name: string;
  formula: string;
  pane: "overlay" | "oscillator";
  series_type: "line" | "histogram" | "dots";
  color: string;
  guide_lines: CustomIndicatorGuideLine[];
  enabled_by_default?: boolean;
}): Promise<CustomIndicator> {
  return api<CustomIndicator>("/finance/indicators", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateCustomIndicator(
  indicatorId: string,
  payload: Partial<{
    name: string;
    formula: string;
    pane: "overlay" | "oscillator";
    series_type: "line" | "histogram" | "dots";
    color: string;
    guide_lines: CustomIndicatorGuideLine[];
    enabled_by_default: boolean;
  }>,
): Promise<CustomIndicator> {
  return api<CustomIndicator>(`/finance/indicators/${indicatorId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteCustomIndicator(indicatorId: string): Promise<void> {
  return api<void>(`/finance/indicators/${indicatorId}`, { method: "DELETE" });
}

export type StockNewsArticle = {
  title: string;
  url: string;
  source: string;
  published_at: string;
  snippet?: string;
  tags?: string[];
  sentiment?: {
    polarity?: number;
    pos?: number;
    neu?: number;
    neg?: number;
  } | null;
};

export type StockNewsFeed = {
  source: string;
  provider: string;
  updated_at: string | null;
  items: StockNewsArticle[];
};

export type StockNewsEntry = {
  id: string;
  symbol: string;
  company_name: string;
  search_query: string;
  summary_markdown: string;
  articles: StockNewsArticle[];
  created_at: string;
};

export async function fetchStockNewsWithFeed(
  symbol?: string,
  refresh = false,
): Promise<{ items: StockNewsEntry[]; feed: StockNewsFeed | null }> {
  const qs = new URLSearchParams();
  if (symbol) qs.set("symbol", symbol);
  if (refresh) qs.set("refresh", "true");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await api<{ items: StockNewsEntry[]; feed?: StockNewsFeed | null }>(`/finance/news${suffix}`);
  return {
    items: res.items || [],
    feed: res.feed ?? null,
  };
}

export async function fetchStockNews(symbol?: string): Promise<StockNewsEntry[]> {
  const res = await fetchStockNewsWithFeed(symbol, false);
  return res.items;
}

export async function searchStockNews(payload: {
  symbol: string;
  company_name?: string;
  focus_query?: string;
}): Promise<StockNewsEntry> {
  return api<StockNewsEntry>("/finance/news/search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteStockNews(newsId: string): Promise<void> {
  return api<void>(`/finance/news/${newsId}`, { method: "DELETE" });
}

export type QuarterlyReportTable = {
  index: number;
  page: number;
  title: string;
  markdown: string;
  rows_count: number;
  cols_count: number;
};

export type QuarterlyReport = {
  id: string;
  symbol: string;
  company_name: string;
  title: string;
  period_label: string;
  source_type: "pdf" | "pdf-ocr" | "docx" | "text" | string;
  filename: string;
  extracted_chars: number;
  page_count?: number;
  tables_count?: number;
  summary_markdown: string;
  key_metrics: Record<string, string>;
  has_file: boolean;
  created_at: string;
  extracted_text?: string;
  extracted_tables?: QuarterlyReportTable[];
};

export async function fetchQuarterlyReports(symbol?: string): Promise<QuarterlyReport[]> {
  const q = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  const res = await api<{ items: QuarterlyReport[] }>(`/finance/reports${q}`);
  return res.items || [];
}

export async function fetchQuarterlyReport(reportId: string): Promise<QuarterlyReport> {
  return api<QuarterlyReport>(`/finance/reports/${reportId}`);
}

export async function importQuarterlyReport(formData: FormData): Promise<QuarterlyReport> {
  const response = await fetch("/api/finance/reports", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw await responseError(response);
  }
  return (await response.json()) as QuarterlyReport;
}

export async function deleteQuarterlyReport(reportId: string): Promise<void> {
  return api<void>(`/finance/reports/${reportId}`, { method: "DELETE" });
}

export type MoatPillar = {
  name: string;
  status: "strong" | "moderate" | "absent";
  explanation: string;
};

export type MoatQuantitativeSignal = {
  label: string;
  value: string;
  verdict: "favorable" | "neutral" | "weak";
  reason: string;
};

export type StockMoatAnalysis = {
  id: string;
  symbol: string;
  company_name: string;
  moat_rating: "wide" | "narrow" | "none";
  moat_score: number;
  pillars: MoatPillar[];
  strengths: string[];
  weaknesses: string[];
  quantitative_signals: MoatQuantitativeSignal[];
  summary_markdown: string;
  created_at: string;
};

export async function fetchStockMoats(symbol?: string): Promise<StockMoatAnalysis[]> {
  const qs = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  const res = await api<{ items: StockMoatAnalysis[] }>(`/finance/moat${qs}`);
  return res.items || [];
}

export async function analyzeStockMoat(payload: {
  symbol: string;
  company_name?: string;
  custom_focus?: string;
  financial_stats?: FinancialStats;
}): Promise<StockMoatAnalysis> {
  return api<StockMoatAnalysis>("/finance/moat/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteStockMoat(moatId: string): Promise<void> {
  return api<void>(`/finance/moat/${moatId}`, { method: "DELETE" });
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

export type HermesToolName = "web_search" | "memory" | "skills" | "code_execution" | "create_page";

export type HermesToolSpec = {
  id: HermesToolName;
  name: string;
  description: string;
  hermes_ref: string;
};

export type HermesPreset = {
  id: string;
  title: string;
  description: string;
  prompt: string;
  tools: HermesToolName[];
};

export type HermesExecutionMode = "gateway" | "local_autonomous" | "demo" | "offline" | "disabled";
export type HermesEnginePreference = "auto" | "local_autonomous" | "gateway";

export type HermesStatusResponse = {
  enabled: boolean;
  mode: HermesExecutionMode;
  provider?: string;
  gateway_reachable: boolean;
  gateway_url: string;
  gateway_models: string[];
  default_model: string;
  tools: HermesToolSpec[];
  presets: HermesPreset[];
  default_soul: string;
  user_memories_count: number;
  user_skills_count: number;
};

export type HermesStepEvent = {
  type: "step";
  id: string;
  tool: string;
  title: string;
  status: "running" | "done" | "error";
  detail?: string;
};

export type HermesSuggestedSkill = {
  name: string;
  prompt: string;
};

export type HermesRunMetrics = {
  llm_calls: number;
  tool_calls: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number | null;
  duration_ms?: number;
  stop_reason?: string;
};

export type HermesCreatedPage = {
  id: string;
  title: string;
  slug: string;
  page_type: string;
  is_published: boolean;
};

export type HermesArtifactsEvent = {
  type: "artifacts";
  sources: Source[];
  created_pages?: HermesCreatedPage[];
  suggested_skill: HermesSuggestedSkill | null;
  suggested_memory: string | null;
  metrics?: HermesRunMetrics;
};

export type HermesStreamEvent =
  | { type: "meta"; data: { mode: HermesExecutionMode; session_id: string; model: string; gateway_url?: string } }
  | { type: "step"; data: HermesStepEvent }
  | { type: "thought"; data: { text: string } }
  | { type: "delta"; data: { text: string } }
  | { type: "artifacts"; data: HermesArtifactsEvent }
  | { type: "done"; data: { content: string; metrics?: HermesRunMetrics } };

export async function fetchHermesStatus(): Promise<HermesStatusResponse> {
  return api<HermesStatusResponse>("/hermes/status");
}

export async function streamHermesRun(
  body: {
    prompt: string;
    model?: string;
    execution_mode?: HermesEnginePreference;
    session_id?: string;
    conversation_id?: string;
    soul_prompt?: string;
    enabled_tools?: HermesToolName[];
    auto_learn_skill?: boolean;
  },
  signal: AbortSignal,
  onEvent: (event: HermesStreamEvent) => void,
): Promise<void> {
  const response = await fetch("/api/hermes/run", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new Error("Le serveur ne fournit aucun flux Hermes.");
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
    if (["meta", "step", "thought", "delta", "artifacts", "done", "error"].includes(event)) {
      if (event === "done") completed = true;
      if (event === "error") throw new Error(data.message ?? "La mission Hermes Agent a échoué.");
      onEvent({ type: event, data } as HermesStreamEvent);
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
    if (!completed) {
      throw new Error("Le flux Hermes Agent a été interrompu avant la fin de la mission.");
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
