"use client";

import {
  ArrowDown,
  ArrowUp,
  Database,
  Download,
  Filter,
  LineChart,
  LoaderCircle,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  exportScreenerToWatchlist,
  fetchFinanceScreenerMeta,
  hydrateFinanceScreener,
  queryFinanceScreener,
  rebuildFinanceScreener,
  type FinanceWatchlistMeta,
  type PrincipalIndexInfo,
  type ScreenerCoverage,
  type ScreenerFieldMeta,
  type ScreenerPreset,
  type ScreenerRow,
  type ScreenerRule,
} from "@/lib/api";

import styles from "./finance-screener-panel.module.css";

type FinanceScreenerPanelProps = {
  indices: PrincipalIndexInfo[];
  watchlists: FinanceWatchlistMeta[];
  activeListId: string | null;
  onOpenStock: (target: string, displayName: string, openTab: "fundamentals" | "chart_tech") => void | Promise<void>;
  onWatchlistExported: (listId: string) => void | Promise<void>;
};

type ColumnGroup = "overview" | "valuation" | "quality" | "technical";

type EditableRule = {
  id: string;
  kind: "metric" | "compare" | "signal";
  field: string;
  op: string;
  value: string;
  valueMax: string;
  left: string;
  right: string;
};

const CATEGORY_LABELS: Record<ScreenerFieldMeta["category"], string> = {
  performance: "Cours & Performances",
  valuation: "Valorisation",
  quality: "Qualité, Rentabilité & Bilan",
  scores: "Scores & Intrinsèque",
  technical: "Indicateurs Techniques",
};

const METRIC_OPS = [
  { value: "gte", label: "≥" },
  { value: "gt", label: ">" },
  { value: "lte", label: "≤" },
  { value: "lt", label: "<" },
  { value: "between", label: "Entre" },
  { value: "eq", label: "=" },
];

const COMPARE_OPS = [
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
];

let ruleSeq = 0;
function nextRuleId(): string {
  ruleSeq += 1;
  return `scr-rule-${ruleSeq}`;
}

function ruleToEditable(rule: ScreenerRule): EditableRule {
  if (rule.kind === "compare") {
    return {
      id: nextRuleId(),
      kind: "compare",
      field: "rsi_14",
      op: rule.op,
      value: "",
      valueMax: "",
      left: rule.left,
      right: rule.right,
    };
  }
  if (rule.kind === "signal") {
    const valStr = Array.isArray(rule.value) ? String(rule.value[0] ?? 1) : String(rule.value ?? 1);
    return {
      id: nextRuleId(),
      kind: "signal",
      field: rule.field,
      op: "eq",
      value: valStr,
      valueMax: "",
      left: "price",
      right: "sma200",
    };
  }
  return {
    id: nextRuleId(),
    kind: "metric",
    field: rule.field,
    op: rule.op,
    value: rule.value != null ? String(rule.value) : "",
    valueMax: rule.value_max != null ? String(rule.value_max) : "",
    left: "price",
    right: "sma200",
  };
}

function editableToApiRules(rules: EditableRule[], fieldsByKey: Map<string, ScreenerFieldMeta>): ScreenerRule[] {
  const out: ScreenerRule[] = [];
  for (const r of rules) {
    if (r.kind === "compare") {
      if (r.left && r.right && r.left !== r.right) {
        out.push({
          kind: "compare",
          left: r.left,
          op: (["gt", "gte", "lt", "lte"].includes(r.op) ? r.op : "gt") as "gt" | "gte" | "lt" | "lte",
          right: r.right,
        });
      }
      continue;
    }
    const meta = fieldsByKey.get(r.field);
    if (!meta) continue;
    if (r.kind === "signal" || meta.type === "signal") {
      const n = Number(r.value);
      if (Number.isFinite(n)) {
        out.push({ kind: "signal", field: r.field, op: "eq", value: n });
      }
      continue;
    }
    if (r.op === "between") {
      const lo = Number(r.value.replace(",", "."));
      const hi = Number(r.valueMax.replace(",", "."));
      if (Number.isFinite(lo) && Number.isFinite(hi)) {
        out.push({ kind: "metric", field: r.field, op: "between", value: lo, value_max: hi });
      }
      continue;
    }
    const v = Number(r.value.replace(",", "."));
    if (r.value.trim() !== "" && Number.isFinite(v)) {
      out.push({
        kind: "metric",
        field: r.field,
        op: (["gt", "gte", "lt", "lte", "eq", "neq"].includes(r.op) ? r.op : "gte") as
          | "gt"
          | "gte"
          | "lt"
          | "lte"
          | "eq"
          | "neq",
        value: v,
      });
    }
  }
  return out;
}

function fmtNum(v: number | null | undefined, digits = 2, suffix = ""): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

function fmtSignedPct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function fmtMcap(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)} T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)} Md`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(0)} M`;
  return v.toFixed(0);
}

function MiniSparkline({ points }: { points: number[] }) {
  if (!points || points.length < 2) return <span className={styles.muted}>—</span>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const w = 68;
  const h = 22;
  const coords = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - 2 - ((p - min) / span) * (h - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const isUp = points[points.length - 1] >= points[0];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className={styles.sparkline} aria-hidden="true">
      <polyline
        fill="none"
        stroke={isUp ? "#10b981" : "#f43f5e"}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={coords}
      />
    </svg>
  );
}

/**
 * Onglet Screener Boursier intégré (V1 simple + contrat extensible pour formules personnalisées).
 */
export function FinanceScreenerPanel({
  indices,
  watchlists,
  activeListId,
  onOpenStock,
  onWatchlistExported,
}: FinanceScreenerPanelProps) {
  const [fields, setFields] = useState<ScreenerFieldMeta[]>([]);
  const [presets, setPresets] = useState<ScreenerPreset[]>([]);
  const [coverage, setCoverage] = useState<ScreenerCoverage | null>(null);

  const [universeType, setUniverseType] = useState<"all" | "index" | "watchlist">("all");
  const [universeValue, setUniverseValue] = useState<string>("");
  const [searchText, setSearchText] = useState<string>("");
  const [sectorFilter, setSectorFilter] = useState<string>("");
  const [onlyWithFundamentals, setOnlyWithFundamentals] = useState<boolean>(false);
  const [rules, setRules] = useState<EditableRule[]>([]);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<string>("market_cap");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [columnGroup, setColumnGroup] = useState<ColumnGroup>("overview");

  const [items, setItems] = useState<ScreenerRow[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [universeTotal, setUniverseTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [hydrating, setHydrating] = useState<boolean>(false);
  const [exporting, setExporting] = useState<boolean>(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fieldsByKey = useMemo(() => {
    const m = new Map<string, ScreenerFieldMeta>();
    for (const f of fields) m.set(f.key, f);
    return m;
  }, [fields]);

  const comparableFields = useMemo(
    () => fields.filter(f => f.comparable),
    [fields],
  );

  const fieldsGrouped = useMemo(() => {
    const order: ScreenerFieldMeta["category"][] = [
      "valuation",
      "quality",
      "scores",
      "technical",
      "performance",
    ];
    return order
      .map(cat => ({
        category: cat,
        label: CATEGORY_LABELS[cat],
        items: fields.filter(f => f.category === cat),
      }))
      .filter(g => g.items.length > 0);
  }, [fields]);

  const apiRules = useMemo(() => editableToApiRules(rules, fieldsByKey), [rules, fieldsByKey]);

  const runQuery = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await queryFinanceScreener({
        universe_type: universeType,
        universe_value: universeType === "all" ? null : universeValue || null,
        search: searchText,
        sector: sectorFilter,
        only_with_fundamentals: onlyWithFundamentals,
        rules: apiRules,
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: 120,
        offset: 0,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
      setUniverseTotal(res.universe_total || 0);
      setCoverage(res.coverage);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'exécution du screener.");
    } finally {
      setLoading(false);
    }
  }, [universeType, universeValue, searchText, sectorFilter, onlyWithFundamentals, apiRules, sortBy, sortDir]);

  // Charge les métadonnées (champs, presets, couverture) à l'ouverture
  useEffect(() => {
    let cancelled = false;
    fetchFinanceScreenerMeta()
      .then(meta => {
        if (cancelled) return;
        setFields(meta.fields || []);
        setPresets(meta.presets || []);
        setCoverage(meta.coverage);
      })
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Impossible d'initialiser le screener.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Exécute la requête avec un court debounce dès qu'un filtre change
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void runQuery();
    }, 180);
    return () => window.clearTimeout(timer);
  }, [runQuery]);

  function handleApplyPreset(preset: ScreenerPreset) {
    setActivePresetId(preset.id);
    setRules(preset.rules.map(ruleToEditable));
    setSortBy(preset.sort_by || "market_cap");
    setSortDir(preset.sort_dir || "desc");
    setBanner(null);
  }

  function handleResetFilters() {
    setActivePresetId(null);
    setRules([]);
    setSearchText("");
    setSectorFilter("");
    setOnlyWithFundamentals(false);
    setSortBy("market_cap");
    setSortDir("desc");
    setBanner(null);
  }

  function handleAddMetricRule() {
    setActivePresetId(null);
    setRules(prev => [
      ...prev,
      {
        id: nextRuleId(),
        kind: "metric",
        field: "rsi_14",
        op: "lte",
        value: "40",
        valueMax: "",
        left: "price",
        right: "sma200",
      },
    ]);
  }

  function handleAddCompareRule() {
    setActivePresetId(null);
    setRules(prev => [
      ...prev,
      {
        id: nextRuleId(),
        kind: "compare",
        field: "rsi_14",
        op: "gt",
        value: "",
        valueMax: "",
        left: "price",
        right: "sma200",
      },
    ]);
  }

  function handleUpdateRule(id: string, patch: Partial<EditableRule>) {
    setActivePresetId(null);
    setRules(prev =>
      prev.map(r => {
        if (r.id !== id) return r;
        const next = { ...r, ...patch };
        if (patch.field) {
          const meta = fieldsByKey.get(patch.field);
          if (meta?.type === "signal") {
            next.kind = "signal";
            next.op = "eq";
            next.value = String(meta.options?.[0]?.value ?? 1);
          } else if (r.kind === "signal") {
            next.kind = "metric";
            next.op = "gte";
            next.value = "";
          }
        }
        return next;
      }),
    );
  }

  function handleRemoveRule(id: string) {
    setActivePresetId(null);
    setRules(prev => prev.filter(r => r.id !== id));
  }

  function handleToggleSort(column: string) {
    if (sortBy === column) {
      setSortDir(prev => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(column);
      setSortDir(column === "symbol" || column === "name" || column === "rsi_14" || column === "pe_ttm" ? "asc" : "desc");
    }
  }

  async function handleRebuildLocal() {
    setHydrating(true);
    setBanner(null);
    setError(null);
    try {
      const res = await rebuildFinanceScreener();
      setCoverage(res.coverage);
      setBanner(`Index local reconstruit : ${res.indexed_count} valeur(s) analysée(s) depuis l'entrepôt SQLite (0 appel réseau).`);
      await runQuery();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Échec de reconstruction locale.");
    } finally {
      setHydrating(false);
    }
  }

  async function handleHydrateUniverse(includeFundamentals: boolean) {
    setHydrating(true);
    setBanner(null);
    setError(null);
    try {
      const targetType = universeType === "all" && indices.length > 0 ? "all" : universeType;
      const res = await hydrateFinanceScreener({
        universe_type: targetType,
        universe_value: targetType === "all" ? null : universeValue || null,
        include_fundamentals: includeFundamentals,
        max_fundamentals: 40,
        refresh_eod: false,
      });
      setCoverage(res.coverage);
      setBanner(
        includeFundamentals
          ? `Synchronisation terminée : ${res.indexed_count} titres indexés, ${res.fundamentals_enriched} dossiers fondamentaux enrichis (${res.fundamentals_cached} déjà en cache).`
          : `Cours & indicateurs techniques actualisés pour ${res.indexed_count} titre(s).`,
      );
      await runQuery();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'enrichissement de l'univers.");
    } finally {
      setHydrating(false);
    }
  }

  async function handleExportWatchlist() {
    if (items.length === 0 || exporting) return;
    setExporting(true);
    setBanner(null);
    setError(null);
    try {
      const activePreset = presets.find(p => p.id === activePresetId);
      const listName = activePreset
        ? `Screener · ${activePreset.name}`
        : `Screener (${new Date().toLocaleDateString("fr-FR")})`;
      const res = await exportScreenerToWatchlist({
        list_name: listName,
        items: items.slice(0, 80).map(it => ({
          symbol: it.symbol,
          eod_ticker: it.eod_ticker,
          yahoo_symbol: it.yahoo_symbol,
          name: it.name,
          exchange: it.exchange,
          currency: it.currency,
        })),
      });
      setBanner(
        res.added_count > 0
          ? `${res.added_count} titre(s) ajouté(s) à la liste « ${res.list.name} » — ouvrez un titre en plein écran pour les parcourir avec ← / →.`
          : `Ces titres sont déjà présents dans la liste « ${res.list.name} ».`,
      );
      await onWatchlistExported(res.list.id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Impossible d'exporter vers une liste de suivi.");
    } finally {
      setExporting(false);
    }
  }

  function renderSortIcon(col: string) {
    if (sortBy !== col) return null;
    return sortDir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
  }

  return (
    <div className={styles.root}>
      {/* En-tête Univers & Couverture */}
      <div className={styles.topCard}>
        <div className={styles.topHeader}>
          <div className={styles.titleBlock}>
            <span className={styles.titleIcon}>
              <SlidersHorizontal size={17} />
            </span>
            <div>
              <h3>Screener Boursier · Fondamentaux &amp; Technique</h3>
              <p className={styles.subtitle}>
                Filtrage instantané sur l&apos;entrepôt SQLite local · architecture prête pour vos futures formules personnalisées
              </p>
            </div>
          </div>

          <div className={styles.coveragePills}>
            <span className={styles.coveragePill} title="Titres indexés dans la table matérialisée du Screener">
              <Database size={12} />
              <strong>{coverage?.total_snapshots ?? 0}</strong> indexés
            </span>
            <span className={styles.coveragePill} title="Titres disposant de suffisamment de séances EOD pour les indicateurs techniques">
              Technique : <strong>{coverage?.with_technicals ?? 0}</strong>
            </span>
            <span className={styles.coveragePill} title="Titres disposant de leurs ratios fondamentaux et scores en cache">
              Fondamentaux : <strong>{coverage?.with_fundamentals ?? 0}</strong>
            </span>
          </div>
        </div>

        {/* Contrôles d'univers */}
        <div className={styles.universeRow}>
          <div className={styles.controlGroup}>
            <label className={styles.label}>Univers</label>
            <select
              className={styles.select}
              value={universeType}
              onChange={e => {
                const next = e.target.value as "all" | "index" | "watchlist";
                setUniverseType(next);
                if (next === "index") {
                  setUniverseValue(indices[0]?.code || "CAC40");
                } else if (next === "watchlist") {
                  setUniverseValue(activeListId || watchlists[0]?.id || "");
                } else {
                  setUniverseValue("");
                }
              }}
            >
              <option value="all">Tout l&apos;entrepôt local</option>
              <option value="index">Par indice boursier</option>
              <option value="watchlist">Ma liste de suivi</option>
            </select>

            {universeType === "index" && (
              <select
                className={styles.select}
                value={universeValue}
                onChange={e => setUniverseValue(e.target.value)}
                aria-label="Choisir un indice"
              >
                {indices.map(idx => (
                  <option key={idx.code} value={idx.code}>
                    {idx.flag} {idx.name} ({idx.code})
                  </option>
                ))}
              </select>
            )}

            {universeType === "watchlist" && (
              <select
                className={styles.select}
                value={universeValue}
                onChange={e => setUniverseValue(e.target.value)}
                aria-label="Choisir une liste de suivi"
              >
                {watchlists.map(wl => (
                  <option key={wl.id} value={wl.id}>
                    {wl.name} ({wl.items_count})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className={styles.controlGroup}>
            <div className={styles.searchWrap}>
              <Search size={13} className={styles.searchIcon} />
              <input
                type="text"
                className={styles.searchInput}
                placeholder="Filtrer ticker ou nom..."
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
              />
            </div>

            {coverage && coverage.sectors.length > 0 && (
              <select
                className={styles.select}
                value={sectorFilter}
                onChange={e => setSectorFilter(e.target.value)}
                aria-label="Filtrer par secteur"
              >
                <option value="">Tous les secteurs</option>
                {coverage.sectors.map(sec => (
                  <option key={sec} value={sec}>
                    {sec}
                  </option>
                ))}
              </select>
            )}

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={onlyWithFundamentals}
                onChange={e => setOnlyWithFundamentals(e.target.checked)}
              />
              <span>Fondamentaux seuls</span>
            </label>
          </div>

          <div className={styles.syncActions}>
            <button
              type="button"
              className={styles.secondaryBtn}
              onClick={() => void handleRebuildLocal()}
              disabled={hydrating}
              title="Recalcule tous les indicateurs techniques et fondamentaux depuis le cache SQLite (0 appel API)"
            >
              {hydrating ? <LoaderCircle size={13} className="spin" /> : <RefreshCw size={13} />}
              <span>Indexer cache</span>
            </button>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={() => void handleHydrateUniverse(true)}
              disabled={hydrating}
              title="Télécharge les cours EOD manquants et enrichit jusqu'à 40 dossiers fondamentaux de l'univers choisi (TTL 15j)"
            >
              {hydrating ? <LoaderCircle size={13} className="spin" /> : <Download size={13} />}
              <span>Enrichir univers</span>
            </button>
          </div>
        </div>

        {/* Presets en 1 clic */}
        {presets.length > 0 && (
          <div className={styles.presetsRow}>
            <span className={styles.presetsLabel}>
              <Sparkles size={12} /> Presets :
            </span>
            {presets.map(p => (
              <button
                key={p.id}
                type="button"
                className={`${styles.presetChip} ${activePresetId === p.id ? styles.presetChipActive : ""}`}
                onClick={() => handleApplyPreset(p)}
                title={p.description}
              >
                {p.name}
              </button>
            ))}
            {(rules.length > 0 || searchText || sectorFilter || onlyWithFundamentals) && (
              <button
                type="button"
                className={styles.resetChip}
                onClick={handleResetFilters}
              >
                <RotateCcw size={11} /> Réinitialiser
              </button>
            )}
          </div>
        )}
      </div>

      {/* Constructeur de règles */}
      <div className={styles.rulesCard}>
        <div className={styles.rulesHeader}>
          <div className={styles.rulesTitle}>
            <Filter size={14} />
            <strong>Critères de sélection ({apiRules.length} actif{apiRules.length > 1 ? "s" : ""})</strong>
          </div>
          <div className={styles.rulesButtons}>
            <button type="button" className={styles.addRuleBtn} onClick={handleAddMetricRule}>
              <Plus size={13} /> Critère (Fondamental / Technique)
            </button>
            <button type="button" className={styles.addRuleBtn} onClick={handleAddCompareRule}>
              <Plus size={13} /> Comparer cours / MM
            </button>
          </div>
        </div>

        {rules.length === 0 ? (
          <p className={styles.emptyRulesHint}>
            Aucun filtre actif : toutes les valeurs de l&apos;univers s&apos;affichent. Choisissez un preset ci-dessus ou ajoutez un critère (ex. <code>ROIC ≥ 12 %</code>, <code>Cours &gt; SMA 200</code>, <code>RSI (14) ≤ 35</code>).
          </p>
        ) : (
          <div className={styles.rulesList}>
            {rules.map(r => {
              if (r.kind === "compare") {
                return (
                  <div key={r.id} className={styles.ruleRow}>
                    <span className={styles.ruleKindBadge}>Comparaison</span>
                    <select
                      className={styles.select}
                      value={r.left}
                      onChange={e => handleUpdateRule(r.id, { left: e.target.value })}
                    >
                      {comparableFields.map(f => (
                        <option key={f.key} value={f.key}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                    <select
                      className={styles.opSelect}
                      value={r.op}
                      onChange={e => handleUpdateRule(r.id, { op: e.target.value })}
                    >
                      {COMPARE_OPS.map(o => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                    <select
                      className={styles.select}
                      value={r.right}
                      onChange={e => handleUpdateRule(r.id, { right: e.target.value })}
                    >
                      {comparableFields.map(f => (
                        <option key={f.key} value={f.key}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className={styles.deleteRuleBtn}
                      onClick={() => handleRemoveRule(r.id)}
                      aria-label="Supprimer cette règle"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                );
              }

              const meta = fieldsByKey.get(r.field);
              const isSignal = r.kind === "signal" || meta?.type === "signal";

              return (
                <div key={r.id} className={styles.ruleRow}>
                  <span className={styles.ruleKindBadge}>{isSignal ? "Signal" : "Critère"}</span>
                  <select
                    className={styles.select}
                    value={r.field}
                    onChange={e => handleUpdateRule(r.id, { field: e.target.value })}
                  >
                    {fieldsGrouped.map(grp => (
                      <optgroup key={grp.category} label={grp.label}>
                        {grp.items.map(f => (
                          <option key={f.key} value={f.key}>
                            {f.label}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>

                  {isSignal ? (
                    <select
                      className={styles.select}
                      value={r.value}
                      onChange={e => handleUpdateRule(r.id, { value: e.target.value })}
                    >
                      {(meta?.options || []).map(opt => (
                        <option key={opt.value} value={String(opt.value)}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <>
                      <select
                        className={styles.opSelect}
                        value={r.op}
                        onChange={e => handleUpdateRule(r.id, { op: e.target.value })}
                      >
                        {METRIC_OPS.map(o => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                      <input
                        type="number"
                        step="any"
                        className={styles.numInput}
                        placeholder="Valeur"
                        value={r.value}
                        onChange={e => handleUpdateRule(r.id, { value: e.target.value })}
                      />
                      {r.op === "between" && (
                        <>
                          <span className={styles.muted}>et</span>
                          <input
                            type="number"
                            step="any"
                            className={styles.numInput}
                            placeholder="Max"
                            value={r.valueMax}
                            onChange={e => handleUpdateRule(r.id, { valueMax: e.target.value })}
                          />
                        </>
                      )}
                    </>
                  )}

                  {meta?.description && (
                    <span className={styles.ruleHint} title={meta.description}>
                      {meta.description}
                    </span>
                  )}

                  <button
                    type="button"
                    className={styles.deleteRuleBtn}
                    onClick={() => handleRemoveRule(r.id)}
                    aria-label="Supprimer cette règle"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {banner && <div className={styles.bannerInfo}>{banner}</div>}
      {error && (
        <div className={styles.bannerError} role="alert">
          ⚠️ {error}
        </div>
      )}

      {/* Barre de résultats & groupes de colonnes */}
      <div className={styles.resultsCard}>
        <div className={styles.resultsToolbar}>
          <div className={styles.resultsCount}>
            {loading && <LoaderCircle size={14} className="spin" />}
            <strong>{total}</strong> résultat{total > 1 ? "s" : ""}
            <span className={styles.muted}>sur {universeTotal} titre{universeTotal > 1 ? "s" : ""}</span>
          </div>

          <div className={styles.colGroupTabs} role="tablist" aria-label="Vue des colonnes">
            {(
              [
                ["overview", "Synthèse"],
                ["valuation", "Valorisation"],
                ["quality", "Qualité & Scores"],
                ["technical", "Technique"],
              ] as const
            ).map(([gid, label]) => (
              <button
                key={gid}
                type="button"
                role="tab"
                aria-selected={columnGroup === gid}
                className={`${styles.colGroupBtn} ${columnGroup === gid ? styles.colGroupBtnActive : ""}`}
                onClick={() => setColumnGroup(gid)}
              >
                {label}
              </button>
            ))}
          </div>

          <button
            type="button"
            className={styles.exportBtn}
            disabled={items.length === 0 || exporting}
            onClick={() => void handleExportWatchlist()}
            title="Enregistre ces résultats dans une liste de suivi pour les parcourir en plein écran"
          >
            {exporting ? <LoaderCircle size={13} className="spin" /> : <Plus size={13} />}
            <span>Envoyer en Watchlist ({Math.min(items.length, 80)})</span>
          </button>
        </div>

        <div className={styles.tableWrap}>
          {items.length === 0 ? (
            <div className={styles.emptyTable}>
              {coverage && coverage.total_snapshots === 0 ? (
                <>
                  <p>Aucune valeur n&apos;est encore indexée dans le Screener.</p>
                  <p className={styles.muted}>
                    Choisissez un indice ci-dessus (ex. CAC 40) puis cliquez sur <strong>« Enrichir univers »</strong>, ou cliquez sur <strong>« Indexer cache »</strong> si vous avez déjà consulté des valeurs.
                  </p>
                </>
              ) : (
                <p>Aucune valeur ne correspond à l&apos;ensemble de vos critères actifs.</p>
              )}
            </div>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th onClick={() => handleToggleSort("symbol")}>
                    Titre {renderSortIcon("symbol")}
                  </th>
                  <th className={styles.numCol} onClick={() => handleToggleSort("price")}>
                    Cours {renderSortIcon("price")}
                  </th>
                  <th className={styles.numCol} onClick={() => handleToggleSort("change_1d_pct")}>
                    1J {renderSortIcon("change_1d_pct")}
                  </th>
                  <th className={styles.numCol} onClick={() => handleToggleSort("change_1y_pct")}>
                    1A {renderSortIcon("change_1y_pct")}
                  </th>
                  <th>Tendance</th>

                  {columnGroup === "overview" && (
                    <>
                      <th className={styles.numCol} onClick={() => handleToggleSort("market_cap")}>
                        Cap. {renderSortIcon("market_cap")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("pe_ttm")}>
                        PER {renderSortIcon("pe_ttm")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("roic_pct")}>
                        ROIC {renderSortIcon("roic_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("ih_score")}>
                        IH /9 {renderSortIcon("ih_score")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("rsi_14")}>
                        RSI 14 {renderSortIcon("rsi_14")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("dist_sma200_pct")}>
                        vs SMA200 {renderSortIcon("dist_sma200_pct")}
                      </th>
                      <th>Supertrend</th>
                    </>
                  )}

                  {columnGroup === "valuation" && (
                    <>
                      <th className={styles.numCol} onClick={() => handleToggleSort("market_cap")}>
                        Cap. {renderSortIcon("market_cap")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("pe_ttm")}>
                        PER TTM {renderSortIcon("pe_ttm")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("pe_forward")}>
                        PER Fwd {renderSortIcon("pe_forward")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("peg_ratio")}>
                        PEG {renderSortIcon("peg_ratio")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("ev_ebitda")}>
                        VE/EBITDA {renderSortIcon("ev_ebitda")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("fcf_yield_pct")}>
                        FCF Yield {renderSortIcon("fcf_yield_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("dividend_yield_pct")}>
                        Div. {renderSortIcon("dividend_yield_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("mos_intrinsic_pct")}>
                        MoS % {renderSortIcon("mos_intrinsic_pct")}
                      </th>
                    </>
                  )}

                  {columnGroup === "quality" && (
                    <>
                      <th className={styles.numCol} onClick={() => handleToggleSort("roic_pct")}>
                        ROIC {renderSortIcon("roic_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("roe_pct")}>
                        ROE {renderSortIcon("roe_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("op_margin_pct")}>
                        Marge Op. {renderSortIcon("op_margin_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("net_debt_ebitda")}>
                        DN/EBITDA {renderSortIcon("net_debt_ebitda")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("rev_cagr_3y_pct")}>
                        CA 3A {renderSortIcon("rev_cagr_3y_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("ih_score")}>
                        IH /9 {renderSortIcon("ih_score")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("piotroski_f")}>
                        Piotroski {renderSortIcon("piotroski_f")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("altman_z")}>
                        Altman Z {renderSortIcon("altman_z")}
                      </th>
                    </>
                  )}

                  {columnGroup === "technical" && (
                    <>
                      <th className={styles.numCol} onClick={() => handleToggleSort("rsi_14")}>
                        RSI 14 {renderSortIcon("rsi_14")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("dist_sma50_pct")}>
                        vs SMA50 {renderSortIcon("dist_sma50_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("dist_sma200_pct")}>
                        vs SMA200 {renderSortIcon("dist_sma200_pct")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("macd_hist")}>
                        MACD Hist {renderSortIcon("macd_hist")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("adx_14")}>
                        ADX 14 {renderSortIcon("adx_14")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("boll_pct_b")}>
                        Boll %B {renderSortIcon("boll_pct_b")}
                      </th>
                      <th className={styles.numCol} onClick={() => handleToggleSort("rel_volume_20d")}>
                        Vol. rel. {renderSortIcon("rel_volume_20d")}
                      </th>
                      <th>Supertrend</th>
                    </>
                  )}

                  <th className={styles.actionCol}>Graph.</th>
                </tr>
              </thead>
              <tbody>
                {items.map(row => {
                  const target = row.eod_ticker || row.yahoo_symbol || row.symbol;
                  return (
                    <tr
                      key={row.symbol}
                      className={styles.dataRow}
                      onClick={() => void onOpenStock(target, row.name || row.symbol, "fundamentals")}
                    >
                      <td>
                        <div className={styles.stockCell}>
                          <span className={styles.symbolBadge}>{row.symbol}</span>
                          <div className={styles.stockMeta}>
                            <strong className={styles.stockName}>{row.name || row.symbol}</strong>
                            <small className={styles.stockSub}>
                              {row.sector || row.exchange || "—"}
                              {row.indices.length > 0 ? ` · ${row.indices.slice(0, 2).join(", ")}` : ""}
                            </small>
                          </div>
                        </div>
                      </td>
                      <td className={styles.numCol}>
                        {row.price != null ? (
                          <strong>
                            {row.price.toFixed(2)} <span className={styles.curr}>{row.currency}</span>
                          </strong>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className={`${styles.numCol} ${(row.change_1d_pct ?? 0) >= 0 ? styles.pos : styles.neg}`}>
                        {fmtSignedPct(row.change_1d_pct, 2)}
                      </td>
                      <td className={`${styles.numCol} ${(row.change_1y_pct ?? 0) >= 0 ? styles.pos : styles.neg}`}>
                        {fmtSignedPct(row.change_1y_pct, 1)}
                      </td>
                      <td>
                        <MiniSparkline points={row.sparkline} />
                      </td>

                      {columnGroup === "overview" && (
                        <>
                          <td className={styles.numCol}>{fmtMcap(row.market_cap)}</td>
                          <td className={styles.numCol}>{fmtNum(row.pe_ttm, 1, "×")}</td>
                          <td className={styles.numCol}>{fmtNum(row.roic_pct, 1, "%")}</td>
                          <td className={styles.numCol}>
                            {row.ih_score != null ? (
                              <span className={row.ih_score >= 6 ? styles.badgePos : styles.badgeNeutral}>
                                {row.ih_score.toFixed(0)}/9
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className={styles.numCol}>
                            {row.rsi_14 != null ? (
                              <span
                                className={
                                  row.rsi_14 <= 35
                                    ? styles.badgePos
                                    : row.rsi_14 >= 70
                                      ? styles.badgeNeg
                                      : styles.badgeNeutral
                                }
                              >
                                {row.rsi_14.toFixed(1)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className={`${styles.numCol} ${(row.dist_sma200_pct ?? 0) >= 0 ? styles.pos : styles.neg}`}>
                            {fmtSignedPct(row.dist_sma200_pct, 1)}
                          </td>
                          <td>
                            {row.supertrend_dir === 1 ? (
                              <span className={styles.badgePos}>Haussier</span>
                            ) : row.supertrend_dir === -1 ? (
                              <span className={styles.badgeNeg}>Baissier</span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </>
                      )}

                      {columnGroup === "valuation" && (
                        <>
                          <td className={styles.numCol}>{fmtMcap(row.market_cap)}</td>
                          <td className={styles.numCol}>{fmtNum(row.pe_ttm, 1, "×")}</td>
                          <td className={styles.numCol}>{fmtNum(row.pe_forward, 1, "×")}</td>
                          <td className={styles.numCol}>{fmtNum(row.peg_ratio, 2)}</td>
                          <td className={styles.numCol}>{fmtNum(row.ev_ebitda, 1, "×")}</td>
                          <td className={styles.numCol}>{fmtNum(row.fcf_yield_pct, 1, "%")}</td>
                          <td className={styles.numCol}>{fmtNum(row.dividend_yield_pct, 2, "%")}</td>
                          <td className={`${styles.numCol} ${(row.mos_intrinsic_pct ?? 0) >= 15 ? styles.pos : ""}`}>
                            {fmtSignedPct(row.mos_intrinsic_pct, 1)}
                          </td>
                        </>
                      )}

                      {columnGroup === "quality" && (
                        <>
                          <td className={styles.numCol}>{fmtNum(row.roic_pct, 1, "%")}</td>
                          <td className={styles.numCol}>{fmtNum(row.roe_pct, 1, "%")}</td>
                          <td className={styles.numCol}>{fmtNum(row.op_margin_pct, 1, "%")}</td>
                          <td className={styles.numCol}>{fmtNum(row.net_debt_ebitda, 2, "×")}</td>
                          <td className={styles.numCol}>{fmtSignedPct(row.rev_cagr_3y_pct, 1)}</td>
                          <td className={styles.numCol}>{row.ih_score != null ? `${row.ih_score.toFixed(0)}/9` : "—"}</td>
                          <td className={styles.numCol}>{row.piotroski_f != null ? `${row.piotroski_f.toFixed(0)}/9` : "—"}</td>
                          <td className={styles.numCol}>{fmtNum(row.altman_z, 2)}</td>
                        </>
                      )}

                      {columnGroup === "technical" && (
                        <>
                          <td className={styles.numCol}>{fmtNum(row.rsi_14, 1)}</td>
                          <td className={`${styles.numCol} ${(row.dist_sma50_pct ?? 0) >= 0 ? styles.pos : styles.neg}`}>
                            {fmtSignedPct(row.dist_sma50_pct, 1)}
                          </td>
                          <td className={`${styles.numCol} ${(row.dist_sma200_pct ?? 0) >= 0 ? styles.pos : styles.neg}`}>
                            {fmtSignedPct(row.dist_sma200_pct, 1)}
                          </td>
                          <td className={`${styles.numCol} ${(row.macd_hist ?? 0) >= 0 ? styles.pos : styles.neg}`}>
                            {fmtNum(row.macd_hist, 3)}
                          </td>
                          <td className={styles.numCol}>{fmtNum(row.adx_14, 1)}</td>
                          <td className={styles.numCol}>{fmtNum(row.boll_pct_b, 0, "%")}</td>
                          <td className={styles.numCol}>{fmtNum(row.rel_volume_20d, 2, "×")}</td>
                          <td>
                            {row.supertrend_dir === 1 ? (
                              <span className={styles.badgePos}>Haussier</span>
                            ) : row.supertrend_dir === -1 ? (
                              <span className={styles.badgeNeg}>Baissier</span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </>
                      )}

                      <td className={styles.actionCol} onClick={e => e.stopPropagation()}>
                        <button
                          type="button"
                          className={styles.chartIconBtn}
                          onClick={() => void onOpenStock(target, row.name || row.symbol, "chart_tech")}
                          title="Ouvrir directement sur le graphique technique"
                          aria-label={`Ouvrir le graphique de ${row.name || row.symbol}`}
                        >
                          <LineChart size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
