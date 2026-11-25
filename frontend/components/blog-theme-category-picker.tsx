"use client";

import { useMemo, useState } from "react";
import {
  Check,
  ExternalLink,
  Globe2,
  Newspaper,
  Rss,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import type { BlogThemeCategoryDef, BlogThemeSourceItem } from "@/lib/api";

export const FALLBACK_BLOG_THEME_CATEGORIES: BlogThemeCategoryDef[] = [
  {
    id: "general",
    group: "Société, Monde & Savoirs",
    label: "Général & Multi-Sources",
    emoji: "🌐",
    description: "Agences de presse mondiales, grands quotidiens de référence et encyclopédies",
    sample_prompts: ["Les grands événements mondiaux et décryptages de la semaine"],
    sources: [
      { name: "Reuters", domain: "reuters.com", kind: "primary" },
      { name: "Associated Press", domain: "apnews.com", kind: "primary" },
      { name: "Franceinfo", domain: "francetvinfo.fr", kind: "primary" },
      { name: "Le Monde", domain: "lemonde.fr", kind: "journal" },
      { name: "Les Échos", domain: "lesechos.fr", kind: "journal" },
      { name: "The Conversation", domain: "theconversation.com", kind: "blog" },
    ],
  },
  {
    id: "cinema_series",
    group: "Culture & Divertissement",
    label: "Cinéma, Séries & Streaming",
    emoji: "🎬",
    description: "Sorties salles, critiques films, séries TV, plateformes VOD et box-office",
    sample_prompts: ["Sorties cinéma de la semaine, critiques et box-office mondial"],
    sources: [
      { name: "AlloCiné", domain: "allocine.fr", kind: "primary" },
      { name: "IMDb", domain: "imdb.com", kind: "primary" },
      { name: "Écran Large", domain: "ecranlarge.com", kind: "primary" },
      { name: "SensCritique", domain: "senscritique.com", kind: "primary" },
      { name: "Rotten Tomatoes", domain: "rottentomatoes.com", kind: "primary" },
      { name: "Première", domain: "premiere.fr", kind: "journal" },
      { name: "Cahiers du Cinéma", domain: "cahiersducinema.com", kind: "journal" },
      { name: "Variety", domain: "variety.com", kind: "journal" },
      { name: "IndieWire", domain: "indiewire.com", kind: "blog" },
      { name: "Critikat", domain: "critikat.com", kind: "blog" },
    ],
  },
  {
    id: "gaming",
    group: "Tech, Gaming & Sciences",
    label: "Jeux Vidéo & Esport",
    emoji: "🎮",
    description: "Tests de jeux PC/PS5/Xbox/Switch, annonces studios, hardware gaming et esport",
    sample_prompts: ["Tests des dernières sorties jeux vidéo, notes et annonces majeures PC et consoles"],
    sources: [
      { name: "JeuxVideo.com", domain: "jeuxvideo.com", kind: "primary" },
      { name: "IGN", domain: "ign.com", kind: "primary" },
      { name: "Gamekult", domain: "gamekult.com", kind: "primary" },
      { name: "Gameblog", domain: "gameblog.fr", kind: "primary" },
      { name: "Canard PC", domain: "canardpc.com", kind: "journal" },
      { name: "PC Gamer", domain: "pcgamer.com", kind: "journal" },
      { name: "Eurogamer", domain: "eurogamer.net", kind: "journal" },
      { name: "Polygon", domain: "polygon.com", kind: "journal" },
      { name: "Kotaku", domain: "kotaku.com", kind: "blog" },
      { name: "ActuGaming", domain: "actugaming.net", kind: "blog" },
    ],
  },
  {
    id: "finance_markets",
    group: "Économie, Finance & Droit",
    label: "Finance, Bourse & Investissement",
    emoji: "📈",
    description: "Marchés actions, CAC 40, S&P 500, ETFs, banques centrales et résultats trimestriels",
    sample_prompts: ["Point marchés boursiers, décisions Fed/BCE et résultats d'entreprises"],
    sources: [
      { name: "Boursorama", domain: "boursorama.com", kind: "primary" },
      { name: "Zonebourse", domain: "zonebourse.com", kind: "primary" },
      { name: "Boursier.com", domain: "boursier.com", kind: "primary" },
      { name: "Investing.com", domain: "investing.com", kind: "primary" },
      { name: "Les Échos", domain: "lesechos.fr", kind: "journal" },
      { name: "Bloomberg", domain: "bloomberg.com", kind: "journal" },
      { name: "Financial Times", domain: "ft.com", kind: "journal" },
      { name: "Avenue des Investisseurs", domain: "avenuedesinvestisseurs.fr", kind: "blog" },
    ],
  },
];

type BlogThemeCategoryPickerProps = {
  categories: BlogThemeCategoryDef[];
  selectedCategoryId: string;
  onSelectCategory: (categoryId: string) => void;
  onApplySamplePrompt?: (samplePrompt: string, categoryLabel: string) => void;
  disabled?: boolean;
  compact?: boolean;
};

const SOURCE_KIND_META: Record<
  BlogThemeSourceItem["kind"],
  { label: string; badgeBg: string; badgeText: string; badgeBorder: string }
> = {
  primary: {
    label: "Sources principales & Portails",
    badgeBg: "var(--accent-subtle, rgba(180, 83, 42, 0.1))",
    badgeText: "var(--accent-primary, #B4532A)",
    badgeBorder: "var(--accent-border, rgba(180, 83, 42, 0.28))",
  },
  journal: {
    label: "Journaux & Magazines",
    badgeBg: "rgba(37, 99, 235, 0.08)",
    badgeText: "var(--text-primary)",
    badgeBorder: "var(--border-subtle)",
  },
  blog: {
    label: "Blogs & Sites experts",
    badgeBg: "rgba(16, 185, 129, 0.08)",
    badgeText: "var(--text-primary)",
    badgeBorder: "var(--border-subtle)",
  },
};

export function BlogThemeCategoryPicker({
  categories,
  selectedCategoryId,
  onSelectCategory,
  onApplySamplePrompt,
  disabled = false,
  compact = false,
}: BlogThemeCategoryPickerProps) {
  const effectiveCategories = categories.length > 0 ? categories : FALLBACK_BLOG_THEME_CATEGORIES;
  const [selectedGroup, setSelectedGroup] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const groups = useMemo(() => {
    const seen: string[] = [];
    for (const c of effectiveCategories) {
      if (c.group && !seen.includes(c.group)) {
        seen.push(c.group);
      }
    }
    return seen;
  }, [effectiveCategories]);

  const filteredCategories = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return effectiveCategories.filter(cat => {
      if (selectedGroup !== "all" && cat.group !== selectedGroup) {
        return false;
      }
      if (!q) return true;
      const inTitle =
        cat.label.toLowerCase().includes(q) ||
        cat.description.toLowerCase().includes(q) ||
        cat.group.toLowerCase().includes(q);
      if (inTitle) return true;
      return cat.sources.some(
        s => s.name.toLowerCase().includes(q) || s.domain.toLowerCase().includes(q),
      );
    });
  }, [effectiveCategories, selectedGroup, searchQuery]);

  const activeCategory = useMemo(
    () =>
      effectiveCategories.find(c => c.id === selectedCategoryId) ||
      effectiveCategories[0],
    [effectiveCategories, selectedCategoryId],
  );

  const groupedSources = useMemo(() => {
    const sources = activeCategory?.sources || [];
    return {
      primary: sources.filter(s => s.kind === "primary"),
      journal: sources.filter(s => s.kind === "journal"),
      blog: sources.filter(s => s.kind === "blog"),
    };
  }, [activeCategory]);

  return (
    <div
      className="blog-theme-cat-picker"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: compact ? 10 : 12,
        padding: compact ? "12px" : "14px 16px",
        borderRadius: 12,
        border: "1px solid var(--border-subtle, rgba(120,120,120,0.22))",
        background: "var(--bg-surface, rgba(255,255,255,0.03))",
      }}
    >
      {/* Top Row: Title + Search Filter */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Globe2 size={15} style={{ color: "var(--accent-primary, #B4532A)" }} />
          <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>
            Catégorie de thème & Sources configurées ({effectiveCategories.length} thèmes)
          </span>
        </div>

        <div
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            minWidth: 230,
            flex: "0 1 280px",
          }}
        >
          <Search
            size={13}
            style={{
              position: "absolute",
              left: 10,
              color: "var(--text-muted, #888)",
              pointerEvents: "none",
            }}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Filtrer thème ou source (ex: AlloCiné, IGN, Bourse…)"
            disabled={disabled}
            aria-label="Filtrer les catégories de thèmes ou les sources"
            style={{
              width: "100%",
              padding: "6px 28px 6px 30px",
              fontSize: "0.78rem",
              borderRadius: 8,
              border: "1px solid var(--border-subtle, rgba(120,120,120,0.25))",
              background: "var(--bg-canvas, transparent)",
              color: "var(--text-primary, inherit)",
            }}
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              aria-label="Effacer la recherche de thème"
              style={{
                position: "absolute",
                right: 6,
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: "var(--text-muted, #888)",
                display: "flex",
                alignItems: "center",
                padding: 2,
              }}
            >
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Family Group Filter Pills */}
      <div
        role="tablist"
        aria-label="Familles de thèmes"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
        }}
      >
        <button
          type="button"
          role="tab"
          aria-selected={selectedGroup === "all"}
          disabled={disabled}
          onClick={() => setSelectedGroup("all")}
          style={{
            padding: "4px 10px",
            borderRadius: 999,
            fontSize: "0.75rem",
            fontWeight: selectedGroup === "all" ? 600 : 500,
            border:
              selectedGroup === "all"
                ? "1px solid var(--accent-primary, #B4532A)"
                : "1px solid var(--border-subtle, rgba(120,120,120,0.22))",
            background:
              selectedGroup === "all"
                ? "var(--accent-subtle, rgba(180, 83, 42, 0.14))"
                : "transparent",
            color:
              selectedGroup === "all"
                ? "var(--accent-primary, #B4532A)"
                : "var(--text-secondary, inherit)",
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          Tous les thèmes ({effectiveCategories.length})
        </button>
        {groups.map(grp => {
          const isActive = selectedGroup === grp;
          const count = effectiveCategories.filter(c => c.group === grp).length;
          return (
            <button
              key={grp}
              type="button"
              role="tab"
              aria-selected={isActive}
              disabled={disabled}
              onClick={() => setSelectedGroup(grp)}
              style={{
                padding: "4px 10px",
                borderRadius: 999,
                fontSize: "0.75rem",
                fontWeight: isActive ? 600 : 500,
                border: isActive
                  ? "1px solid var(--accent-primary, #B4532A)"
                  : "1px solid var(--border-subtle, rgba(120,120,120,0.22))",
                background: isActive
                  ? "var(--accent-subtle, rgba(180, 83, 42, 0.14))"
                  : "transparent",
                color: isActive
                  ? "var(--accent-primary, #B4532A)"
                  : "var(--text-secondary, inherit)",
                cursor: disabled ? "not-allowed" : "pointer",
              }}
            >
              {grp} ({count})
            </button>
          );
        })}
      </div>

      {/* Grid of Theme Categories */}
      {filteredCategories.length === 0 ? (
        <div
          style={{
            padding: "16px",
            textAlign: "center",
            fontSize: "0.82rem",
            color: "var(--text-muted, #888)",
            border: "1px dashed var(--border-subtle, rgba(120,120,120,0.25))",
            borderRadius: 10,
          }}
        >
          Aucune catégorie ou source ne correspond à « {searchQuery} ».
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
            gap: 8,
            maxHeight: compact ? 190 : 240,
            overflowY: "auto",
            paddingRight: 4,
          }}
        >
          {filteredCategories.map(cat => {
            const isSelected = cat.id === activeCategory?.id;
            const previewSources = cat.sources
              .slice(0, 3)
              .map(s => s.name)
              .join(", ");
            return (
              <button
                key={cat.id}
                type="button"
                disabled={disabled}
                onClick={() => onSelectCategory(cat.id)}
                title={`${cat.label} — ${cat.description}`}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  textAlign: "left",
                  gap: 4,
                  padding: "9px 11px",
                  borderRadius: 10,
                  border: isSelected
                    ? "1.5px solid var(--accent-primary, #B4532A)"
                    : "1px solid var(--border-subtle, rgba(120,120,120,0.22))",
                  background: isSelected
                    ? "var(--accent-subtle, rgba(180, 83, 42, 0.1))"
                    : "var(--bg-canvas, rgba(255,255,255,0.02))",
                  cursor: disabled ? "not-allowed" : "pointer",
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    width: "100%",
                    gap: 6,
                  }}
                >
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      fontWeight: 600,
                      fontSize: "0.81rem",
                      color: "var(--text-primary, inherit)",
                      minWidth: 0,
                    }}
                  >
                    <span>{cat.emoji}</span>
                    <span
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {cat.label}
                    </span>
                  </span>
                  <span
                    style={{
                      flexShrink: 0,
                      fontSize: "0.68rem",
                      fontVariantNumeric: "tabular-nums",
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: isSelected
                        ? "var(--accent-primary, #B4532A)"
                        : "var(--bg-elevated, rgba(120,120,120,0.14))",
                      color: isSelected ? "#fff" : "var(--text-muted, #888)",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 3,
                    }}
                  >
                    {isSelected && <Check size={10} strokeWidth={3} />}
                    {cat.sources.length}
                  </span>
                </div>
                <span
                  style={{
                    fontSize: "0.71rem",
                    color: "var(--text-muted, #888)",
                    width: "100%",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {previewSources}
                  {cat.sources.length > 3 ? ` +${cat.sources.length - 3}` : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Selected Theme Sources Drawer */}
      {activeCategory && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            padding: "10px 12px",
            borderRadius: 10,
            background: "var(--bg-canvas, rgba(0,0,0,0.03))",
            border: "1px solid var(--border-subtle, rgba(120,120,120,0.2))",
          }}
        >
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ fontSize: "1.05rem" }}>{activeCategory.emoji}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.82rem" }}>
                  {activeCategory.label}{" "}
                  <span
                    style={{
                      fontWeight: 500,
                      fontSize: "0.74rem",
                      color: "var(--text-muted, #888)",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    ({activeCategory.sources.length} sources JSON configurées)
                  </span>
                </div>
                <div style={{ fontSize: "0.73rem", color: "var(--text-muted, #888)" }}>
                  {activeCategory.description}
                </div>
              </div>
            </div>

            {onApplySamplePrompt &&
              activeCategory.sample_prompts &&
              activeCategory.sample_prompts.length > 0 && (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() =>
                    onApplySamplePrompt(activeCategory.sample_prompts![0], activeCategory.label)
                  }
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    padding: "4px 9px",
                    borderRadius: 7,
                    fontSize: "0.73rem",
                    fontWeight: 500,
                    border: "1px solid var(--border-subtle, rgba(120,120,120,0.25))",
                    background: "var(--bg-surface, transparent)",
                    color: "var(--text-primary, inherit)",
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                  title="Remplir avec un exemple de sujet pour cette catégorie"
                >
                  <Sparkles size={12} />
                  <span>Idée de prompt</span>
                </button>
              )}
          </div>

          {/* 3-tier sources breakdown: primary, journal, blog */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {(["primary", "journal", "blog"] as const).map(kind => {
              const list = groupedSources[kind];
              if (!list || list.length === 0) return null;
              const meta = SOURCE_KIND_META[kind];
              return (
                <div
                  key={kind}
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: 5,
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      fontSize: "0.71rem",
                      fontWeight: 600,
                      color: "var(--text-muted, #888)",
                      minWidth: 165,
                    }}
                  >
                    {kind === "primary" ? (
                      <Globe2 size={11} />
                    ) : kind === "journal" ? (
                      <Newspaper size={11} />
                    ) : (
                      <Rss size={11} />
                    )}
                    <span>{meta.label} :</span>
                  </span>
                  {list.map(src => (
                    <a
                      key={`${kind}-${src.domain}-${src.name}`}
                      href={src.url || `https://${src.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`${src.name} (${src.domain})`}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                        padding: "2px 7px",
                        borderRadius: 6,
                        fontSize: "0.71rem",
                        textDecoration: "none",
                        background: meta.badgeBg,
                        color: meta.badgeText,
                        border: `1px solid ${meta.badgeBorder}`,
                      }}
                    >
                      <span>{src.name}</span>
                      <span style={{ opacity: 0.65, fontSize: "0.66rem" }}>({src.domain})</span>
                      <ExternalLink size={9} style={{ opacity: 0.6 }} />
                    </a>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
