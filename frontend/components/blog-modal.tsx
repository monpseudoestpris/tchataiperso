"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  BookOpen,
  Calendar,
  Check,
  ChevronDown,
  CircleAlert,
  Clock,
  Compass,
  Copy,
  ExternalLink,
  FileText,
  Globe2,
  LayoutGrid,
  LoaderCircle,
  Newspaper,
  Palette,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import {
  createBlog,
  deleteBlog,
  deleteBlogPost,
  errorMessage,
  fetchBlog,
  fetchBlogs,
  refreshBlog,
  updateBlog,
  type Blog,
  type BlogPost,
  type Source,
} from "@/lib/api";

type BlogModalProps = {
  onClose: () => void;
  initialPrompt?: string;
};

const SUGGESTIONS = [
  {
    topic: "Les dernières actualités et avancées en intelligence artificielle",
    label: "Actualités IA & LLM",
    icon: "🤖",
  },
  {
    topic: "Cybersécurité, failles critiques et attaques récentes",
    label: "Cybersécurité & Failles",
    icon: "🛡️",
  },
  {
    topic: "Innovations en énergie propre, climat et fusion nucléaire",
    label: "Énergie & Climat",
    icon: "⚡",
  },
  {
    topic: "Actualités open-source, langages et développement logiciel",
    label: "Open Source & Dév",
    icon: "💻",
  },
  {
    topic: "Exploration spatiale, missions de la NASA et découvertes astronomie",
    label: "Espace & Astronomie",
    icon: "🚀",
  },
];

function formatBlogDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function relativeTime(dateStr: string): string {
  try {
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return "À l'instant";
    if (diff < 3600) return `Il y a ${Math.max(1, Math.floor(diff / 60))} min`;
    if (diff < 86400) return `Il y a ${Math.floor(diff / 3600)} h`;
    return formatBlogDate(dateStr);
  } catch {
    return dateStr;
  }
}

function formatMarkdownFromPost(post: BlogPost): string {
  if (post.cards && post.cards.length > 0) {
    const lines = [`# ${post.title}\n`, `> ${post.summary}\n`];
    for (const c of post.cards) {
      lines.push(
        `### [${c.title}](${c.url})\n` +
        `*Source : ${c.source_name} | Thématique : ${c.tag}*\n\n` +
        `${c.text}\n`
      );
    }
    return lines.join("\n");
  }
  return post.content;
}

export type BlogThemeDef = {
  id: string;
  name: string;
  emoji: string;
  primary: string;
  secondary: string;
  bgLight: string;
  border: string;
  accentText: string;
};

export const BLOG_THEMES: BlogThemeDef[] = [
  { id: "sunset", name: "Coucher de Soleil", emoji: "🌅", primary: "#f97316", secondary: "#ea580c", bgLight: "#fff7ed", border: "#fed7aa", accentText: "#c2410c" },
  { id: "cyber", name: "Cyber Nuit", emoji: "🌌", primary: "#818cf8", secondary: "#6366f1", bgLight: "#0b0f19", border: "#3730a3", accentText: "#a5b4fc" },
  { id: "emerald", name: "Forêt d'Émeraude", emoji: "🌲", primary: "#10b981", secondary: "#047857", bgLight: "#ecfdf5", border: "#a7f3d0", accentText: "#065f46" },
  { id: "synthwave", name: "Synthwave 80s", emoji: "🔮", primary: "#f472b6", secondary: "#d946ef", bgLight: "#130924", border: "#86198f", accentText: "#f0abfc" },
  { id: "ocean", name: "Océan Profond", emoji: "🌊", primary: "#0284c7", secondary: "#0369a1", bgLight: "#f0f9ff", border: "#bae6fd", accentText: "#075985" },
  { id: "ruby", name: "Rubis Impérial", emoji: "🍷", primary: "#e11d48", secondary: "#be123c", bgLight: "#fff1f2", border: "#fecdd3", accentText: "#9f1239" },
  { id: "mocha", name: "Café Mocha", emoji: "☕", primary: "#854d0e", secondary: "#713f12", bgLight: "#fdf8f0", border: "#ddc7b2", accentText: "#543007" },
  { id: "sakura", name: "Cerisier Sakura", emoji: "🌸", primary: "#ec4899", secondary: "#db2777", bgLight: "#fdf2f8", border: "#fbcfe8", accentText: "#9d174d" },
  { id: "matrix", name: "Vert Matrix", emoji: "⚡", primary: "#22c55e", secondary: "#16a34a", bgLight: "#05140b", border: "#15803d", accentText: "#86efac" },
  { id: "nordic", name: "Glace Nordique", emoji: "🧊", primary: "#06b6d4", secondary: "#0891b2", bgLight: "#ecfeff", border: "#a5f3fc", accentText: "#155e75" },
  { id: "terracotta", name: "Dune & Terracotta", emoji: "🏜️", primary: "#c2410c", secondary: "#9a3412", bgLight: "#ffedd5", border: "#fed7aa", accentText: "#7c2d12" },
  { id: "plum", name: "Prune Royale", emoji: "🍇", primary: "#9333ea", secondary: "#7e22ce", bgLight: "#faf5ff", border: "#e9d5ff", accentText: "#581c87" },
  { id: "mint", name: "Menthe & Sauge", emoji: "🍃", primary: "#14b8a6", secondary: "#0f766e", bgLight: "#f0fdfa", border: "#99f6e4", accentText: "#115e59" },
  { id: "slate", name: "Ardoise Moderne", emoji: "🏙️", primary: "#94a3b8", secondary: "#64748b", bgLight: "#0f172a", border: "#475569", accentText: "#cbd5e1" },
  { id: "gold", name: "Or Solaire", emoji: "☀️", primary: "#eab308", secondary: "#ca8a04", bgLight: "#fefce8", border: "#fef08a", accentText: "#854d0e" },
  { id: "volcano", name: "Braise Volcanique", emoji: "🌋", primary: "#ef4444", secondary: "#dc2626", bgLight: "#fef2f2", border: "#fecaca", accentText: "#991b1b" },
  { id: "peacock", name: "Paon Turquoise", emoji: "🦚", primary: "#0d9488", secondary: "#115e59", bgLight: "#e6fffa", border: "#81e6d9", accentText: "#134e4a" },
  { id: "aurora", name: "Aurore Boréale", emoji: "✨", primary: "#3b82f6", secondary: "#8b5cf6", bgLight: "#eff6ff", border: "#bfdbfe", accentText: "#1d4ed8" },
  { id: "berry", name: "Baies Sauvages", emoji: "🍓", primary: "#f43f5e", secondary: "#be123c", bgLight: "#fff1f2", border: "#fda4af", accentText: "#881337" },
  { id: "caramel", name: "Caramel Brûlé", emoji: "🍫", primary: "#b45309", secondary: "#78350f", bgLight: "#fffbeb", border: "#fde68a", accentText: "#78350f" },
  { id: "steel", name: "Acier & Platine", emoji: "🪙", primary: "#64748b", secondary: "#475569", bgLight: "#f1f5f9", border: "#cbd5e1", accentText: "#0f172a" },
];

function getBlogTheme(themeId?: string): BlogThemeDef {
  return BLOG_THEMES.find(t => t.id === themeId) || BLOG_THEMES[0];
}

export function BlogModal({ onClose, initialPrompt = "" }: BlogModalProps) {
  const [blogs, setBlogs] = useState<Blog[]>([]);
  const [selectedBlogId, setSelectedBlogId] = useState<string | null>(null);
  const [activeBlog, setActiveBlog] = useState<Blog | null>(null);
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [blogLoading, setBlogLoading] = useState(false);
  const [busy, setBusy] = useState<"" | "create" | "refresh" | "update" | "delete">("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  // Creation form state
  const [isCreating, setIsCreating] = useState(false);
  const [createPrompt, setCreatePrompt] = useState(initialPrompt);
  const [createTitle, setCreateTitle] = useState("");
  const [createAutoRefresh, setCreateAutoRefresh] = useState(false);
  const [createTheme, setCreateTheme] = useState("sunset");

  // Theme selection state for viewer
  const [isThemePickerOpen, setIsThemePickerOpen] = useState(false);

  // Edit title modal / inline
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");

  // Search filter
  const [filterQuery, setFilterQuery] = useState("");

  // Auto-refresh cooldown tracker per blog (10 minutes)
  const lastAutoRefreshRef = useRef<Record<string, number>>({});

  // Copy indicator
  const [copied, setCopied] = useState(false);

  // View mode switcher: "cards" (encarts colorés) vs "text" (texte continu)
  const [viewMode, setViewMode] = useState<"cards" | "text">("cards");
  const [copiedCardIdx, setCopiedCardIdx] = useState<number | null>(null);

  // Deletion confirmation modal
  const [blogToDelete, setBlogToDelete] = useState<Blog | null>(null);

  function handleCopyCard(text: string, idx: number) {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedCardIdx(idx);
      setTimeout(() => setCopiedCardIdx(null), 2000);
    });
  }

  // Load initial blogs list
  useEffect(() => {
    const controller = new AbortController();
    fetchBlogs()
      .then(items => {
        setBlogs(items);
        if (initialPrompt.trim()) {
          setIsCreating(true);
          setCreatePrompt(initialPrompt.trim());
        } else if (items.length > 0) {
          setSelectedBlogId(items[0].id);
        } else {
          setIsCreating(true);
        }
      })
      .catch(err => {
        if (!controller.signal.aborted) setError(errorMessage(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [initialPrompt]);

  // Load selected blog details & check auto-refresh
  useEffect(() => {
    if (!selectedBlogId) {
      setActiveBlog(null);
      return;
    }
    let cancelled = false;
    setBlogLoading(true);

    fetchBlog(selectedBlogId)
      .then(blog => {
        if (cancelled) return;
        setActiveBlog(blog);
        if (blog.posts && blog.posts.length > 0) {
          setSelectedPostId(current => (current && blog.posts?.some(p => p.id === current) ? current : blog.posts![0].id));
        } else {
          setSelectedPostId(null);
        }

        // Les actualisations sont désormais manuelles à la demande (pas d'auto-refresh à la visite).
      })
      .catch(err => {
        if (!cancelled) {
          const msg = errorMessage(err);
          if (msg.toLowerCase().includes("introuvable")) {
            setBlogs(current => current.filter(b => b.id !== selectedBlogId));
            setSelectedBlogId(null);
            return;
          }
          setError(msg);
        }
      })
      .finally(() => {
        if (!cancelled) setBlogLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedBlogId]);

  // Trigger refresh (manual or automatic on visit)
  async function triggerRefresh(blogId: string, isAuto = false) {
    if (busy === "refresh") return;
    setBusy("refresh");
    setError("");
    if (!isAuto) {
      lastAutoRefreshRef.current[blogId] = Date.now();
    }
    try {
      const res = await refreshBlog(blogId);
      setActiveBlog(res.blog);
      setSelectedPostId(res.new_post.id);
      setBlogs(current => current.map(b => (b.id === blogId ? res.blog : b)));
      showToast(isAuto ? "Nouvelle édition publiée automatiquement !" : "Édition actualisée avec succès via SearXNG !");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 4500);
  }

  // Handle create blog
  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const prompt = createPrompt.trim();
    if (!prompt || busy) return;
    setBusy("create");
    setError("");

    try {
      const created = await createBlog({
        prompt,
        title: createTitle.trim() || undefined,
        auto_refresh: createAutoRefresh,
        theme: createTheme,
      });

      lastAutoRefreshRef.current[created.id] = Date.now();
      setBlogs(current => [created, ...current]);
      setActiveBlog(created);
      setSelectedBlogId(created.id);
      if (created.posts && created.posts.length > 0) {
        setSelectedPostId(created.posts[0].id);
      }
      setIsCreating(false);
      setCreatePrompt("");
      setCreateTitle("");
      showToast("Blog créé et première édition rédigée avec succès !");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  // Switch theme for active blog independently (persisted in DB)
  async function handleSelectTheme(themeId: string) {
    if (!activeBlog) return;
    const previousTheme = activeBlog.theme;
    const updated = { ...activeBlog, theme: themeId };
    setActiveBlog(updated);
    setBlogs(current => current.map(b => (b.id === activeBlog.id ? updated : b)));
    setIsThemePickerOpen(false);
    const themeDef = getBlogTheme(themeId);
    showToast(`Thème « ${themeDef.name} » activé`);

    try {
      await updateBlog(activeBlog.id, { theme: themeId });
    } catch (err) {
      const reverted = { ...activeBlog, theme: previousTheme };
      setActiveBlog(reverted);
      setBlogs(current => current.map(b => (b.id === activeBlog.id ? reverted : b)));
      setError(errorMessage(err));
    }
  }

  // Handle delete blog via confirmation dialog
  function handleRequestDeleteBlog(blog: Blog) {
    setBlogToDelete(blog);
  }

  async function executeDeleteBlog(blogId: string) {
    setBusy("delete");
    setError("");
    try {
      await deleteBlog(blogId);
      const remaining = blogs.filter(b => b.id !== blogId);
      setBlogs(remaining);
      setBlogToDelete(null);
      if (selectedBlogId === blogId) {
        if (remaining.length > 0) {
          setSelectedBlogId(remaining[0].id);
        } else {
          setSelectedBlogId(null);
          setActiveBlog(null);
          setIsCreating(true);
        }
      }
      showToast("Blog et éditions supprimés avec succès.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  // Handle delete single post
  async function handleDeletePost(blogId: string, postId: string) {
    if (!confirm("Supprimer cette édition du blog ?")) return;
    setError("");
    try {
      await deleteBlogPost(blogId, postId);
      if (activeBlog) {
        const remainingPosts = (activeBlog.posts || []).filter(p => p.id !== postId);
        const updated = { ...activeBlog, posts: remainingPosts, posts_count: remainingPosts.length };
        setActiveBlog(updated);
        setBlogs(current => current.map(b => (b.id === blogId ? updated : b)));
        if (remainingPosts.length > 0) {
          setSelectedPostId(remainingPosts[0].id);
        } else {
          setSelectedPostId(null);
        }
      }
      showToast("Édition supprimée.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  // Toggle auto refresh
  async function handleToggleAutoRefresh() {
    if (!activeBlog || busy) return;
    const nextVal = !activeBlog.auto_refresh;
    try {
      const updated = await updateBlog(activeBlog.id, { auto_refresh: nextVal });
      setActiveBlog(updated);
      setBlogs(current => current.map(b => (b.id === updated.id ? updated : b)));
      showToast(nextVal ? "Mise à jour automatique à chaque visite activée" : "Mise à jour automatique désactivée");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  // Save edited title
  async function handleSaveTitle() {
    if (!activeBlog || !titleDraft.trim() || busy) return;
    setBusy("update");
    try {
      const updated = await updateBlog(activeBlog.id, { title: titleDraft.trim() });
      setActiveBlog(updated);
      setBlogs(current => current.map(b => (b.id === updated.id ? updated : b)));
      setEditingTitle(false);
      showToast("Titre mis à jour");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  // Copy post content formatted cleanly as Markdown
  function handleCopyContent(post: BlogPost) {
    const markdown = formatMarkdownFromPost(post);
    navigator.clipboard.writeText(markdown).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  // Filtered blogs list
  const filteredBlogs = blogs.filter(b => {
    if (!filterQuery.trim()) return true;
    const q = filterQuery.toLowerCase();
    return b.title.toLowerCase().includes(q) || b.prompt.toLowerCase().includes(q);
  });

  const activePost: BlogPost | null =
    activeBlog?.posts?.find(p => p.id === selectedPostId) ??
    (activeBlog?.posts && activeBlog.posts.length > 0 ? activeBlog.posts[0] : null);

  return (
    <div
      className="modal-backdrop"
      onClick={e => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div className="blog-modal" role="dialog" aria-modal="true" aria-label="Mes Blogs et actualités thématiques">
        {/* Top Header */}
        <header className="blog-modal-header">
          <div className="blog-modal-header-left">
            <span className="blog-modal-header-icon">
              <Newspaper size={20} />
            </span>
            <div>
              <h2>Mes Blogs & Veille IA</h2>
              <p>Recherche web d’actualités via SearXNG et synthèses générées automatiquement</p>
            </div>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            disabled={busy === "create"}
            aria-label="Fermer la fenêtre des blogs"
          >
            <X size={18} />
          </button>
        </header>

        {/* Global Toast Notification */}
        {toast && (
          <div className="blog-toast" role="status">
            <Sparkles size={15} />
            <span>{toast}</span>
          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="blog-error-banner" role="alert">
            <CircleAlert size={16} />
            <span>{error}</span>
            <button type="button" onClick={() => setError("")} aria-label="Ignorer l’erreur">
              <X size={14} />
            </button>
          </div>
        )}

        {/* Main Body with 2 panes */}
        <div className="blog-modal-body">
          {/* Left Sidebar: Blogs list & creation button */}
          <aside className="blog-sidebar">
            <div className="blog-sidebar-actions">
              <button
                type="button"
                className={`blog-create-btn ${isCreating ? "active" : ""}`}
                onClick={() => {
                  setIsCreating(true);
                  setError("");
                  setCreatePrompt("");
                  setCreateTitle("");
                }}
              >
                <Plus size={16} />
                <span>Nouveau blog</span>
              </button>
            </div>

            {blogs.length > 3 && (
              <div className="blog-search-box">
                <Search size={14} className="blog-search-icon" />
                <input
                  type="text"
                  placeholder="Filtrer mes blogs…"
                  value={filterQuery}
                  onChange={e => setFilterQuery(e.target.value)}
                  className="blog-search-input"
                />
              </div>
            )}

            <div className="blog-list-container">
              {loading ? (
                <div className="blog-loading-state">
                  <LoaderCircle size={20} className="spin" />
                  <span>Chargement de vos blogs…</span>
                </div>
              ) : filteredBlogs.length > 0 ? (
                <ul className="blog-nav-list" role="list">
                  {filteredBlogs.map(item => {
                    const isSelected = !isCreating && selectedBlogId === item.id;
                    return (
                      <li key={item.id} className="blog-nav-item-row">
                        <button
                          type="button"
                          className={`blog-nav-item ${isSelected ? "is-selected" : ""}`}
                          onClick={() => {
                            setIsCreating(false);
                            setSelectedBlogId(item.id);
                          }}
                        >
                          <div className="blog-nav-item-top">
                            <span className="blog-nav-title">
                              <span className="blog-nav-theme-emoji">{getBlogTheme(item.theme).emoji}</span>
                              <span>{item.title}</span>
                            </span>
                          </div>
                          <span className="blog-nav-prompt">🔍 {item.prompt}</span>
                          <div className="blog-nav-meta">
                            <span>{relativeTime(item.updated_at)}</span>
                            <span className="blog-editions-pill">
                              {item.posts_count} {item.posts_count > 1 ? "éditions" : "édition"}
                            </span>
                          </div>
                        </button>
                        <button
                          type="button"
                          className="blog-item-delete-btn"
                          onClick={() => handleRequestDeleteBlog(item)}
                          title={`Supprimer le blog « ${item.title} »`}
                          aria-label={`Supprimer le blog ${item.title}`}
                        >
                          <Trash2 size={12} />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : blogs.length > 0 ? (
                <div className="blog-empty-filter">
                  <p>Aucun blog ne correspond à votre filtre.</p>
                </div>
              ) : (
                <div className="blog-empty-sidebar">
                  <BookOpen size={24} strokeWidth={1.4} />
                  <p>Créez votre premier blog d'actualités thématiques.</p>
                </div>
              )}
            </div>
          </aside>

          {/* Right Main Pane */}
          <main className="blog-content-pane">
            {isCreating ? (
              /* --- NEW BLOG CREATION FORM --- */
              <div className="blog-create-view">
                <div className="blog-create-header">
                  <span className="blog-create-icon">
                    <Compass size={22} />
                  </span>
                  <div>
                    <h3>Créer un nouveau blog d’actualités</h3>
                    <p>
                      Indiquez un sujet. L’application effectuera une recherche web via SearXNG et rédigera
                      automatiquement les éditions du blog dès que vous le visiterez.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleCreate} className="blog-create-form">
                  <div className="blog-form-group">
                    <label htmlFor="blog-prompt-input">
                      Sujet ou requête web pour le blog <span className="required">*</span>
                    </label>
                    <textarea
                      id="blog-prompt-input"
                      rows={3}
                      placeholder="Ex : Les dernières news IA et modèles de raisonnement"
                      value={createPrompt}
                      onChange={e => setCreatePrompt(e.target.value)}
                      disabled={busy === "create"}
                      required
                      autoFocus
                    />
                  </div>

                  <div className="blog-suggestions-wrap">
                    <span className="blog-suggestions-label">Suggestions en 1 clic :</span>
                    <div className="blog-suggestions-pills">
                      {SUGGESTIONS.map(s => (
                        <button
                          key={s.label}
                          type="button"
                          className="blog-suggestion-pill"
                          disabled={busy === "create"}
                          onClick={() => {
                            setCreatePrompt(s.topic);
                            if (!createTitle) setCreateTitle(s.label);
                          }}
                        >
                          <span>{s.icon}</span>
                          <span>{s.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="blog-form-group">
                    <label htmlFor="blog-title-input">Titre du blog (facultatif)</label>
                    <input
                      id="blog-title-input"
                      type="text"
                      placeholder="Ex : Mon Journal IA (laissé vide, il sera déduit de l'article)"
                      value={createTitle}
                      onChange={e => setCreateTitle(e.target.value)}
                      disabled={busy === "create"}
                      maxLength={180}
                    />
                  </div>

                  <div className="blog-manual-notice">
                    <Sparkles size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                    <div>
                      <strong>Actualisation manuelle à la demande</strong>
                      <p>
                        Générez de nouvelles éditions quand vous le souhaitez grâce au bouton « Actualiser ». Les recherches mondiales et la synthèse sont effectuées par un modèle IA rapide et économique.
                      </p>
                    </div>
                  </div>

                  <div className="blog-form-group">
                    <label>
                      <Palette size={13} style={{ display: "inline", verticalAlign: "middle", marginRight: 5 }} />
                      Thème visuel du blog ({BLOG_THEMES.length} thèmes au choix)
                    </label>
                    <div className="blog-create-theme-grid">
                      {BLOG_THEMES.map(t => {
                        const isChosen = createTheme === t.id;
                        return (
                          <button
                            key={t.id}
                            type="button"
                            className={`blog-create-theme-chip ${isChosen ? "is-selected" : ""}`}
                            onClick={() => setCreateTheme(t.id)}
                            title={`Appliquer le thème ${t.name}`}
                          >
                            <span className="blog-theme-emoji">{t.emoji}</span>
                            <span className="blog-theme-chip-name">{t.name}</span>
                            <span
                              className="blog-theme-chip-dot"
                              style={{ background: `linear-gradient(135deg, ${t.primary}, ${t.secondary})` }}
                            />
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="blog-create-actions">
                    {blogs.length > 0 && (
                      <button
                        type="button"
                        className="blog-cancel-btn"
                        disabled={busy === "create"}
                        onClick={() => {
                          setIsCreating(false);
                          setError("");
                          if (blogs[0]) setSelectedBlogId(blogs[0].id);
                        }}
                      >
                        Annuler
                      </button>
                    )}
                    <button
                      type="submit"
                      className="blog-submit-btn"
                      disabled={busy === "create" || !createPrompt.trim()}
                    >
                      {busy === "create" ? (
                        <>
                          <LoaderCircle size={17} className="spin" />
                          <span>Recherche SearXNG & Rédaction IA en cours…</span>
                        </>
                      ) : (
                        <>
                          <span className="blog-submit-icon-wrap">
                            <Sparkles size={14} />
                          </span>
                          <span>Créer et générer le blog</span>
                        </>
                      )}
                    </button>
                  </div>

                  {busy === "create" && (
                    <div className="blog-creation-progress">
                      <div className="blog-progress-orb">
                        <Globe2 size={24} className="spin-slow" />
                      </div>
                      <h4>Génération de votre blog thématique…</h4>
                      <p>
                        1. Requête web en temps réel envoyée au métamoteur SearXNG<br />
                        2. Sélection des sources les plus récentes et pertinentes<br />
                        3. Rédaction journalistique complète de la première édition par l'IA
                      </p>
                    </div>
                  )}
                </form>
              </div>
            ) : blogLoading ? (
              <div className="blog-loading-viewer">
                <LoaderCircle size={28} className="spin" />
                <p>Chargement du blog et vérification des actualités…</p>
              </div>
            ) : activeBlog ? (
              /* --- BLOG VIEWER --- */
              <div className={`blog-reader-view blog-theme-${getBlogTheme(activeBlog.theme).id}`}>
                {/* Blog Header & Controls */}
                <header className="blog-reader-header">
                  <div className="blog-reader-title-area">
                    {editingTitle ? (
                      <div className="blog-title-edit-row">
                        <input
                          type="text"
                          value={titleDraft}
                          onChange={e => setTitleDraft(e.target.value)}
                          className="blog-title-input"
                          maxLength={180}
                          autoFocus
                        />
                        <button
                          type="button"
                          className="primary-button small-btn"
                          onClick={handleSaveTitle}
                          disabled={busy === "update"}
                        >
                          Enregistrer
                        </button>
                        <button
                          type="button"
                          className="secondary-button small-btn"
                          onClick={() => setEditingTitle(false)}
                        >
                          Annuler
                        </button>
                      </div>
                    ) : (
                      <div className="blog-title-display-row">
                        <h2>{activeBlog.title}</h2>
                        <button
                          type="button"
                          className="icon-button-subtle"
                          title="Modifier le titre"
                          onClick={() => {
                            setTitleDraft(activeBlog.title);
                            setEditingTitle(true);
                          }}
                        >
                          <Pencil size={14} />
                        </button>
                      </div>
                    )}
                    <div className="blog-reader-subrow">
                      <span className="blog-topic-pill" title="Requête web SearXNG">
                        <Globe2 size={12} />
                        <span>Recherche : {activeBlog.prompt}</span>
                      </span>
                      <span className="blog-updated-time">
                        <Clock size={12} />
                        <span>Dernière mise à jour : {relativeTime(activeBlog.updated_at)}</span>
                      </span>
                    </div>
                  </div>

                  <div className="blog-reader-actions">
                    {/* Theme Selector Popover Button */}
                    <div className="blog-theme-selector-container">
                      <button
                        type="button"
                        className="blog-theme-trigger-btn"
                        onClick={() => setIsThemePickerOpen(open => !open)}
                        title="Changer le thème visuel du blog (21 thèmes au choix)"
                        aria-expanded={isThemePickerOpen}
                      >
                        <span
                          className="blog-theme-swatch"
                          style={{
                            background: `linear-gradient(135deg, ${getBlogTheme(activeBlog.theme).primary}, ${getBlogTheme(activeBlog.theme).secondary})`,
                          }}
                        />
                        <Palette size={13} />
                        <span className="blog-theme-trigger-label">
                          {getBlogTheme(activeBlog.theme).emoji} {getBlogTheme(activeBlog.theme).name}
                        </span>
                        <ChevronDown size={12} className={`blog-theme-chevron ${isThemePickerOpen ? "open" : ""}`} />
                      </button>

                      {isThemePickerOpen && (
                        <div className="blog-theme-popover" role="menu" aria-label="Choisir un thème visuel">
                          <div className="blog-theme-popover-header">
                            <div className="blog-theme-popover-title">
                              <Palette size={14} />
                              <span>Choisir le thème ({BLOG_THEMES.length} thèmes)</span>
                            </div>
                            <button
                              type="button"
                              className="blog-theme-popover-close"
                              onClick={() => setIsThemePickerOpen(false)}
                            >
                              <X size={13} />
                            </button>
                          </div>
                          <div className="blog-theme-grid">
                            {BLOG_THEMES.map(themeItem => {
                              const isActive = (activeBlog.theme || "sunset") === themeItem.id;
                              return (
                                <button
                                  key={themeItem.id}
                                  type="button"
                                  className={`blog-theme-option ${isActive ? "is-active" : ""}`}
                                  onClick={() => handleSelectTheme(themeItem.id)}
                                >
                                  <span className="blog-theme-emoji">{themeItem.emoji}</span>
                                  <div className="blog-theme-info">
                                    <span className="blog-theme-name">{themeItem.name}</span>
                                    <div className="blog-theme-palette-preview">
                                      <span style={{ backgroundColor: themeItem.primary }} />
                                      <span style={{ backgroundColor: themeItem.secondary }} />
                                      <span style={{ backgroundColor: themeItem.border }} />
                                    </div>
                                  </div>
                                  {isActive && <Check size={13} className="blog-theme-check" />}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Manual Refresh Button */}
                    <button
                      type="button"
                      className="blog-refresh-action-btn"
                      onClick={() => triggerRefresh(activeBlog.id)}
                      disabled={busy === "refresh"}
                      title="Lancer une recherche mondiale SearXNG et synthétiser une nouvelle édition"
                    >
                      <RefreshCw size={14} className={busy === "refresh" ? "spin" : ""} />
                      <span>{busy === "refresh" ? "Actualisation…" : "Actualiser les actus"}</span>
                    </button>

                    {/* Delete Blog Button */}
                    <button
                      type="button"
                      className="blog-delete-header-btn"
                      onClick={() => handleRequestDeleteBlog(activeBlog)}
                      title="Supprimer définitivement ce blog"
                    >
                      <Trash2 size={13} />
                      <span>Supprimer le blog</span>
                    </button>
                  </div>
                </header>

                {/* Live updating banner */}
                {busy === "refresh" && (
                  <div className="blog-live-banner" role="status">
                    <LoaderCircle size={16} className="spin" />
                    <span>
                      Recherche des dernières actualités en cours via SearXNG et rédaction de la nouvelle édition…
                    </span>
                  </div>
                )}

                {/* Editions timeline switcher */}
                {activeBlog.posts && activeBlog.posts.length > 1 && (
                  <nav className="blog-editions-bar" aria-label="Historique des éditions">
                    <span className="blog-editions-bar-label">
                      <Calendar size={13} />
                      <span>Éditions :</span>
                    </span>
                    <div className="blog-editions-scroll">
                      {activeBlog.posts.map((post, idx) => {
                        const isCurrent = post.id === activePost?.id;
                        return (
                          <button
                            key={post.id}
                            type="button"
                            className={`blog-edition-pill ${isCurrent ? "is-selected" : ""}`}
                            onClick={() => setSelectedPostId(post.id)}
                          >
                            <span>{idx === 0 ? "⚡ Dernière" : `Édition #${activeBlog.posts!.length - idx}`}</span>
                            <span className="blog-edition-date">{formatBlogDate(post.created_at)}</span>
                          </button>
                        );
                      })}
                    </div>
                  </nav>
                )}

                {/* Post Content Area */}
                {activePost ? (
                  <article className="blog-article-wrapper">
                    {/* Article metadata bar */}
                    <div className="blog-article-top">
                      <div className="blog-article-meta">
                        <span className="blog-meta-item">
                          <Calendar size={13} />
                          <span>Publiée le {formatBlogDate(activePost.created_at)}</span>
                        </span>
                        {activePost.sources && activePost.sources.length > 0 && (
                          <span className="blog-meta-item">
                            <Globe2 size={13} />
                            <span>{activePost.sources.length} sources web analysées</span>
                          </span>
                        )}
                      </div>

                      <div className="blog-article-tools">
                        {activePost.cards && activePost.cards.length > 0 && (
                          <div className="blog-view-toggle" role="group" aria-label="Mode d'affichage">
                            <button
                              type="button"
                              className={`blog-view-btn ${viewMode === "cards" ? "is-active" : ""}`}
                              onClick={() => setViewMode("cards")}
                              title="Afficher sous la forme d'encarts colorés"
                            >
                              <LayoutGrid size={13} />
                              <span>Encarts ({activePost.cards.length})</span>
                            </button>
                            <button
                              type="button"
                              className={`blog-view-btn ${viewMode === "text" ? "is-active" : ""}`}
                              onClick={() => setViewMode("text")}
                              title="Afficher en texte continu"
                            >
                              <FileText size={13} />
                              <span>Texte</span>
                            </button>
                          </div>
                        )}

                        <button
                          type="button"
                          className="blog-tool-btn"
                          onClick={() => handleCopyContent(activePost)}
                          title="Copier le texte en Markdown"
                        >
                          {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
                          <span>{copied ? "Copié !" : "Copier"}</span>
                        </button>

                        {activeBlog.posts && activeBlog.posts.length > 1 && (
                          <button
                            type="button"
                            className="blog-tool-btn text-rose-600"
                            onClick={() => handleDeletePost(activeBlog.id, activePost.id)}
                            title="Supprimer cette édition spécifique"
                          >
                            <Trash2 size={14} />
                            <span>Supprimer</span>
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Main Content: Cards Grid or Markdown Text */}
                    {viewMode === "cards" && activePost.cards && activePost.cards.length > 0 ? (
                      <div className="blog-cards-view">
                        {/* Lead Banner */}
                        <header className="blog-lead-banner">
                          <div className="blog-lead-badge">
                            <Globe2 size={13} />
                            <span>Veille internationale · {activePost.cards.length} actualités mondiales traduites en français</span>
                          </div>
                          <h1 className="blog-lead-title">{activePost.title}</h1>
                          {activePost.summary && <p className="blog-lead-summary">{activePost.summary}</p>}
                        </header>

                        {/* Responsive Colored Cards Grid */}
                        <div className="blog-cards-grid">
                          {activePost.cards.map((card, idx) => {
                            const colorClass = `theme-${card.color || "blue"}`;
                            return (
                              <article key={idx} className={`blog-card ${colorClass}`}>
                                <div className="blog-card-top-bar">
                                  <span className="blog-card-tag">{card.tag || "Actualité"}</span>
                                  <span className="blog-card-source" title={`Source média : ${card.source_name}`}>
                                    <Globe2 size={11} />
                                    <span>{card.source_name || "Média web"}</span>
                                  </span>
                                </div>

                                <h3 className="blog-card-title">{card.title}</h3>

                                <p className="blog-card-text">{card.text}</p>

                                <div className="blog-card-actions">
                                  <a
                                    href={card.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="blog-card-link-btn"
                                    title={`Consulter l'article original sur ${card.source_name}`}
                                  >
                                    <span>Consulter la source</span>
                                    <ArrowUpRight size={14} />
                                  </a>
                                  <button
                                    type="button"
                                    className="blog-card-action-btn"
                                    onClick={() =>
                                      handleCopyCard(
                                        `${card.title}\n\n${card.text}\n\nSource (${card.source_name}) : ${card.url}`,
                                        idx
                                      )
                                    }
                                    title="Copier cet encart"
                                  >
                                    {copiedCardIdx === idx ? (
                                      <Check size={13} className="text-emerald-600" />
                                    ) : (
                                      <Copy size={13} />
                                    )}
                                  </button>
                                </div>
                              </article>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
                      /* Markdown Body fallback / continuous text */
                      <div className="blog-article-markdown markdown">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
                          components={{
                            a: ({ href, children }) => (
                              <a href={href} target="_blank" rel="noopener noreferrer" className="blog-inline-link">
                                {children}
                                <ExternalLink size={12} className="blog-ext-icon" />
                              </a>
                            ),
                            pre: ({ children }) => (
                              <div className="code-block">
                                <div className="code-label">
                                  <span>Encart / Code</span>
                                </div>
                                <pre>{children}</pre>
                              </div>
                            ),
                            table: ({ children }) => (
                              <div className="table-scroll">
                                <table>{children}</table>
                              </div>
                            ),
                          }}
                        >
                          {formatMarkdownFromPost(activePost)}
                        </ReactMarkdown>
                      </div>
                    )}

                    {/* Web Sources section */}
                    {activePost.sources && activePost.sources.length > 0 && (
                      <section className="blog-sources-section">
                        <div className="blog-sources-header">
                          <Globe2 size={16} />
                          <h4>Sources web consultées via SearXNG</h4>
                        </div>
                        <div className="blog-sources-grid">
                          {activePost.sources.map((src, sIdx) => {
                            let domain = "";
                            try {
                              domain = new URL(src.url).hostname.replace(/^www\./, "");
                            } catch {
                              domain = "web";
                            }
                            return (
                              <a
                                key={sIdx}
                                href={src.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="blog-source-card"
                              >
                                <div className="blog-source-domain">
                                  <span>{domain}</span>
                                  <ExternalLink size={12} />
                                </div>
                                <h5 className="blog-source-title">{src.title}</h5>
                                {src.snippet && <p className="blog-source-snippet">{src.snippet}</p>}
                              </a>
                            );
                          })}
                        </div>
                      </section>
                    )}
                  </article>
                ) : (
                  <div className="blog-empty-post">
                    <p>Aucune édition disponible pour le moment.</p>
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => triggerRefresh(activeBlog.id)}
                      disabled={busy === "refresh"}
                    >
                      <RefreshCw size={15} />
                      <span>Générer la première édition</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="blog-no-selection">
                <Compass size={32} strokeWidth={1.3} />
                <h3>Sélectionnez un blog ou créez-en un nouveau</h3>
                <p>Suivez les sujets qui vous intéressent grâce aux mises à jour automatiques par le web.</p>
                <button type="button" className="primary-button" onClick={() => setIsCreating(true)}>
                  <Plus size={16} />
                  <span>Nouveau blog</span>
                </button>
              </div>
            )}
          </main>
        </div>
        {/* Blog Deletion Confirmation Modal */}
        {blogToDelete && (
          <div
            className="blog-confirm-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-delete-blog-title"
          >
            <div className="blog-confirm-card">
              <div className="blog-confirm-icon-box">
                <Trash2 size={24} />
              </div>
              <h3 id="confirm-delete-blog-title">Supprimer ce blog ?</h3>
              <p>
                Êtes-vous sûr de vouloir supprimer définitivement le blog <strong>« {blogToDelete.title} »</strong> ?
                Toutes ses éditions ({blogToDelete.posts_count} {blogToDelete.posts_count > 1 ? "éditions" : "édition"}) et ses archives d'actualités seront définitivement effacées.
              </p>
              <div className="blog-confirm-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setBlogToDelete(null)}
                  disabled={busy === "delete"}
                >
                  Annuler
                </button>
                <button
                  type="button"
                  className="blog-confirm-delete-btn"
                  onClick={() => executeDeleteBlog(blogToDelete.id)}
                  disabled={busy === "delete"}
                >
                  {busy === "delete" ? (
                    <>
                      <LoaderCircle size={14} className="spin" />
                      <span>Suppression…</span>
                    </>
                  ) : (
                    <>
                      <Trash2 size={14} />
                      <span>Oui, supprimer le blog</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

