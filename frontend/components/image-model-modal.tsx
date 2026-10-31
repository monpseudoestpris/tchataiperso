"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  CircleAlert,
  Coins,
  Cpu,
  Eye,
  ImagePlus,
  Layers,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import type { ImageModel } from "@/lib/api";

type ImageModelModalProps = {
  currentModel: string;
  models: ImageModel[];
  onSelectModel: (modelId: string) => void;
  onClose: () => void;
  onRefreshModels?: () => Promise<void>;
};

type SortOption = "recommended" | "name_asc";

const IMAGE_PROVIDERS = [
  { id: "all", label: "Tous" },
  { id: "top", label: "⭐ Top Collection" },
  { id: "ideogram", label: "Ideogram v2" },
  { id: "google", label: "Google" },
  { id: "openai", label: "OpenAI" },
  { id: "bytedance", label: "ByteDance" },
  { id: "black-forest-labs", label: "FLUX / BFL" },
  { id: "recraft", label: "Recraft" },
  { id: "other", label: "Autres" },
];

function providerColor(id: string): string {
  const p = id.split("/")[0].toLowerCase();
  switch (p) {
    case "google":
      return "#2563eb";
    case "openai":
      return "#10a37f";
    case "bytedance-seed":
    case "bytedance":
      return "#0284c7";
    case "black-forest-labs":
      return "#7c3aed";
    case "recraft":
      return "#ea580c";
    case "ideogram":
      return "#db2777";
    case "meta":
      return "#0284c7";
    case "tencent":
      return "#059669";
    case "krea":
      return "#d97706";
    default:
      return "#64748b";
  }
}

export function ImageModelModal({
  currentModel,
  models,
  onSelectModel,
  onClose,
  onRefreshModels,
}: ImageModelModalProps) {
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState<string>("all");
  const [sort, setSort] = useState<SortOption>("recommended");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

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

  async function handleRefresh() {
    if (!onRefreshModels || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await onRefreshModels();
    } finally {
      setIsRefreshing(false);
    }
  }

  const filteredModels = useMemo(() => {
    const q = query.trim().toLowerCase();

    return models.filter(item => {
      // Tab filter
      if (activeTab === "top" && !item.is_top) return false;
      if (activeTab === "google" && !item.id.toLowerCase().startsWith("google/")) return false;
      if (activeTab === "openai" && !item.id.toLowerCase().startsWith("openai/")) return false;
      if (
        activeTab === "bytedance" &&
        !item.id.toLowerCase().startsWith("bytedance")
      ) {
        return false;
      }
      if (
        activeTab === "black-forest-labs" &&
        !item.id.toLowerCase().startsWith("black-forest-labs")
      ) {
        return false;
      }
      if (activeTab === "recraft" && !item.id.toLowerCase().startsWith("recraft")) return false;
      if (activeTab === "ideogram" && item.provider !== "ideogram" && item.id !== "ideogram") return false;
      if (activeTab === "other") {
        const p = item.id.split("/")[0].toLowerCase();
        if (["google", "openai", "bytedance-seed", "black-forest-labs", "recraft", "ideogram"].includes(p)) {
          return false;
        }
      }

      // Text query filter
      if (q) {
        const idMatch = item.id.toLowerCase().includes(q);
        const nameMatch = item.name.toLowerCase().includes(q);
        const descMatch = (item.description || "").toLowerCase().includes(q);
        const priceMatch = (item.pricing_text || "").toLowerCase().includes(q);
        if (!idMatch && !nameMatch && !descMatch && !priceMatch) {
          return false;
        }
      }

      return true;
    });
  }, [models, query, activeTab]);

  const sortedModels = useMemo(() => {
    const list = [...filteredModels];
    if (sort === "name_asc") {
      return list.sort((a, b) => a.name.localeCompare(b.name));
    }
    // "recommended"
    return list.sort((a, b) => {
      if (a.id === currentModel) return -1;
      if (b.id === currentModel) return 1;
      if (a.id === "ideogram") return -1;
      if (b.id === "ideogram") return 1;
      if (a.is_top && !b.is_top) return -1;
      if (!a.is_top && b.is_top) return 1;
      return a.name.localeCompare(b.name);
    });
  }, [filteredModels, sort, currentModel]);

  const activeModelObj = models.find(m => m.id === currentModel) || models[0];

  return (
    <div
      className="model-modal-overlay image-model-modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Sélection du modèle de génération d'image & vision"
    >
      <div className="model-modal-container image-model-modal-container" onClick={e => e.stopPropagation()}>
        {/* En-tête de la modale */}
        <header className="model-modal-header">
          <div className="model-modal-header-left">
            <div className="model-modal-badge-icon" style={{ background: "linear-gradient(135deg, #ec4899 0%, #8b5cf6 50%, #6366f1 100%)" }}>
              <ImagePlus size={20} />
            </div>
            <div>
              <div className="model-modal-title-row">
                <h2>Sélection du modèle d'image & vision</h2>
                <span className="model-count-pill">{models.length} modèles disponibles</span>
              </div>
              <p>Modèles officiels d'OpenRouter Image API & Ideogram avec tarifs directs, résolutions et capacités.</p>
            </div>
          </div>
          <div className="model-modal-header-right">
            {onRefreshModels && (
              <button
                type="button"
                className="model-refresh-btn"
                onClick={handleRefresh}
                disabled={isRefreshing}
                title="Actualiser les modèles et tarifs en temps réel depuis OpenRouter"
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

        {/* Bannière du modèle actif */}
        {activeModelObj && (
          <div className="model-active-banner">
            <div className="model-active-banner-left">
              <span className="model-active-dot" />
              <span>Modèle sélectionné :</span>
              <strong>{activeModelObj.name}</strong>
              <code className="model-id-pill">{activeModelObj.id}</code>
            </div>
            <div className="model-active-banner-right">
              {activeModelObj.is_top && (
                <span className="model-tag-pill vision" style={{ background: "#fef3c7", color: "#b45309", borderColor: "#fde68a" }}>
                  <Sparkles size={11} />
                  <span>Top Collection</span>
                </span>
              )}
              {activeModelObj.pricing_text && (
                <span className="model-tag-pill price">
                  <Coins size={12} />
                  <span>{activeModelObj.pricing_text}</span>
                </span>
              )}
              {activeModelObj.supported_resolutions && activeModelObj.supported_resolutions.length > 0 && (
                <span className="model-tag-pill context">
                  <Layers size={12} />
                  <span>Max : {activeModelObj.supported_resolutions[activeModelObj.supported_resolutions.length - 1]}</span>
                </span>
              )}
            </div>
          </div>
        )}

        {/* Barre d'outils : Recherche et Tri */}
        <div className="model-modal-toolbar">
          <div className="model-search-box">
            <Search size={16} className="model-search-icon" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Rechercher par nom (ex: Banana, Sunburst, Flux, Seedream, Recraft, 4K)..."
              value={query}
              onChange={e => setQuery(e.target.value)}
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
            <label htmlFor="image-model-sort-select">Trier par :</label>
            <div className="model-sort-select-wrap">
              <select
                id="image-model-sort-select"
                value={sort}
                onChange={e => setSort(e.target.value as SortOption)}
              >
                <option value="recommended">Recommandés (Top Collection)</option>
                <option value="name_asc">Nom alphabétique (A-Z)</option>
              </select>
              <ChevronDown size={14} />
            </div>
          </div>
        </div>

        {/* Onglets de filtrage par famille / provider */}
        <div className="model-filter-tabs">
          {IMAGE_PROVIDERS.map(provider => {
            const isSelected = activeTab === provider.id;
            return (
              <button
                key={provider.id}
                type="button"
                className={`model-filter-tab ${isSelected ? "is-active" : ""}`}
                onClick={() => setActiveTab(provider.id)}
              >
                {provider.label}
              </button>
            );
          })}
        </div>

        {/* Liste des cartes de modèles */}
        <div className="model-modal-list">
          {sortedModels.length === 0 ? (
            <div className="model-empty-state">
              <CircleAlert size={36} />
              <h3>Aucun modèle d'image ne correspond à votre recherche</h3>
              <p>Modifiez vos termes de recherche ou choisissez l'onglet « Tous ».</p>
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
              {sortedModels.map(item => {
                const isSelected = item.id === currentModel;
                const pColor = providerColor(item.id);
                const providerLabel =
                  item.provider === "ideogram"
                    ? "Ideogram v2"
                    : item.id.split("/")[0].replace("-", " ").toUpperCase();

                return (
                  <div
                    key={item.id}
                    className={`model-card ${isSelected ? "is-selected" : ""}`}
                    onClick={() => {
                      onSelectModel(item.id);
                      onClose();
                    }}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectModel(item.id);
                        onClose();
                      }
                    }}
                  >
                    {/* En-tête de la carte */}
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
                          {providerLabel}
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
                          onClick={e => {
                            e.stopPropagation();
                            onSelectModel(item.id);
                            onClose();
                          }}
                        >
                          Choisir
                        </button>
                      )}
                    </div>

                    {/* ID du modèle & Top badge */}
                    <div className="model-card-id-row">
                      <code className="model-card-id">{item.id}</code>
                      {item.is_top && (
                        <span
                          className="image-model-top-badge"
                          style={{ fontSize: "10px", padding: "1px 6px" }}
                          title="Fait partie du Top 12 d'OpenRouter Image Models"
                        >
                          <Sparkles size={10} />
                          <span>Top Collection</span>
                        </span>
                      )}
                    </div>

                    {/* Spécifications : Tarif, Résolution, Ratios */}
                    <div className="model-card-specs">
                      {item.pricing_text && (
                        <span className="model-spec-badge price" style={{ background: "#ecfdf5", color: "#065f46", borderColor: "#a7f3d0" }} title="Tarif de génération">
                          <Coins size={12} />
                          <strong>{item.pricing_text}</strong>
                        </span>
                      )}
                      {item.supported_resolutions && item.supported_resolutions.length > 0 && (
                        <span className="model-spec-badge context" title="Résolutions supportées">
                          <Layers size={12} />
                          <span>Max : {item.supported_resolutions[item.supported_resolutions.length - 1]}</span>
                        </span>
                      )}
                      {item.supported_aspect_ratios && item.supported_aspect_ratios.length > 0 && (
                        <span className="model-spec-badge vision" title="Formats d'aspect pris en charge">
                          <Eye size={12} />
                          <span>{item.supported_aspect_ratios.length} formats</span>
                        </span>
                      )}
                    </div>

                    {/* Description */}
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
        </div>

        {/* Pied de page */}
        <footer className="model-modal-footer">
          <div className="model-modal-footer-left">
            <span>
              {sortedModels.length} modèle{sortedModels.length > 1 ? "s" : ""} affiché{sortedModels.length > 1 ? "s" : ""}
            </span>
          </div>
          <div className="model-modal-footer-right">
            <button type="button" className="model-footer-close-btn" onClick={onClose}>
              Fermer
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

