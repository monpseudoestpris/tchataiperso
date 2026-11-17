"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Check, FolderPlus, LineChart, LoaderCircle, Pencil, Plus, RefreshCw, Sparkles, Trash2, X } from "lucide-react";

import { FinanceHoverTip } from "@/components/finance-info-tip";
import type { FinanceWatchlistMeta, WatchlistItem } from "@/lib/api";

type SortKey = "name" | "price" | "change_1d_pct" | "change_1w_pct" | "change_1m_pct" | "change_3m_pct" | "change_1y_pct";

type FinanceWatchlistTableProps = {
  lists: FinanceWatchlistMeta[];
  activeListId: string | null;
  items: WatchlistItem[];
  loading: boolean;
  selectedSymbol?: string | null;
  onSelectList: (listId: string) => void;
  onCreateList: (name: string) => Promise<void>;
  onRenameList: (listId: string, name: string) => Promise<void>;
  onDeleteList: (listId: string) => Promise<void>;
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
  lists,
  activeListId,
  items,
  loading,
  selectedSymbol,
  onSelectList,
  onCreateList,
  onRenameList,
  onDeleteList,
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
  const [creatingList, setCreatingList] = useState(false);
  const [newListName, setNewListName] = useState("");
  const [renamingListId, setRenamingListId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [listBusy, setListBusy] = useState(false);

  const activeList = useMemo(
    () => lists.find(l => l.id === activeListId) || lists[0] || null,
    [lists, activeListId],
  );

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

  async function handleCreateListSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cleaned = newListName.trim();
    if (!cleaned || listBusy) return;
    setListBusy(true);
    setAddError(null);
    try {
      await onCreateList(cleaned);
      setNewListName("");
      setCreatingList(false);
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Impossible de créer la liste.");
    } finally {
      setListBusy(false);
    }
  }

  async function handleRenameSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cleaned = renameValue.trim();
    if (!cleaned || !renamingListId || listBusy) return;
    setListBusy(true);
    setAddError(null);
    try {
      await onRenameList(renamingListId, cleaned);
      setRenamingListId(null);
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Impossible de renommer la liste.");
    } finally {
      setListBusy(false);
    }
  }

  async function handleDeleteActiveList() {
    if (!activeList || lists.length <= 1 || listBusy) return;
    setListBusy(true);
    setAddError(null);
    try {
      await onDeleteList(activeList.id);
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Impossible de supprimer la liste.");
    } finally {
      setListBusy(false);
    }
  }

  return (
    <section className="finance-watchlist-section" aria-label="Tableau de suivi des actions">
      <div className="finance-watchlist-header">
        <div className="finance-watchlist-title">
          <span className="chart-icon-wrap">
            <LineChart size={15} />
          </span>
          <div>
            <strong>
              {activeList ? `${activeList.name} (${items.length})` : `Mon suivi d'actions (${items.length})`}
            </strong>
            <small>Cliquez sur une ligne pour ouvrir la courbe du cours et les indicateurs</small>
          </div>
        </div>

        <div className="finance-watchlist-controls">
          <form className="finance-watchlist-add-form" onSubmit={handleAddSubmit}>
            <input
              type="text"
              value={newQuery}
              onChange={e => setNewQuery(e.target.value)}
              placeholder={`Ajouter à « ${activeList?.name || "Suivi"} » (ex. SAN.PA, TSLA)...`}
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

      {/* Barre des listes personnalisées */}
      <div className="finance-wl-lists-bar">
        <div className="finance-wl-lists-tabs" role="tablist" aria-label="Listes d'actions personnalisées">
          {lists.map(wl => {
            const isActive = wl.id === (activeList?.id ?? activeListId);
            const count = isActive ? items.length : wl.items_count;
            if (renamingListId === wl.id) {
              return (
                <form key={wl.id} className="finance-wl-inline-form" onSubmit={handleRenameSubmit}>
                  <input
                    type="text"
                    value={renameValue}
                    onChange={e => setRenameValue(e.target.value)}
                    placeholder="Nom de la liste..."
                    maxLength={80}
                    autoFocus
                    disabled={listBusy}
                  />
                  <button type="submit" className="finance-wl-inline-ok" disabled={listBusy || !renameValue.trim()} title="Valider">
                    <Check size={12} />
                  </button>
                  <button type="button" className="finance-wl-inline-cancel" onClick={() => setRenamingListId(null)} title="Annuler">
                    <X size={12} />
                  </button>
                </form>
              );
            }
            return (
              <div key={wl.id} className={`finance-wl-tab-pill ${isActive ? "active" : ""}`}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className="finance-wl-tab-btn"
                  onClick={() => onSelectList(wl.id)}
                >
                  <span>{wl.name}</span>
                  <span className="finance-wl-tab-count">{count}</span>
                </button>
                {isActive && (
                  <div className="finance-wl-tab-actions">
                    <button
                      type="button"
                      className="finance-wl-tab-icon-btn"
                      onClick={() => {
                        setRenamingListId(wl.id);
                        setRenameValue(wl.name);
                      }}
                      title="Renommer cette liste"
                      aria-label={`Renommer ${wl.name}`}
                    >
                      <Pencil size={11} />
                    </button>
                    {lists.length > 1 && (
                      <button
                        type="button"
                        className="finance-wl-tab-icon-btn is-del"
                        onClick={() => void handleDeleteActiveList()}
                        disabled={listBusy}
                        title="Supprimer cette liste"
                        aria-label={`Supprimer ${wl.name}`}
                      >
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {creatingList ? (
            <form className="finance-wl-inline-form" onSubmit={handleCreateListSubmit}>
              <input
                type="text"
                value={newListName}
                onChange={e => setNewListName(e.target.value)}
                placeholder="Ex. Tech US, PEA Dividendes..."
                maxLength={80}
                autoFocus
                disabled={listBusy}
              />
              <button type="submit" className="finance-wl-inline-ok" disabled={listBusy || !newListName.trim()} title="Créer la liste">
                <Check size={12} />
              </button>
              <button type="button" className="finance-wl-inline-cancel" onClick={() => { setCreatingList(false); setNewListName(""); }} title="Annuler">
                <X size={12} />
              </button>
            </form>
          ) : (
            <button
              type="button"
              className="finance-wl-new-btn"
              onClick={() => {
                setCreatingList(true);
                setRenamingListId(null);
              }}
              title="Créer une nouvelle liste personnalisée"
            >
              <FolderPlus size={12} />
              <span>Nouvelle liste</span>
            </button>
          )}
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
                <FinanceHoverTip termKey="var_day" delayMs={200}>
                  <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1d_pct")}>
                    Jour {renderSortIcon("change_1d_pct")}
                  </button>
                </FinanceHoverTip>
              </th>
              <th className="is-num">
                <FinanceHoverTip termKey="perf_horizon" delayMs={200}>
                  <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1w_pct")}>
                    Semaine {renderSortIcon("change_1w_pct")}
                  </button>
                </FinanceHoverTip>
              </th>
              <th className="is-num">
                <FinanceHoverTip termKey="perf_horizon" delayMs={200}>
                  <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1m_pct")}>
                    Mois {renderSortIcon("change_1m_pct")}
                  </button>
                </FinanceHoverTip>
              </th>
              <th className="is-num">
                <FinanceHoverTip termKey="perf_horizon" delayMs={200}>
                  <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_3m_pct")}>
                    3 Mois {renderSortIcon("change_3m_pct")}
                  </button>
                </FinanceHoverTip>
              </th>
              <th className="is-num">
                <FinanceHoverTip termKey="perf_horizon" delayMs={200}>
                  <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1y_pct")}>
                    Année {renderSortIcon("change_1y_pct")}
                  </button>
                </FinanceHoverTip>
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
