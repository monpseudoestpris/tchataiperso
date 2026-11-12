"use client";

import { useMemo, useState } from "react";
import { Check, Cpu, Sparkles, Star, X, Zap } from "lucide-react";
import type { Model } from "@/lib/api";
import { useModelFavorites } from "@/lib/model-favorites";
import styles from "./model-picker-modal.module.css";

export type ModelPickerModalProps = {
  isOpen: boolean;
  onClose: () => void;
  models: Model[];
  selectedModelId: string;
  onSelectModel: (modelId: string) => void;
};

export function ModelPickerModal({
  isOpen,
  onClose,
  models,
  selectedModelId,
  onSelectModel,
}: ModelPickerModalProps) {
  const { favoritesSet, isFavorite, toggleFavorite } = useModelFavorites("llm");
  const [search, setSearch] = useState("");

  const filteredModels = useMemo(() => {
    if (!search.trim()) return models;
    const q = search.toLowerCase();
    return models.filter(
      (m) =>
        (m.name || "").toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        (m.provider || "").toLowerCase().includes(q)
    );
  }, [models, search]);

  // Sort with favorites at the head ("en tête")
  const sortedModels = useMemo(() => {
    return [...filteredModels].sort((a, b) => {
      const aFav = favoritesSet.has(a.id);
      const bFav = favoritesSet.has(b.id);
      if (aFav && !bFav) return -1;
      if (!aFav && bFav) return 1;

      if (a.id === selectedModelId) return -1;
      if (b.id === selectedModelId) return 1;

      return 0;
    });
  }, [filteredModels, favoritesSet, selectedModelId]);

  if (!isOpen) return null;

  function getModelDetails(model: Model) {
    const id = model.id.toLowerCase();
    const isRecommended =
      id.includes("flash") || id.includes("sonnet") || id.includes("2.5");
    const isFast = id.includes("flash") || id.includes("mini") || id.includes("haiku");
    const isDeep = id.includes("pro") || id.includes("opus") || id.includes("o1");

    let description = "Modèle IA adapté pour la conception et l'analyse de contenu.";
    if (id.includes("flash")) {
      description =
        "Ultra-rapide et économique : idéal pour cLAIr Pages avec génération de HTML5, CSS3 et SVG inline en quelques secondes.";
    } else if (id.includes("pro") || id.includes("opus")) {
      description =
        "Raisonnement approfondi : recommandé pour les sujets techniques denses, analyses scientifiques et schémas conceptuels riches.";
    } else if (id.includes("sonnet")) {
      description =
        "Excellence graphique : remarquable pour la mise en page CSS moderne et l'élégance typographique.";
    }

    return { isRecommended, isFast, isDeep, description };
  }

  return (
    <div className={styles.backdrop} onClick={onClose} role="dialog" aria-modal="true">
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.titleArea}>
            <div className={styles.iconBadge}>
              <Cpu size={18} />
            </div>
            <div>
              <h3 className={styles.title}>Choisir un Modèle IA</h3>
              <p className={styles.subtitle}>
                Sélectionnez le moteur pour générer et faire évoluer vos pages web
              </p>
            </div>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Fermer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Search */}
        <div className={styles.searchBar}>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Rechercher un modèle (Google, Gemini, Claude, OpenAI...)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
        </div>

        {/* Models List */}
        <div className={styles.list}>
          {sortedModels.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "#64748b", fontSize: "0.85rem" }}>
              Aucun modèle ne correspond à votre recherche.
            </div>
          ) : (
            sortedModels.map((m) => {
              const isSelected = selectedModelId === m.id;
              const isFav = isFavorite(m.id);
              const { isRecommended, isFast, isDeep, description } = getModelDetails(m);

              return (
                <div
                  key={m.id}
                  className={`${styles.modelCard} ${isSelected ? styles.selected : ""}`}
                  onClick={() => {
                    onSelectModel(m.id);
                    onClose();
                  }}
                >
                  <div className={styles.cardTop}>
                    <div className={styles.modelNameRow}>
                      <span className={styles.modelName}>{m.name || m.id}</span>
                      {m.provider && (
                        <span className={styles.providerBadge}>{m.provider}</span>
                      )}
                    </div>

                    <div className={styles.tagPills}>
                      <button
                        type="button"
                        className={`${styles.favoriteBtn} ${isFav ? styles.isFavorite : ""}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleFavorite(m.id);
                        }}
                        title={isFav ? "Retirer des favoris" : "Ajouter aux favoris"}
                        aria-label={isFav ? "Retirer des favoris" : "Ajouter aux favoris"}
                      >
                        <Star
                          size={15}
                          fill={isFav ? "#f59e0b" : "none"}
                          color={isFav ? "#f59e0b" : "#94a3b8"}
                        />
                      </button>
                      {isFav && (
                        <span className={styles.pillFavorite}>
                          <Star size={11} fill="currentColor" />
                          <span>Favori</span>
                        </span>
                      )}
                      {isRecommended && (
                        <span className={styles.pillRecommended}>
                          <Sparkles size={11} />
                          <span>Recommandé</span>
                        </span>
                      )}
                      {isFast && (
                        <span className={styles.pillSpeed}>
                          <Zap size={11} style={{ marginRight: 2 }} />
                          <span>Rapide</span>
                        </span>
                      )}
                      {isDeep && (
                        <span className={styles.pillSpeed} style={{ background: "rgba(124, 58, 237, 0.12)", color: "#7c3aed" }}>
                          <span>Raisonnement</span>
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={styles.modelDesc}>{description}</div>

                  <div className={styles.cardFooter}>
                    <span style={{ fontFamily: "monospace", fontSize: "0.68rem" }}>{m.id}</span>
                    {isSelected ? (
                      <span className={styles.selectedBadge}>
                        <Check size={14} />
                        <span>Sélectionné</span>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className={styles.selectBtn}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectModel(m.id);
                          onClose();
                        }}
                      >
                        Choisir ce modèle
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

