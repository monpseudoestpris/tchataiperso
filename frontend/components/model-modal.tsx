"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Brain,
  Check,
  ChevronDown,
  CircleAlert,
  Coins,
  Cpu,
  Eye,
  Layers,
  LoaderCircle,
  RefreshCw,
  Search,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import type { Model } from "@/lib/api";

type ModelModalProps = {
  currentModel: string;
  models: Model[];
  onSelectModel: (modelId: string) => void | Promise<void>;
  onClose: () => void;
  onRefreshModels?: () => Promise<void>;
};

type SortOption = "recommended" | "price_asc" | "price_desc" | "context_desc" | "name_asc";

const POPULAR_PROVIDERS = [
  { id: "all", label: "Tous" },
  { id: "vision", label: "👁️ Vision" },
  { id: "free", label: "🎁 Gratuits" },
  { id: "reasoning", label: "🧠 Raisonnement" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "google", label: "Google" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "mistralai", label: "Mistral" },
  { id: "meta-llama", label: "Meta Llama" },
  { id: "x-ai", label: "xAI" },
  { id: "qwen", label: "Qwen" },
  { id: "moonshotai", label: "Kimi" },
];

function formatTokens(tokens?: number): string {
  if (!tokens || tokens <= 0) return "—";
  if (tokens >= 1_000_000) {
    const val = tokens / 1_000_000;
    return `${val % 1 === 0 ? val.toFixed(0) : val.toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    return `${Math.round(tokens / 1_000)}k`;
  }
  return `${tokens}`;
}

function formatPrice(val?: number): string {
  if (val === undefined || val === null) return "—";
  if (val === 0) return "Gratuit";
  if (val < 0.01) return "<$0.01";
  if (val < 1) return `$${val.toFixed(2)}`;
  return `$${val.toFixed(2)}`;
}

function providerColor(provider?: string): string {
  switch (provider?.toLowerCase()) {
    case "openai":
      return "#10a37f";
    case "anthropic":
      return "#d97706";
    case "google":
      return "#2563eb";
    case "deepseek":
      return "#6366f1";
    case "mistralai":
      return "#ea580c";
    case "meta-llama":
      return "#0284c7";
    case "x-ai":
      return "#334155";
    case "qwen":
      return "#7c3aed";
    case "moonshotai":
      return "#db2777";
    default:
      return "#64748b";
  }
}

export function ModelModal({
  currentModel,
  models,
  onSelectModel,
  onClose,
  onRefreshModels,
}: ModelModalProps) {
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState<string>("all");
  const [sort, setSort] = useState<SortOption>("recommended");
  const [visibleCount, setVisibleCount] = useState(60);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Focus search input on mount and handle Escape key
  useEffect(() => {
    searchInputRef.current?.focus();
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Handle refresh action
  async function handleRefresh() {
    if (!onRefreshModels || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await onRefreshModels();
    } finally {
      setIsRefreshing(false);
    }
  }

  // Filter models
  const filteredModels = useMemo(() => {
    const q = query.trim().toLowerCase();

    return models.filter((item) => {
      // Tab filter
      if (activeTab === "vision" && !item.vision) return false;
      if (activeTab === "free" && item.prompt_price_1m !== 0 && !item.id.endsWith(":free")) return false;
      if (activeTab === "reasoning" && !item.reasoning) return false;
      if (
        !["all", "vision", "free", "reasoning"].includes(activeTab) &&
        (item.provider || "").toLowerCase() !== activeTab.toLowerCase()
      ) {
        return false;
      }

      // Query filter
      if (q) {
        const idMatch = item.id.toLowerCase().includes(q);
        const nameMatch = item.name.toLowerCase().includes(q);
        const providerMatch = (item.provider || "").toLowerCase().includes(q);
        const descMatch = (item.description || "").toLowerCase().includes(q);
        if (!idMatch && !nameMatch && !providerMatch && !descMatch) {
          return false;
        }
      }

      return true;
    });
  }, [models, query, activeTab]);

  // Sort models
  const sortedModels = useMemo(() => {
    const list = [...filteredModels];

    switch (sort) {
      case "price_asc":
        return list.sort((a, b) => (a.prompt_price_1m ?? 9999) - (b.prompt_price_1m ?? 9999));
      case "price_desc":
        return list.sort((a, b) => (b.prompt_price_1m ?? 0) - (a.prompt_price_1m ?? 0));
      case "context_desc":
        return list.sort((a, b) => (b.context_length ?? 0) - (a.context_length ?? 0));
      case "name_asc":
        return list.sort((a, b) => a.name.localeCompare(b.name));
      case "recommended":
      default: {
        // Active model first, then flagship providers (OpenAI, Anthropic, Google, DeepSeek)
        return list.sort((a, b) => {
          if (a.id === currentModel) return -1;
          if (b.id === currentModel) return 1;

          const topProviders = ["openai", "anthropic", "google", "deepseek", "mistralai"];
          const aIndex = topProviders.indexOf(a.provider || "");
          const bIndex = topProviders.indexOf(b.provider || "");

          if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
          if (aIndex !== -1) return -1;
          if (bIndex !== -1) return 1;

          return a.name.localeCompare(b.name);
        });
      }
    }
  }, [filteredModels, sort, currentModel]);

  const displayedModels = sortedModels.slice(0, visibleCount);
  const activeModelObj = models.find((m) => m.id === currentModel);

  return (
    <div className="model-modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Choisir un modèle IA">
      <div className="model-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <header className="model-modal-header">
          <div className="model-modal-header-left">
            <div className="model-modal-badge-icon">
              <Sparkles size={20} />
            </div>
            <div>
              <div className="model-modal-title-row">
                <h2>Sélection du modèle d’intelligence artificielle</h2>
                <span className="model-count-pill">{models.length} modèles disponibles</span>
              </div>
              <p>Explorez les modèles OpenRouter avec tarifs au million de tokens, capacités et contexte.</p>
            </div>
          </div>
          <div className="model-modal-header-right">
            {onRefreshModels && (
              <button
                type="button"
                className="model-refresh-btn"
                onClick={handleRefresh}
                disabled={isRefreshing}
                title="Recharger la liste en direct depuis OpenRouter"
              >
                <RefreshCw size={14} className={isRefreshing ? "spin-icon" : ""} />
                <span>{isRefreshing ? "Actualisation…" : "Actualiser"}</span>
              </button>
            )}
            <button
              type="button"
              className="model-modal-close"
              onClick={onClose}
              aria-label="Fermer la modale"
            >
              <X size={19} />
            </button>
          </div>
        </header>

        {/* Current model reminder banner */}
        {activeModelObj && (
          <div className="model-active-banner">
            <div className="model-active-banner-left">
              <span className="model-active-dot" />
              <span>Modèle actif actuellement :</span>
              <strong>{activeModelObj.name}</strong>
              <code className="model-id-pill">{activeModelObj.id}</code>
            </div>
            <div className="model-active-banner-right">
              {activeModelObj.vision && (
                <span className="model-tag-pill vision">
                  <Eye size={12} />
                  <span>Vision</span>
                </span>
              )}
              {activeModelObj.context_length ? (
                <span className="model-tag-pill context">
                  <Cpu size={12} />
                  <span>{formatTokens(activeModelObj.context_length)} tokens</span>
                </span>
              ) : null}
              <span className="model-tag-pill price">
                <Coins size={12} />
                <span>
                  {activeModelObj.prompt_price_1m === 0
                    ? "Gratuit"
                    : `${formatPrice(activeModelObj.prompt_price_1m)} in / ${formatPrice(activeModelObj.completion_price_1m)} out`}
                </span>
              </span>
            </div>
          </div>
        )}

        {/* Search & Filter Toolbar */}
        <div className="model-modal-toolbar">
          <div className="model-search-box">
            <Search size={16} className="model-search-icon" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Rechercher par nom, ID (ex: astra, gpt-6, opus, flash), fournisseur ou mot-clé…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setVisibleCount(60);
              }}
            />
            {query && (
              <button
                type="button"
                className="model-search-clear"
                onClick={() => setQuery("")}
                aria-label="Effacer la recherche"
              >
                <X size={14} />
              </button>
            )}
          </div>

          <div className="model-sort-box">
            <label htmlFor="model-sort-select">Trier par :</label>
            <div className="model-sort-select-wrap">
              <select
                id="model-sort-select"
                value={sort}
                onChange={(e) => setSort(e.target.value as SortOption)}
              >
                <option value="recommended">Recommandés & Populaires</option>
                <option value="price_asc">Prix croissant (Économique)</option>
                <option value="price_desc">Prix décroissant (Puissant)</option>
                <option value="context_desc">Fenêtre de contexte (Max tokens)</option>
                <option value="name_asc">Nom alphabétique (A-Z)</option>
              </select>
              <ChevronDown size={14} />
            </div>
          </div>
        </div>

        {/* Quick filter pills */}
        <div className="model-filter-tabs">
          {POPULAR_PROVIDERS.map((provider) => {
            const isSelected = activeTab === provider.id;
            return (
              <button
                key={provider.id}
                type="button"
                className={`model-filter-tab ${isSelected ? "is-active" : ""}`}
                onClick={() => {
                  setActiveTab(provider.id);
                  setVisibleCount(60);
                }}
              >
                {provider.label}
              </button>
            );
          })}
        </div>

        {/* Models list */}
        <div className="model-modal-list">
          {displayedModels.length === 0 ? (
            <div className="model-empty-state">
              <CircleAlert size={36} />
              <h3>Aucun modèle ne correspond à votre recherche</h3>
              <p>Essayez de modifier vos termes de recherche ou de sélectionner « Tous ».</p>
              <button
                type="button"
                className="model-reset-search-btn"
                onClick={() => {
                  setQuery("");
                  setActiveTab("all");
                }}
              >
                Réinitialiser les filtres
              </button>
            </div>
          ) : (
            <div className="model-grid">
              {displayedModels.map((item) => {
                const isSelected = item.id === currentModel;
                const pColor = providerColor(item.provider);

                return (
                  <div
                    key={item.id}
                    className={`model-card ${isSelected ? "is-selected" : ""}`}
                    onClick={() => onSelectModel(item.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectModel(item.id);
                      }
                    }}
                  >
                    {/* Card Header */}
                    <div className="model-card-header">
                      <div className="model-card-title-group">
                        <span
                          className="model-provider-badge"
                          style={{
                            backgroundColor: `${pColor}15`,
                            color: pColor,
                            borderColor: `${pColor}30`,
                          }}
                        >
                          {item.provider || "OpenRouter"}
                        </span>
                        <h4 className="model-card-name" title={item.name}>
                          {item.name}
                        </h4>
                      </div>
                      {isSelected ? (
                        <span className="model-active-badge">
                          <Check size={13} />
                          <span>Actif</span>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="model-select-action-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectModel(item.id);
                          }}
                        >
                          Choisir
                        </button>
                      )}
                    </div>

                    {/* Model ID snippet */}
                    <div className="model-card-id-row">
                      <code className="model-card-id">{item.id}</code>
                    </div>

                    {/* Badges row: Vision, Reasoning, Context window */}
                    <div className="model-card-specs">
                      {item.vision ? (
                        <span className="model-spec-badge vision" title="Ce modèle accepte les images en entrée">
                          <Eye size={12} />
                          <span>Vision</span>
                        </span>
                      ) : (
                        <span className="model-spec-badge text-only" title="Modèle textuel">
                          <span>Texte</span>
                        </span>
                      )}

                      {item.reasoning && (
                        <span className="model-spec-badge reasoning" title="Modèle spécialisé en raisonnement et réflexion">
                          <Brain size={12} />
                          <span>Raisonnement</span>
                        </span>
                      )}

                      <span className="model-spec-badge context" title="Longueur maximale du contexte">
                        <Cpu size={12} />
                        <span>{formatTokens(item.context_length)} ctx</span>
                      </span>
                    </div>

                    {/* Pricing section */}
                    <div className="model-card-pricing">
                      <div className="pricing-col">
                        <span className="pricing-label">Entrée (Prompt)</span>
                        <span className={`pricing-val ${item.prompt_price_1m === 0 ? "is-free" : ""}`}>
                          {item.prompt_price_1m === 0 ? "Gratuit" : `${formatPrice(item.prompt_price_1m)} / 1M`}
                        </span>
                      </div>
                      <div className="pricing-divider" />
                      <div className="pricing-col">
                        <span className="pricing-label">Sortie (Réponse)</span>
                        <span className={`pricing-val ${item.completion_price_1m === 0 ? "is-free" : ""}`}>
                          {item.completion_price_1m === 0 ? "Gratuit" : `${formatPrice(item.completion_price_1m)} / 1M`}
                        </span>
                      </div>
                      {item.input_cache_read_price_1m !== null && item.input_cache_read_price_1m !== undefined && (
                        <>
                          <div className="pricing-divider" />
                          <div className="pricing-col" title="Coût de lecture du cache pour les prompts longs">
                            <span className="pricing-label">Cache</span>
                            <span className="pricing-val cache">
                              {formatPrice(item.input_cache_read_price_1m)} / 1M
                            </span>
                          </div>
                        </>
                      )}
                    </div>

                    {/* Description preview */}
                    {item.description && (
                      <p className="model-card-desc" title={item.description}>
                        {item.description}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Load more button */}
          {visibleCount < sortedModels.length && (
            <div className="model-load-more-wrap">
              <button
                type="button"
                className="model-load-more-btn"
                onClick={() => setVisibleCount((prev) => prev + 60)}
              >
                <span>Afficher 60 modèles de plus</span>
                <span className="model-load-more-count">
                  ({displayedModels.length} sur {sortedModels.length})
                </span>
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="model-modal-footer">
          <div className="model-footer-stats">
            <span>
              Affichage de <strong>{displayedModels.length}</strong> modèles sur <strong>{sortedModels.length}</strong> correspondants ({models.length} au total)
            </span>
          </div>
          <button type="button" className="model-footer-close-btn" onClick={onClose}>
            Fermer
          </button>
        </footer>
      </div>
    </div>
  );
}

