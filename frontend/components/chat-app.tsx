"use client";

import {
  ArrowDown, ArrowUp, BookOpen, Brain, Check, ChevronDown, ChevronLeft, ChevronRight,
  CircleAlert, Copy, ExternalLink, FileText, Globe2, ImagePlus, LoaderCircle,
  LogOut, Menu, MessageCircle, PanelLeftClose, Paperclip, Pencil, Plus, Search,
  RefreshCw, Shield, Sparkles, Square, Trash2, WandSparkles, X,
} from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AdminPanel } from "@/components/admin-panel";
import { AuthPanel } from "@/components/auth-panel";
import { SkillsPanel } from "@/components/skills-panel";
import { ApiError, api, errorMessage, streamMessage, type Attachment, type AuthUser, type Config, type Conversation, type DocumentExtraction, type Memory, type Message } from "@/lib/api";

const suggestions = [
  { icon: WandSparkles, title: "Faire émerger une idée", description: "Explorer une piste et lui donner forme", prompt: "Aide-moi à explorer une idée. Pose-moi quelques questions pour comprendre ce que je veux créer." },
  { icon: BookOpen, title: "Comprendre un sujet", description: "Rendre les choses complexes plus claires", prompt: "J’aimerais mieux comprendre un sujet. Aide-moi à l’aborder avec des explications simples et des exemples." },
  { icon: FileText, title: "Travailler un document", description: "Résumer, analyser, prendre du recul", prompt: "Je vais joindre un document. Peux-tu m’en proposer une synthèse et en faire ressortir les points essentiels ?" },
  { icon: ImagePlus, title: "Imaginer une image", description: "Du premier mot à une création visuelle", prompt: "Une petite maison d’architecte au milieu d’une forêt brumeuse, lumière du matin, photographie cinématographique." },
];

function subscribeToLocation(callback: () => void) {
  window.addEventListener("popstate", callback);
  window.addEventListener("hashchange", callback);
  return () => {
    window.removeEventListener("popstate", callback);
    window.removeEventListener("hashchange", callback);
  };
}

function getInvitationToken() {
  return new URLSearchParams(window.location.hash.slice(1)).get("invite") ?? "";
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(new Date(value));
}

function dateGroup(value: string) {
  const day = new Date(value);
  const today = new Date();
  if (day.toDateString() === today.toDateString()) return "Aujourd’hui";
  if (today.getTime() - day.getTime() < 7 * 86400000) return "Ces 7 derniers jours";
  return "Plus tôt";
}

function BrandMark({ small = false }: { small?: boolean }) {
  return <span className={`brand-mark ${small ? "small" : ""}`} aria-hidden="true"><Sparkles strokeWidth={1.5} /></span>;
}

function IconButton({ label, children, className = "", ...props }: { label: string; children: ReactNode; className?: string } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={`icon-button ${className}`} aria-label={label} title={label} {...props}>{children}</button>;
}

function AttachmentAnalysis({ attachment }: { attachment: Attachment }) {
  const [extraction, setExtraction] = useState<DocumentExtraction | null>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [rawText, setRawText] = useState(true);
  async function load() {
    setLoading(true); setError("");
    try {
      const result = await api<{ extraction: DocumentExtraction | null }>(`/attachments/${attachment.id}/extraction`);
      setExtraction(result.extraction);
    } catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  }
  const page = extraction?.pages[pageIndex];
  return <details className="attachment-analysis" onToggle={event => {
    if (event.currentTarget.open && extraction === undefined && !loading && !error) void load();
  }}>
    <summary><BookOpen size={14} />Contenu extrait{attachment.page_count ? <span>{attachment.page_count} p.</span> : null}</summary>
    {loading && <p className="analysis-status" role="status"><LoaderCircle size={14} className="spin" />Chargement de l’analyse…</p>}
    {error && <div className="analysis-status" role="alert"><p>{error}</p><IconButton label="Réessayer le chargement" onClick={() => void load()}><RefreshCw size={15} /></IconButton></div>}
    {extraction === null && <p className="analysis-status">Analyse indisponible pour cette pièce jointe. Joignez à nouveau le fichier pour l’analyser.</p>}
    {extraction && page && <>
      <div className="analysis-toolbar">
        <IconButton label="Page précédente" disabled={pageIndex === 0} onClick={() => setPageIndex(index => index - 1)}><ChevronLeft size={16} /></IconButton>
        <label>Page <select value={pageIndex} onChange={event => setPageIndex(Number(event.target.value))}>{extraction.pages.map((item, index) => <option key={item.index} value={index}>{item.index + 1}</option>)}</select> / {extraction.pages.length}</label>
        <IconButton label="Page suivante" disabled={pageIndex === extraction.pages.length - 1} onClick={() => setPageIndex(index => index + 1)}><ChevronRight size={16} /></IconButton>
        <span>{page.method === "vision" ? "OCR + vision" : page.method === "local" ? "Extraction locale" : "OCR"}</span>
      </div>
      <div className="analysis-format" role="group" aria-label="Format de lecture">
        <button type="button" aria-pressed={rawText} onClick={() => setRawText(true)}><FileText size={13} />Texte brut</button>
        <button type="button" aria-pressed={!rawText} onClick={() => setRawText(false)}><BookOpen size={13} />Mise en forme</button>
      </div>
      <div className="analysis-content" aria-live="polite">
        {extraction.warnings.map((warning, index) => <p className="analysis-warning" key={index}>{warning}</p>)}
        <section className="analysis-section"><h4>Transcription OCR · page {page.index + 1}</h4>
          {page.markdown.trim() ? rawText ? <pre className="analysis-transcript">{page.markdown}</pre> : <div className="markdown"><ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{
            img: ({ alt }) => <span className="analysis-image-label">[{alt || "Illustration"}]</span>,
            a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
            table: ({ children }) => <div className="table-scroll"><table>{children}</table></div>,
          }}>{page.markdown}</ReactMarkdown></div> : <p>Aucun texte détecté.</p>}
        </section>
        {page.images.map(image => image.annotation && <section className="analysis-section" key={image.id}>
          <h4>{image.id} · {image.annotation.image_type}</h4><p>{image.annotation.description}</p>
          {image.annotation.visible_text && <pre className="analysis-transcript analysis-visible-text">{image.annotation.visible_text}</pre>}
        </section>)}
        {page.vision_description && <section className="analysis-section"><h4>Description visuelle · page {page.index + 1}</h4><p>{page.vision_description}</p></section>}
        {pageIndex === 0 && extraction.annotations.length > 0 && <details className="analysis-annotations"><summary>Analyse documentaire complémentaire</summary>
          {extraction.annotations.map((annotation, index) => <section className="analysis-section" key={index}><h4>{annotation.title || "Relevé documentaire"}</h4><p>{annotation.summary}</p></section>)}
        </details>}
      </div>
    </>}
  </details>;
}

function AttachmentView({ attachment }: { attachment: Attachment }) {
  return <div className="attachment-entry">
    {attachment.mime_type.startsWith("image/")
      ? <a className="message-image" href={attachment.url} target="_blank" rel="noreferrer"><img src={attachment.url} alt={attachment.filename} loading="lazy" /><span>{attachment.filename}<ExternalLink size={13} /></span></a>
      : <a className="document-link" href={attachment.url} target="_blank" rel="noreferrer"><FileText size={18} /><span>{attachment.filename}</span><ExternalLink size={13} /></a>}
    <AttachmentAnalysis attachment={attachment} />
  </div>;
}

function MessageView({ message, streaming }: { message: Message; streaming?: boolean }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const searchNotices = [...new Set((message.sources ?? []).flatMap(source => source.provider === "duckduckgo_instant_answers" && source.search_notice ? [source.search_notice] : []))];
  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { setCopied(false); }
  }
  return <article className={`message ${isUser ? "from-user" : "from-assistant"}`} aria-label={isUser ? "Votre message" : "Réponse de l’assistant"}>
    {!isUser && <div className="message-author"><BrandMark small /><span>cLAIr</span>{streaming && <span className="streaming-label">en train d’écrire</span>}</div>}
    {message.content ? <div className={`markdown ${streaming ? "is-streaming" : ""}`}><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
      pre: ({ children }) => <div className="code-block"><div className="code-label">Code</div><pre>{children}</pre></div>,
      table: ({ children }) => <div className="table-scroll"><table>{children}</table></div>,
    }}>{message.content}</ReactMarkdown></div> : streaming && <div className="thinking-dots" aria-label="Réponse en cours"><i /><i /><i /></div>}
    {!!message.attachments?.length && <div className="message-attachments">{message.attachments.map(item => <AttachmentView key={item.id} attachment={item} />)}</div>}
    {!!message.sources?.length && <div className="sources"><p><Globe2 size={13} /> Résultats de recherche</p><div>{message.sources.map((source, index) => <a key={`${source.url}-${index}`} href={source.url} target="_blank" rel="noreferrer" title={source.snippet}><span>{index + 1}</span><span>{source.title || new URL(source.url).hostname}</span>{source.provider === "duckduckgo_instant_answers" && <small className="source-provider">DuckDuckGo</small>}<ExternalLink size={12} /></a>)}</div>{searchNotices.map(notice => <p className="source-notice" key={notice}><CircleAlert size={12} />{notice}</p>)}{message.sources.some(source => source.provider === "duckduckgo_instant_answers") && <p className="source-attribution">Réponses instantanées fournies par <a href="https://duckduckgo.com" target="_blank" rel="noreferrer">DuckDuckGo<ExternalLink size={10} /></a>.</p>}</div>}
    {!isUser && message.content && !streaming && <div className="message-actions"><button type="button" onClick={copy} aria-label={copied ? "Réponse copiée" : "Copier la réponse"}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Copié" : "Copier"}</button><span>{new Date(message.created_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</span></div>}
  </article>;
}

export function ChatApp() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authError, setAuthError] = useState("");
  const invitationToken = useSyncExternalStore(subscribeToLocation, getInvitationToken, () => "");
  const [adminOpen, setAdminOpen] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [model, setModel] = useState("");
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [webSearch, setWebSearch] = useState(false);
  const [imageMode, setImageMode] = useState(false);
  const [busy, setBusy] = useState<string | null>("init");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [contextTab, setContextTab] = useState<"summary" | "memories">("summary");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [dialog, setDialog] = useState<{ type: "rename" | "delete"; conversation: Conversation } | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const controllerRef = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  async function loadWorkspace(signal?: AbortSignal) {
    const [settings, chats, savedMemories] = await Promise.all([
      api<Config>("/config", { signal }), api<Conversation[]>("/conversations", { signal }), api<Memory[]>("/memories", { signal }),
    ]);
    setConfig(settings); setModel(settings.default_model); setConversations(chats); setMemories(savedMemories);
  }

  async function bootstrap(signal?: AbortSignal) {
    setBusy("init"); setError("");
    try {
      const current = await api<AuthUser>("/auth/session", { signal });
      setUser(current);
      await loadWorkspace(signal);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setUser(null);
      else setError(`Connexion au serveur impossible. ${errorMessage(err)}`);
    } finally { setBusy(null); setAuthReady(true); }
  }

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    api<AuthUser>("/auth/session", { signal: controller.signal })
      .then(async current => {
        if (!active) return;
        setUser(current);
        const [settings, chats, savedMemories] = await Promise.all([
          api<Config>("/config", { signal: controller.signal }),
          api<Conversation[]>("/conversations", { signal: controller.signal }),
          api<Memory[]>("/memories", { signal: controller.signal }),
        ]);
        if (!active) return;
        setConfig(settings); setModel(settings.default_model); setConversations(chats); setMemories(savedMemories);
      }).catch(err => {
        if (!active || (err instanceof ApiError && err.status === 401)) return;
        setAuthError(`Connexion au serveur impossible. ${errorMessage(err)}`);
      }).finally(() => { if (active) { setAuthReady(true); setBusy(null); } });
    return () => { active = false; controller.abort(); controllerRef.current?.abort(); };
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) { textarea.style.height = "auto"; textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`; }
  }, [draft]);

  useEffect(() => {
    if (!dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    const focusTarget = document.querySelector<HTMLElement>(dialog.type === "rename" ? "#rename-input" : ".modal .secondary-button");
    focusTarget?.focus();
    return () => previous?.focus();
  }, [dialog]);

  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ behavior: streamingId ? "instant" : "smooth", block: "end" });
  }, [conversation?.messages, atBottom, streamingId, status]);

  const messages = conversation?.messages ?? [];
  const working = busy !== null;
  const sending = busy === "send" || busy === "image";
  const needsVision = attachments.some(file => file.mime_type.startsWith("image/") && !file.has_extraction) && !config?.demo_mode && !config?.models.find(item => item.id === model)?.vision;
  const canSend = !!config && !working && (imageMode ? config.features.image_generation && !!draft.trim() && draft.length <= 4000 : config.features.chat && !needsVision && (!!draft.trim() || attachments.length > 0));
  const searchProviders = config?.search_providers ?? (config?.features.web_search ? ["brave"] : []);
  const hasBrave = searchProviders.includes("brave");
  const hasDuckDuckGo = searchProviders.includes("duckduckgo_instant_answers");
  const duckDuckGoOnly = hasDuckDuckGo && !hasBrave;
  const showDuckDuckGoNotice = duckDuckGoOnly && webSearch && !imageMode && !!config?.features.web_search;
  const webSearchTooltip = !config?.features.web_search
    ? "Configurez une clé Brave ou activez DuckDuckGo côté serveur (DUCKDUCKGO_ENABLED=true) pour utiliser la recherche."
    : hasBrave && hasDuckDuckGo
      ? "Recherche web avec Brave ; DuckDuckGo en secours pour des réponses instantanées à couverture limitée."
      : duckDuckGoOnly
        ? "Réponses instantanées DuckDuckGo : sans clé, couverture limitée, sans recherche web complète."
        : "Rechercher sur le web avec Brave pour enrichir la réponse.";
  const filteredConversations = conversations.filter(item => item.title.toLocaleLowerCase("fr").includes(query.toLocaleLowerCase("fr")));
  const groups = ["Aujourd’hui", "Ces 7 derniers jours", "Plus tôt"].map(label => ({ label, items: filteredConversations.filter(item => dateGroup(item.updated_at) === label) })).filter(group => group.items.length);

  async function refreshConversations() { setConversations(await api<Conversation[]>("/conversations")); }

  async function discardUploads(files: Attachment[]) {
    const results = await Promise.allSettled(files.map(file => api(`/attachments/${file.id}`, { method: "DELETE" })));
    return results.some(result => result.status === "rejected") ? "Certains fichiers du brouillon n’ont pas pu être supprimés du serveur." : "";
  }

  async function removeAttachment(id: string) {
    if (working) return;
    setBusy("upload-delete"); setError("");
    try {
      await api(`/attachments/${id}`, { method: "DELETE" });
      setAttachments(old => old.filter(file => file.id !== id));
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function openConversation(id: string) {
    if (working) return;
    setBusy("switch"); setError(""); setSidebarOpen(false);
    try {
      const loaded = await api<Conversation>(`/conversations/${id}`);
      const warning = await discardUploads(attachments);
      setConversation(loaded); setModel(loaded.model); setDraft(""); setAttachments([]); setAtBottom(true); setImageMode(false);
      if (warning) setError(warning);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function newConversation() {
    if (working) return;
    setBusy("cleanup");
    const warning = await discardUploads(attachments);
    setConversation(null); setDraft(""); setAttachments([]); setModel(config?.default_model ?? ""); setError(""); setImageMode(false); setSidebarOpen(false); setAtBottom(true);
    if (warning) setError(warning);
    setBusy(null);
    textareaRef.current?.focus();
  }

  async function changeModel(value: string) {
    if (working) return;
    const previous = model;
    setModel(value);
    if (!conversation) return;
    setBusy("model"); setError("");
    try {
      const updated = await api<Conversation>(`/conversations/${conversation.id}`, { method: "PATCH", body: JSON.stringify({ model: value }) });
      setConversation(old => old ? { ...old, ...updated, messages: updated.messages ?? old.messages } : updated);
      await refreshConversations();
    } catch (err) { setModel(previous); setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length || working) return;
    const incoming = Array.from(files);
    const imageCount = attachments.filter(file => file.mime_type.startsWith("image/")).length + incoming.filter(file => file.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(file.name)).length;
    if (incoming.length + attachments.length > 5 || imageCount > 4) {
      setError("Un message peut contenir au maximum 5 pièces jointes, dont 4 images. Retirez des fichiers avant d’en ajouter.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setBusy("upload"); setError("");
    const uploaded: Attachment[] = [];
    try {
      for (const file of incoming) {
        if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} dépasse la limite de 20 Mo par fichier.`);
        if ((file.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(file.name)) && file.size > 8 * 1024 * 1024) throw new Error(`${file.name} dépasse la limite de 8 Mo par image.`);
        setStatus(`Importation et analyse de ${file.name}…`);
        const body = new FormData(); body.append("file", file);
        uploaded.push(await api<Attachment>("/attachments", { method: "POST", body }));
      }
    } catch (err) { setError(errorMessage(err)); }
    finally {
      setAttachments(old => [...old, ...uploaded]); setBusy(null); setStatus("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend || !config) return;
    const text = draft.trim();
    const files = attachments;
    const generatingImage = imageMode;
    const controller = new AbortController(); controllerRef.current = controller;
    setBusy(generatingImage ? "image" : "send"); setError(""); setStatus(generatingImage ? "Ideogram prépare votre image…" : "Connexion au modèle…"); setDraft(""); setAttachments([]); setAtBottom(true);
    let activeId = conversation?.id;
    let persisted = false;
    let assistantId = "";
    try {
      if (!activeId) {
        const created = await api<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ model }), signal: controller.signal });
        activeId = created.id; setConversation({ ...created, messages: created.messages ?? [] });
      }
      if (generatingImage) {
        const message = await api<Message>(`/conversations/${activeId}/images`, { method: "POST", body: JSON.stringify({ prompt: text, aspect_ratio: "1:1" }), signal: controller.signal });
        persisted = true;
        setConversation(old => old ? { ...old, messages: [...(old.messages ?? []), message] } : old);
      } else {
        await streamMessage(activeId, { content: text, model, web_search: webSearch && config.features.web_search, attachment_ids: files.map(item => item.id) }, controller.signal, event => {
          if (event.type === "meta") {
            persisted = true; assistantId = event.data.assistant_message_id; setStreamingId(assistantId);
            const empty: Message = { id: assistantId, role: "assistant", content: "", created_at: new Date().toISOString(), attachments: [], sources: [] };
            setConversation(old => old ? { ...old, messages: [...(old.messages ?? []), event.data.user_message, empty] } : old);
            setStatus("Le modèle réfléchit…");
          } else if (event.type === "status") setStatus(event.data.message);
          else if (event.type === "delta") {
            setStatus("");
            setConversation(old => old ? { ...old, messages: (old.messages ?? []).map(item => item.id === assistantId ? { ...item, content: item.content + event.data.text } : item) } : old);
          } else if (event.type === "done") {
            setConversation(old => ({ ...event.data.conversation, skills: event.data.conversation.skills ?? old?.skills ?? [], messages: event.data.conversation.messages ?? (old?.messages ?? []).map(item => item.id === assistantId ? event.data.message : item) }));
          }
        });
      }
      const loaded = await api<Conversation>(`/conversations/${activeId}`);
      setConversation(loaded); await refreshConversations();
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      setError(aborted ? "Génération interrompue. Les messages déjà enregistrés restent dans l’historique." : errorMessage(err));
      if (!persisted) { setDraft(text); setAttachments(files); }
      if (activeId) {
        try { setConversation(await api<Conversation>(`/conversations/${activeId}`)); await refreshConversations(); }
        catch { /* Preserve the existing history if the backend is unavailable. */ }
      }
    } finally { controllerRef.current = null; setStreamingId(null); setBusy(null); setStatus(""); textareaRef.current?.focus(); }
  }

  async function saveMemory(event: FormEvent) {
    event.preventDefault();
    if (!memoryDraft.trim() || working) return;
    setBusy("memory"); setError("");
    try {
      const saved = await api<Memory>("/memories", { method: "POST", body: JSON.stringify({ content: memoryDraft.trim() }) });
      setMemories(old => [saved, ...old]); setMemoryDraft("");
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function deleteMemory(id: string) {
    if (working) return;
    setBusy("memory"); setError("");
    try { await api(`/memories/${id}`, { method: "DELETE" }); setMemories(old => old.filter(item => item.id !== id)); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function authenticated(current: AuthUser) {
    setUser(current); setError(""); setBusy("init");
    try { await loadWorkspace(); }
    catch (err) { setError(`Connexion au serveur impossible. ${errorMessage(err)}`); }
    finally { setBusy(null); setAuthReady(true); }
  }

  function invitationAccepted() {
    setUser(null); setConfig(null); setConversations([]); setConversation(null); setMemories([]);
    setDraft(""); setAttachments([]); setMemoryDraft(""); setAdminOpen(false);
    window.history.replaceState({}, "", window.location.pathname + window.location.search);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  async function logout() {
    setError("");
    try {
      await api<void>("/auth/logout", { method: "POST" });
      setUser(null); setConfig(null); setConversations([]); setConversation(null); setMemories([]);
      setAuthReady(true); setAdminOpen(false);
    } catch (err) { setError(errorMessage(err)); }
  }

  async function submitDialog(event: FormEvent) {
    event.preventDefault();
    if (!dialog || working || (dialog.type === "rename" && !renameValue.trim())) return;
    setBusy("edit"); setError("");
    try {
      const id = dialog.conversation.id;
      if (dialog.type === "delete") {
        await api(`/conversations/${id}`, { method: "DELETE" });
        if (conversation?.id === id) { setConversation(null); setDraft(""); setAttachments([]); }
      } else {
        const updated = await api<Conversation>(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title: renameValue.trim() }) });
        if (conversation?.id === id) setConversation(old => old ? { ...old, ...updated, messages: updated.messages ?? old.messages } : updated);
      }
      await refreshConversations(); setDialog(null);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
  }

  if (!authReady) return <div className="auth-loading" role="status"><LoaderCircle className="spin" size={20} />Vérification de la session…</div>;
  if (invitationToken || !user) return <AuthPanel invitationToken={invitationToken} serviceError={authError} onAuthenticated={authenticated} onRegistration={invitationAccepted} />;

  return <div className="app-shell">
    <a className="skip-link" href="#composer">Aller au message</a>
    {sidebarOpen && <button className="sidebar-overlay" type="button" aria-label="Fermer le menu" onClick={() => setSidebarOpen(false)} />}
    <aside className={`sidebar ${sidebarOpen ? "is-open" : ""}`} aria-label="Conversations">
      <div className="brand"><BrandMark small /><span>cLAIr<span className="brand-dot">.</span></span><IconButton label="Fermer le menu" className="mobile-only" onClick={() => setSidebarOpen(false)}><PanelLeftClose size={18} /></IconButton></div>
      <button type="button" className="new-chat" onClick={() => void newConversation()} disabled={working}><Plus size={18} /><span>Nouvelle conversation</span><kbd>+</kbd></button>
      <label className="search-field"><Search size={16} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Rechercher une conversation" aria-label="Rechercher dans les titres des conversations" /><kbd>⌕</kbd></label>
      <div className="history-header"><span>VOTRE ESPACE</span><span>{conversations.length}</span></div>
      <nav className="history-list" aria-label="Historique des conversations">
        {busy === "init" ? <p className="history-empty"><LoaderCircle className="spin" size={16} /> Chargement de l’historique…</p> : groups.length ? groups.map(group => <div key={group.label} className="history-group"><h2>{group.label}</h2>{group.items.map(item => <div key={item.id} className={`history-item ${conversation?.id === item.id ? "is-active" : ""}`}>
          <button type="button" className="history-select" disabled={working} onClick={() => void openConversation(item.id)}><MessageCircle size={15} /><span>{item.title}</span></button>
          <div className="history-tools"><IconButton label={`Renommer « ${item.title} »`} disabled={working} onClick={() => { setDialog({ type: "rename", conversation: item }); setRenameValue(item.title); }}><Pencil size={13} /></IconButton><IconButton label={`Supprimer « ${item.title} »`} disabled={working} onClick={() => setDialog({ type: "delete", conversation: item })}><Trash2 size={13} /></IconButton></div>
        </div>)}</div>) : <div className="history-empty"><MessageCircle size={20} /><p>{query ? "Aucune conversation trouvée." : "Une idée, une question…\nVotre historique commence ici."}</p></div>}
      </nav>
      <div className="sidebar-bottom"><button type="button" className="memory-shortcut" onClick={() => { setContextTab("memories"); setContextOpen(true); setSidebarOpen(false); }}><span className="memory-icon"><Brain size={18} /></span><span><strong>Votre mémoire</strong><small>{memories.length ? `${memories.length} information${memories.length > 1 ? "s" : ""} enregistrée${memories.length > 1 ? "s" : ""}` : "Les choses qui comptent"}</small></span><ChevronRight size={16} /></button><div className="profile"><span className="avatar">{user.username[0].toLocaleUpperCase("fr")}</span><span className="profile-user"><strong>{user.username}</strong><small><span className="connection-dot" /> Compte sécurisé</small></span>{user.is_admin && <IconButton label="Gérer les utilisateurs" onClick={() => setAdminOpen(true)}><Shield size={16} /></IconButton>}<IconButton label="Se déconnecter" onClick={() => void logout()}><LogOut size={16} /></IconButton></div></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="topbar-left"><IconButton label="Ouvrir le menu" className="mobile-only" onClick={() => setSidebarOpen(true)}><Menu size={21} /></IconButton><div className="model-select-wrap"><span className="model-indicator" /><select aria-label="Modèle d’intelligence artificielle" value={model} onChange={event => void changeModel(event.target.value)} disabled={!config || working}>{config?.models.map(item => <option key={item.id} value={item.id}>{item.name}</option>) ?? <option>Connexion…</option>}</select><ChevronDown size={14} /></div><span className="topbar-divider" /><span className="personal-label">Votre espace IA</span></div><div className="topbar-right"><button type="button" className={`context-toggle ${contextOpen ? "is-selected" : ""}`} onClick={() => setContextOpen(old => !old)} aria-expanded={contextOpen} aria-controls="context-panel" aria-label="Mémoire & contexte"><Brain size={17} /><span>Mémoire & contexte</span><span className="memory-count">{memories.length}</span></button></div></header>

      {config?.demo_mode && <div className="demo-banner" role="status"><CircleAlert size={17} /><span><strong>Mode démonstration.</strong> Les réponses sont simulées, aucun modèle IA n’est appelé. Configurez une clé côté serveur et désactivez <code>DEMO_MODE</code> pour activer l’IA.</span></div>}
      {config && !config.features.chat && !config.demo_mode && <div className="demo-banner" role="status"><CircleAlert size={17} /><span><strong>Le tchat attend sa configuration.</strong> Ajoutez une clé du fournisseur IA dans le fichier <code>.env</code> du serveur, puis redémarrez le backend.</span></div>}

      <div className="workspace">
        <section className="chat-panel" aria-label="Conversation">
          <div className="chat-skills-toolbar"><span>{conversation?.skills?.length ? conversation.skills.map(skill => skill.name).join(" · ") : "Aucune compétence active"}</span><button type="button" onClick={() => { setContextOpen(false); setSkillsOpen(true); }}><Sparkles size={15} />Compétences<small>{conversation?.skills?.length ?? 0}</small></button></div>
          {skillsOpen && <SkillsPanel conversation={conversation} model={model} config={config} onClose={() => setSkillsOpen(false)} onConversationChange={setConversation} onRefreshConversations={refreshConversations} />}
          <div className="chat-scroll" ref={messagesRef} onScroll={() => { const el = messagesRef.current; if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120); }}>
            {!messages.length && busy !== "switch" ? <div className="welcome"><div className="welcome-eyebrow"><span /> UN PEU DE CLARTÉ, BEAUCOUP DE POSSIBILITÉS</div><BrandMark /><h1>Qu’avez-vous en tête<span> aujourd’hui ?</span></h1><p>Un espace pour vos questions, vos idées et vos projets.<br />Commencez quelque part. On avance ensemble.</p><div className="suggestions">{suggestions.map((item, index) => <button type="button" className="suggestion" key={item.title} disabled={working || (index === 3 && !config?.features.image_generation)} title={index === 3 && !config?.features.image_generation ? "Configurez votre clé Ideogram côté serveur pour créer des images." : undefined} onClick={() => { setDraft(item.prompt); setImageMode(index === 3); textareaRef.current?.focus(); }}><span className={`suggestion-icon suggestion-icon-${index}`}><item.icon size={19} strokeWidth={1.6} /></span><strong>{item.title}</strong><span>{item.description}</span><ChevronRight size={15} className="suggestion-arrow" /></button>)}</div><div className="welcome-note"><Brain size={14} /><span>Les souvenirs que vous choisissez gardent le fil d’une conversation à l’autre.</span></div></div> : busy === "switch" ? <div className="loading-conversation"><LoaderCircle size={23} className="spin" />Ouverture de votre conversation…</div> : <div className="messages"><div className="conversation-heading"><span>CONVERSATION</span><h1>{conversation?.title}</h1></div>{messages.map(message => <MessageView key={message.id} message={message} streaming={streamingId === message.id} />)}<div ref={bottomRef} /></div>}
          </div>
          {!atBottom && !!messages.length && <IconButton className="scroll-bottom" label="Aller aux derniers messages" onClick={() => { setAtBottom(true); bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }}><ArrowDown size={18} /></IconButton>}

          <div className="composer-area">
            {error && <div className="error-banner" role="alert"><CircleAlert size={17} /><p>{error}</p>{!config && <button type="button" disabled={working} onClick={() => void bootstrap()}>Réessayer</button>}<IconButton label="Fermer le message d’erreur" onClick={() => setError("")}><X size={15} /></IconButton></div>}
            {showDuckDuckGoNotice && <div className="search-notice" id="web-search-hint" role="status"><Globe2 size={13} />DuckDuckGo fournit des réponses instantanées et des sujets associés ; couverture limitée.</div>}
            {needsVision && <div className="vision-notice" role="status"><CircleAlert size={13} />Pour analyser vos images, choisissez un modèle compatible avec la vision.</div>}
            {status && <div className="generation-status" role="status"><LoaderCircle size={13} className="spin" />{status}</div>}
            <form className={`composer ${imageMode ? "image-mode" : ""}`} onSubmit={event => void send(event)}>
              {imageMode && <div className="image-mode-label"><ImagePlus size={15} /><span>Studio image <strong>Ideogram</strong></span><button type="button" disabled={working} onClick={() => setImageMode(false)}>Revenir au tchat <X size={13} /></button></div>}
              {!!attachments.length && <div className="pending-attachments">{attachments.map(item => <div className="pending-entry" key={item.id}><div className="pending-file"><FileText size={15} /><span>{item.filename}</span><IconButton label={`Retirer ${item.filename}`} disabled={working} onClick={() => void removeAttachment(item.id)}><X size={13} /></IconButton></div><AttachmentAnalysis attachment={item} /></div>)}</div>}
              <label className="sr-only" htmlFor="composer">{imageMode ? "Décrivez l’image à générer" : "Votre message"}</label><textarea id="composer" ref={textareaRef} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={composerKeyDown} placeholder={imageMode ? "Décrivez l’image que vous imaginez…" : "Une question, une idée, un début de quelque chose…"} rows={2} maxLength={imageMode ? 4000 : 20000} disabled={working || !config} aria-describedby="composer-hint" />
              <div className="composer-toolbar"><div className="composer-tools"><input className="sr-only" type="file" ref={fileRef} multiple accept=".txt,.md,.csv,.json,.pdf,.docx,image/png,image/jpeg,image/webp" onChange={event => void uploadFiles(event.target.files)} tabIndex={-1} /><IconButton label="Joindre jusqu’à 5 fichiers (20 Mo par document, 8 Mo par image)" disabled={working || imageMode || !config} onClick={() => fileRef.current?.click()}><Paperclip size={19} /></IconButton><span className="tool-divider" /><button type="button" className={`tool-button ${webSearch && !imageMode ? "active" : ""}`} disabled={working || imageMode || !config?.features.web_search} aria-pressed={webSearch && !imageMode} title={webSearchTooltip} aria-describedby={showDuckDuckGoNotice ? "web-search-hint" : undefined} onClick={() => setWebSearch(old => !old)}><Globe2 size={16} /><span>Web</span>{webSearch && !imageMode && <Check size={12} />}</button><button type="button" className={`tool-button ${imageMode ? "active" : ""}`} disabled={working || !config?.features.image_generation || attachments.length > 0} aria-pressed={imageMode} title={config?.features.image_generation ? "Créer une image avec Ideogram" : "Ajoutez votre clé Ideogram côté serveur pour créer des images"} onClick={() => { setImageMode(old => !old); textareaRef.current?.focus(); }}><ImagePlus size={16} /><span>Image</span></button></div><div className="composer-submit"><span className="enter-hint">↵ pour envoyer</span>{sending ? <button className="send-button stop-button" type="button" onClick={() => controllerRef.current?.abort()} aria-label="Interrompre la génération" title="Interrompre la génération"><Square size={14} fill="currentColor" /></button> : <button className="send-button" type="submit" disabled={!canSend} aria-label={imageMode ? "Générer l’image" : "Envoyer le message"}>{busy === "upload" ? <LoaderCircle size={19} className="spin" /> : <ArrowUp size={20} />}</button>}</div></div>
            </form>
            <div className="composer-footnote" id="composer-hint"><span>cLAIr peut se tromper. Gardez un regard critique sur les réponses.</span><span>Maj + Entrée pour un saut de ligne</span></div>
          </div>
        </section>

        {contextOpen && <aside className="context-panel" id="context-panel" aria-label="Mémoire et contexte"><div className="context-heading"><div><span className="eyebrow">GARDER LE FIL</span><h2>Mémoire & contexte</h2></div><IconButton label="Fermer le panneau mémoire" onClick={() => setContextOpen(false)}><X size={18} /></IconButton></div><div className="context-tabs" role="tablist" aria-label="Contexte"><button id="summary-tab" type="button" role="tab" aria-selected={contextTab === "summary"} aria-controls="summary-panel" className={contextTab === "summary" ? "active" : ""} onClick={() => setContextTab("summary")}>Cette conversation</button><button id="memories-tab" type="button" role="tab" aria-selected={contextTab === "memories"} aria-controls="memories-panel" className={contextTab === "memories" ? "active" : ""} onClick={() => setContextTab("memories")}>Mes souvenirs <span>{memories.length}</span></button></div>
          {contextTab === "summary" ? <div className="context-content" role="tabpanel" id="summary-panel" aria-labelledby="summary-tab"><div className="context-info"><BookOpen size={19} /><h3>L’essentiel, au même endroit.</h3><p>Un résumé progressif aide l’IA à garder le contexte quand la conversation s’allonge.</p></div>{conversation?.summary ? <div className="summary-card markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{conversation.summary}</ReactMarkdown></div> : <div className="context-empty"><span className="empty-orbit"><BookOpen size={24} strokeWidth={1.2} /></span><strong>Chaque échange a son fil.</strong><p>{conversation ? "Le résumé apparaîtra ici lorsque cette conversation sera assez longue." : "Commencez une conversation pour retrouver son résumé ici."}</p></div>}<p className="context-explainer"><CircleAlert size={14} />Ce résumé est lié à cette conversation. Vos souvenirs, eux, peuvent enrichir tous vos échanges.</p></div> : <div className="context-content" role="tabpanel" id="memories-panel" aria-labelledby="memories-tab"><div className="context-info"><Brain size={20} /><h3>Les petites choses à retenir.</h3><p>Ajoutez vos préférences, vos projets ou des informations utiles. Vous gardez le contrôle.</p></div><form className="memory-form" onSubmit={event => void saveMemory(event)}><label className="sr-only" htmlFor="memory-input">Nouvelle information à mémoriser</label><textarea id="memory-input" placeholder="Par exemple : je préfère des réponses courtes et concrètes." value={memoryDraft} onChange={event => setMemoryDraft(event.target.value)} disabled={working} maxLength={2000} rows={3} /><button type="submit" disabled={!memoryDraft.trim() || working}><Plus size={15} />Mémoriser</button></form>{memories.length ? <ul className="memory-list">{memories.map(memory => <li key={memory.id}><div><span className="memory-bullet" /><p>{memory.content}</p><IconButton label={`Oublier : ${memory.content.slice(0, 45)}`} disabled={working} onClick={() => void deleteMemory(memory.id)}><Trash2 size={14} /></IconButton></div><small>Ajouté le {shortDate(memory.created_at)}</small></li>)}</ul> : <div className="memory-empty"><Brain size={23} strokeWidth={1.3} /><p>Votre mémoire est encore une page blanche.</p></div>}<p className="context-explainer"><CircleAlert size={14} />Ces informations sont envoyées au modèle dans vos conversations. Vous pouvez les supprimer à tout moment.</p></div>}
        </aside>}
      </div>
    </main>

    {adminOpen && user.is_admin && <AdminPanel currentUser={user} onClose={() => setAdminOpen(false)} />}
    {dialog && <div className="modal-backdrop" onClick={event => { if (event.target === event.currentTarget && !working) setDialog(null); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title" onKeyDown={event => { if (event.key === "Escape" && !working) setDialog(null); if (event.key === "Tab") { const elements = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)')); if (!elements.length) return; const first = elements[0]; const last = elements[elements.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } }}><form onSubmit={event => void submitDialog(event)}><div className="modal-header"><span className="modal-icon">{dialog.type === "delete" ? <Trash2 size={20} /> : <Pencil size={20} />}</span><IconButton label="Fermer" disabled={working} onClick={() => setDialog(null)}><X size={18} /></IconButton></div><h2 id="dialog-title">{dialog.type === "delete" ? "Supprimer cette conversation ?" : "Un nouveau titre"}</h2>{dialog.type === "delete" ? <p>« {dialog.conversation.title} » et ses messages seront supprimés. Cette action est définitive.</p> : <><label htmlFor="rename-input">Titre de la conversation</label><input id="rename-input" value={renameValue} onChange={event => setRenameValue(event.target.value)} maxLength={200} autoFocus disabled={working} /></>}<div className="modal-actions"><button type="button" className="secondary-button" disabled={working} onClick={() => setDialog(null)}>Annuler</button><button type="submit" className={dialog.type === "delete" ? "danger-button" : "primary-button"} disabled={working || (dialog.type === "rename" && !renameValue.trim())}>{working ? <LoaderCircle className="spin" size={15} /> : null}{dialog.type === "delete" ? "Supprimer" : "Enregistrer"}</button></div></form></section></div>}
  </div>;
}
