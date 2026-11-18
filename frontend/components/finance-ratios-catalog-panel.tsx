"use client";

import { BookOpen, ChevronDown, ChevronUp, Database, Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { FinanceHelpGuideId } from "@/components/finance-help-modal";
import { FinanceMetricLabel, type FinanceCalcDetail, type MetricCalcStep } from "@/components/finance-info-tip";
import type { UncleStockCatalogItem, UncleStockCatalogPayload } from "@/lib/api";

function fmtCatalogCell(v: number | null | undefined, unit: string, currency: string): string {
  if (v == null || !Number.isFinite(v)) return "—";
  switch (unit) {
    case "pct":
      return `${(v * 100).toFixed(1)}%`;
    case "pct_already":
      return `${v.toFixed(1)}%`;
    case "ratio":
      return `${v.toFixed(2)}×`;
    case "currency":
      if (Math.abs(v) >= 1e9) return `${(v / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} Md`;
      if (Math.abs(v) >= 1e6) return `${Math.round(v / 1e6).toLocaleString("fr-FR")} M`;
      return `${Math.round(v).toLocaleString("fr-FR")} ${currency}`;
    case "per_share":
      return `${v.toFixed(2)} ${currency}`;
    case "days":
      return `${Math.round(v)} j`;
    case "months":
      return `${v.toFixed(1)} m`;
    case "int":
      return Math.round(v).toLocaleString("fr-FR");
    case "bool":
      return v >= 0.5 ? "Oui" : "Non";
    default:
      return v.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
  }
}

function buildCatalogCalcDetail(
  item: UncleStockCatalogItem,
  years: string[],
  currency: string,
): FinanceCalcDetail {
  const steps: MetricCalcStep[] = [];
  if (item.values_by_year.length > 0 && years.length > 0) {
    const startIdx = Math.max(0, years.length - item.values_by_year.length);
    item.values_by_year.forEach((v, i) => {
      const yr = years[startIdx + i] || `N-${item.values_by_year.length - 1 - i}`;
      if (v != null) {
        steps.push({ label: `Exercice ${yr}`, value: fmtCatalogCell(v, item.unit, currency) });
      }
    });
  }

  const sm = item.submetrics;
  if (sm) {
    if (sm.yr_avg) steps.push({ label: "Moyenne 2 ans (.yr avg)", value: sm.yr_avg });
    if (sm.avg_5y) steps.push({ label: "Moyenne 5 ans (.5y avg)", value: sm.avg_5y });
    if (sm.wavg_5y) steps.push({ label: "Moyenne pondérée (.wavg)", value: sm.wavg_5y });
    if (sm.growth_1y) steps.push({ label: "Variation 1 an (.1y growth)", value: sm.growth_1y });
    if (sm.rcagr_67) steps.push({ label: "Tendance prudente (rCAGR 67%)", value: sm.rcagr_67 });
    if (sm.sd_5y) steps.push({ label: "Écart-type 5 ans (.5y SD)", value: sm.sd_5y });
    if (sm.cv_5y) steps.push({ label: "Coeff. de variation (.5y CV)", value: sm.cv_5y });
  }

  const notes: string[] = [];
  if (item.description) notes.push(item.description);
  if (item.method) notes.push(`Méthode : ${item.method}`);
  if (item.example) notes.push(`Exemple illustratif : ${item.example}`);
  if (item.notes) notes.push(item.notes);

  return {
    title: `${item.name} (${item.category})`,
    formula: item.formula || "Poste issu directement des états financiers ou des données marché",
    substitution: item.substitution || undefined,
    result: item.formatted_value,
    steps: steps.length > 0 ? steps : undefined,
    notes: notes.length > 0 ? notes : undefined,
    source: item.section ? `Référentiel Uncle Stock · ${item.category} / ${item.section}` : `Référentiel Uncle Stock · ${item.category}`,
  };
}

/** Explorateur secondaire dépliable des 508 métriques et valeurs calculées du référentiel Uncle Stock. */
export function FinanceRatiosCatalogPanel({
  catalog,
  currency,
  onOpenHelp,
  expanded,
  onToggleExpanded,
}: {
  catalog: UncleStockCatalogPayload | null | undefined;
  currency: string;
  onOpenHelp?: (guide?: FinanceHelpGuideId) => void;
  expanded?: boolean;
  onToggleExpanded?: () => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("Toutes");
  const [onlyComputed, setOnlyComputed] = useState(true);

  const isOpen = expanded ?? internalOpen;
  const handleToggle = () => {
    if (onToggleExpanded) {
      onToggleExpanded();
    } else {
      setInternalOpen(prev => !prev);
    }
  };

  const filteredItems = useMemo(() => {
    if (!catalog) return [];
    const q = query.trim().toLowerCase();
    return catalog.items.filter(it => {
      if (it.unit === "doc" && onlyComputed) return false;
      if (onlyComputed && !it.available) return false;
      if (selectedCategory !== "Toutes" && it.category !== selectedCategory) return false;
      if (!q) return true;
      const hay = `${it.name} ${it.category} ${it.section} ${it.formula} ${it.description}`.toLowerCase();
      return hay.includes(q);
    });
  }, [catalog, query, selectedCategory, onlyComputed]);

  if (!catalog || catalog.items.length === 0) return null;

  const years = catalog.years || [];

  return (
    <section id="dossier-unclestock-catalog" className="finance-dossier-section finance-catalog-drawer">
      <div className="finance-catalog-drawer-head">
        <div className="finance-catalog-drawer-meta">
          <div className="finance-catalog-drawer-title">
            <Database size={16} />
            <div>
              <h4>Référentiel complet Uncle Stock — Valeurs &amp; Formules détaillées</h4>
              <small className="finance-dossier-unit">
                {catalog.computed_count} valeurs calculées sur ce titre / {catalog.total_count} indicateurs du référentiel
                (hors onglets principaux)
              </small>
            </div>
          </div>
        </div>
        <div className="finance-intrinsic-head-actions">
          {onOpenHelp && (
            <button
              type="button"
              className="finance-tf-btn finance-help-inline-btn"
              onClick={() => onOpenHelp("ratios")}
              title="Ouvrir la page web complète du référentiel (508 définitions, filtres & export CSV)"
            >
              <BookOpen size={12} />
              <span>Page web complète</span>
            </button>
          )}
          <button
            type="button"
            className={`finance-tf-btn ${isOpen ? "active" : ""}`}
            onClick={handleToggle}
            aria-expanded={isOpen}
          >
            {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            <span>{isOpen ? "Masquer toutes les valeurs" : `Explorer les ${catalog.total_count} métriques`}</span>
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="finance-catalog-body">
          <div className="finance-catalog-toolbar">
            <div className="finance-catalog-search">
              <Search size={14} />
              <input
                type="search"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Filtrer par nom, formule, bilan, liquidité, solvabilité…"
                aria-label="Rechercher dans le référentiel des 508 métriques"
              />
            </div>
            <label className="finance-catalog-toggle">
              <input
                type="checkbox"
                checked={onlyComputed}
                onChange={e => setOnlyComputed(e.target.checked)}
              />
              <span>Calculées sur ce titre ({catalog.computed_count})</span>
            </label>
          </div>

          <div className="finance-unclestock-filters" role="group" aria-label="Catégories du référentiel">
            <button
              type="button"
              className={`finance-tf-btn ${selectedCategory === "Toutes" ? "active" : ""}`}
              onClick={() => setSelectedCategory("Toutes")}
            >
              Toutes ({onlyComputed ? catalog.computed_count : catalog.total_count})
            </button>
            {catalog.categories.map(cat => (
              <button
                key={cat.name}
                type="button"
                className={`finance-tf-btn ${selectedCategory === cat.name ? "active" : ""}`}
                onClick={() => setSelectedCategory(cat.name)}
              >
                {cat.name} ({onlyComputed ? cat.computed : `${cat.computed}/${cat.total}`})
              </button>
            ))}
          </div>

          <div className="finance-catalog-count">
            {filteredItems.length} indicateur{filteredItems.length > 1 ? "s" : ""} affiché{filteredItems.length > 1 ? "s" : ""}
          </div>

          <div className="finance-table-wrapper finance-catalog-table-wrap finance-stmt-scroll">
            <table className="finance-data-table finance-stmt-table finance-catalog-table">
              <thead>
                <tr>
                  <th className="finance-stmt-sticky-col">Indicateur &amp; Catégorie</th>
                  <th>Dernière valeur</th>
                  {years.map(y => (
                    <th key={`cat-y-${y}`}>{y}</th>
                  ))}
                  <th>Sous-métriques clés</th>
                  <th>Formule Uncle Stock</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={4 + years.length} className="finance-stmt-muted">
                      Aucun indicateur ne correspond aux filtres actuels. Décochez « Calculées sur ce titre » pour voir aussi les postes non publiés.
                    </td>
                  </tr>
                ) : (
                  filteredItems.map(item => (
                    <tr key={item.id} className={!item.available ? "is-muted-row" : undefined}>
                      <td className="finance-stmt-sticky-col">
                        <div className="finance-catalog-name-cell">
                          <FinanceMetricLabel
                            termKey={item.name}
                            label={item.name}
                            calcDetail={buildCatalogCalcDetail(item, years, currency)}
                            strong={item.available}
                          />
                          <small className="finance-catalog-cat-tag">
                            {item.category}
                            {item.section && item.section !== item.category ? ` · ${item.section}` : ""}
                          </small>
                        </div>
                      </td>
                      <td className={item.latest_value != null && item.latest_value < 0 ? "text-rose" : undefined}>
                        <strong>{item.formatted_value}</strong>
                      </td>
                      {years.map((yr, idx) => {
                        const offset = years.length - item.values_by_year.length;
                        const val = idx >= offset ? item.values_by_year[idx - offset] : null;
                        return (
                          <td key={`${item.id}-${yr}`} className={val != null && val < 0 ? "text-rose" : undefined}>
                            {fmtCatalogCell(val, item.unit, currency)}
                          </td>
                        );
                      })}
                      <td>
                        {item.submetrics ? (
                          <div className="finance-catalog-subm">
                            {item.submetrics.avg_5y && <span>Moy.5A : {item.submetrics.avg_5y}</span>}
                            {item.submetrics.growth_1y && <span>1A : {item.submetrics.growth_1y}</span>}
                            {item.submetrics.rcagr_67 && <span>rCAGR67 : {item.submetrics.rcagr_67}</span>}
                          </div>
                        ) : (
                          <span className="finance-stmt-muted">—</span>
                        )}
                      </td>
                      <td>
                        {item.formula ? (
                          <code className="finance-catalog-formula">{item.formula}</code>
                        ) : (
                          <span className="finance-stmt-muted">Donnée directe</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
