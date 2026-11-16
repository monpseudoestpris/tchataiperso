"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, LineChart, LoaderCircle, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";

import type { WatchlistItem } from "@/lib/api";

type SortKey = "name" | "price" | "change_1d_pct" | "change_1w_pct" | "change_1m_pct" | "change_3m_pct" | "change_1y_pct";

type FinanceWatchlistTableProps = {
  items: WatchlistItem[];
  loading: boolean;
  selectedSymbol?: string | null;
  onSelectStock: (item: WatchlistItem) => void;
  onAddStock: (query: string) => Promise<void>;
  onRemoveStock: (id: string) => Promise<void>;
  onRefresh: () => void;
  onSeedDefaults: () => Promise<void>;
};

function ReturnCell({ value }: { value: number | null }) {
  if (value == null || !Number.isFinite(value)) {
    return <span className="finance-perf-na">—</span>;
  }
  const cls = value > 0 ? "is-up" : value < 0 ? "is-down" : "is-flat";
  return (
    <span className={`finance-perf-pill ${cls}`}>
      {value > 0 ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
}

export function FinanceWatchlistTable({
  items,
  loading,
  selectedSymbol,
  onSelectStock,
  onAddStock,
  onRemoveStock,
  onRefresh,
  onSeedDefaults,
}: FinanceWatchlistTableProps) {
  const [newQuery, setNewQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sortedItems = useMemo(() => {
    if (!sortKey) return items;
    return [...items].sort((a, b) => {
      if (sortKey === "name") {
        const cmp = a.name.localeCompare(b.name, "fr");
        return sortDir === "asc" ? cmp : -cmp;
      }
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return sortDir === "asc" ? va - vb : vb - va;
    });
  }, [items, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      if (sortDir === "desc") {
        setSortDir("asc");
      } else {
        setSortKey(null);
      }
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  }

  async function handleAddSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = newQuery.trim();
    if (!q || adding) return;
    setAdding(true);
    setAddError(null);
    try {
      await onAddStock(q);
      setNewQuery("");
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Impossible d'ajouter cette action.");
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    setRemovingId(id);
    try {
      await onRemoveStock(id);
    } finally {
      setRemovingId(null);
    }
  }

  function renderSortIcon(key: SortKey) {
    if (sortKey !== key) return null;
    return sortDir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />;
  }

  return (
    <section className="finance-watchlist-section" aria-label="Tableau de suivi des actions">
      <div className="finance-watchlist-header">
        <div className="finance-watchlist-title">
          <span className="chart-icon-wrap">
            <LineChart size={15} />
          </span>
          <div>
            <strong>Mon suivi d&apos;actions ({items.length})</strong>
            <small>Cliquez sur une ligne pour ouvrir la courbe du cours et les indicateurs</small>
          </div>
        </div>

        <div className="finance-watchlist-controls">
          <form className="finance-watchlist-add-form" onSubmit={handleAddSubmit}>
            <input
              type="text"
              value={newQuery}
              onChange={e => setNewQuery(e.target.value)}
              placeholder="Ajouter une action (ex. Hermes, SAN.PA, TSLA)..."
              disabled={adding}
            />
            <button type="submit" disabled={adding || !newQuery.trim()}>
              {adding ? <LoaderCircle size={13} className="spin" /> : <Plus size={13} />}
              <span>Suivre</span>
            </button>
          </form>

          <button
            type="button"
            className="finance-watchlist-refresh-btn"
            onClick={onRefresh}
            disabled={loading}
            title="Actualiser les cours et évolutions"
          >
            <RefreshCw size={13} className={loading ? "spin" : ""} />
            <span>Actualiser</span>
          </button>
        </div>
      </div>

      {addError && <div className="finance-watchlist-error">⚠️ {addError}</div>}

      <div className="finance-table-wrapper finance-watchlist-table-wrap">
        <table className="finance-data-table finance-watchlist-table">
          <thead>
            <tr>
              <th>
                <button type="button" className="finance-sort-btn" onClick={() => toggleSort("name")}>
                  Action {renderSortIcon("name")}
                </button>
              </th>
              <th className="is-num">
                <button type="button" className="finance-sort-btn" onClick={() => toggleSort("price")}>
                  Cours {renderSortIcon("price")}
                </button>
              </th>
              <th className="is-num">
                <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1d_pct")}>
                  Jour {renderSortIcon("change_1d_pct")}
                </button>
              </th>
              <th className="is-num">
                <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1w_pct")}>
                  Semaine {renderSortIcon("change_1w_pct")}
                </button>
              </th>
              <th className="is-num">
                <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1m_pct")}>
                  Mois {renderSortIcon("change_1m_pct")}
                </button>
              </th>
              <th className="is-num">
                <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_3m_pct")}>
                  3 Mois {renderSortIcon("change_3m_pct")}
                </button>
              </th>
              <th className="is-num">
                <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1y_pct")}>
                  Année {renderSortIcon("change_1y_pct")}
                </button>
              </th>
              <th className="is-actions"></th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 ? (
              <tr>
                <td colSpan={8} className="finance-watchlist-empty-cell">
                  <LoaderCircle size={16} className="spin" /> Chargement de votre liste de suivi…
                </td>
              </tr>
            ) : sortedItems.length === 0 ? (
              <tr>
                <td colSpan={8} className="finance-watchlist-empty-cell">
                  <span>Aucune action dans votre suivi. Ajoutez un ticker ci-dessus ou </span>
                  <button type="button" className="finance-inline-link-btn" onClick={() => void onSeedDefaults()}>
                    <Sparkles size={12} /> charger la sélection type (CAC 40 & Tech)
                  </button>
                </td>
              </tr>
            ) : (
              sortedItems.map(item => {
                const isSelected =
                  !!selectedSymbol &&
                  (selectedSymbol.toUpperCase() === item.symbol.toUpperCase() ||
                    selectedSymbol.toUpperCase() === item.yahoo_symbol.toUpperCase());
                return (
                  <tr
                    key={item.id}
                    className={`finance-watchlist-row ${isSelected ? "is-selected" : ""}`}
                    onClick={() => onSelectStock(item)}
                    title={`Cliquer pour ouvrir la courbe et les indicateurs de ${item.name}`}
                  >
                    <td>
                      <div className="finance-wl-identity">
                        <strong>{item.name}</strong>
                        <div className="finance-wl-meta">
                          <span className="finance-symbol-tag">{item.symbol}</span>
                          {item.exchange && <span className="finance-wl-exch">{item.exchange}</span>}
                        </div>
                      </div>
                    </td>
                    <td className="is-num">
                      {item.price != null ? (
                        <strong className="finance-wl-price">
                          {item.price.toFixed(2)} <small>{item.currency}</small>
                        </strong>
                      ) : (
                        <span className="finance-perf-na">—</span>
                      )}
                    </td>
                    <td className="is-num">
                      <ReturnCell value={item.change_1d_pct} />
                    </td>
                    <td className="is-num">
                      <ReturnCell value={item.change_1w_pct} />
                    </td>
                    <td className="is-num">
                      <ReturnCell value={item.change_1m_pct} />
                    </td>
                    <td className="is-num">
                      <ReturnCell value={item.change_3m_pct} />
                    </td>
                    <td className="is-num">
                      <ReturnCell value={item.change_1y_pct} />
                    </td>
                    <td className="is-actions">
                      <button
                        type="button"
                        className="finance-wl-remove-btn"
                        onClick={e => void handleRemove(e, item.id)}
                        disabled={removingId === item.id}
                        title={`Retirer ${item.name} du suivi`}
                        aria-label={`Retirer ${item.name}`}
                      >
                        {removingId === item.id ? <LoaderCircle size={13} className="spin" /> : <Trash2 size={13} />}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
