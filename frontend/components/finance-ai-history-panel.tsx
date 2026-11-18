"use client";

import { ArrowUpRight, History, RefreshCw, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  deleteFinanceAiHistoryItem,
  fetchFinanceAiHistory,
  type FinanceAiAnalysisKind,
  type FinanceAiAnalysisRecord,
} from "@/lib/api";

type FinanceAiHistoryPanelProps = {
  symbol: string;
  onSelectSymbol?: (symbol: string) => void;
  onInsertIntoChat?: (text: string) => void;
};

const KIND_LABELS: Record<FinanceAiAnalysisKind, string> = {
  expert: "Expert IA",
  dossier: "Dossier IA",
  moat: "MOAT",
  news: "Actus IA",
  report: "Rapport",
};

const KIND_ACCENTS: Record<FinanceAiAnalysisKind, string> = {
  expert: "#10b981",
  dossier: "#4f46e5",
  moat: "#0ea5e9",
  news: "#f59e0b",
  report: "#8b5cf6",
};

function fmtFullDate(iso?: string | null): string {
  if (!iso) return "Date inconnue";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso.slice(0, 16);
  return dt.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

/** Onglet « Archives IA » : historique daté complet des analyses IA (Experts, Dossier, MOAT, Actus, Rapports). */
export function FinanceAiHistoryPanel({
  symbol,
  onSelectSymbol,
  onInsertIntoChat,
}: FinanceAiHistoryPanelProps) {
  const [scope, setScope] = useState<"all" | "current">("all");
  const [kindFilter, setKindFilter] = useState<FinanceAiAnalysisKind | "all">("all");
  const [searchText, setSearchText] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const requestKey = `${scope}:${kindFilter}:${scope === "current" ? symbol : "*"}:${reloadNonce}`;
  const [archiveState, setArchiveState] = useState<{
    key: string;
    items: FinanceAiAnalysisRecord[];
    error: string | null;
  }>({ key: "", items: [], error: null });
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFinanceAiHistory({
      symbol: scope === "current" ? symbol : null,
      kind: kindFilter === "all" ? null : kindFilter,
      limit: 150,
    })
      .then(res => {
        if (cancelled) return;
        const list = res.items || [];
        setArchiveState({ key: requestKey, items: list, error: null });
        setSelectedId(prev => (prev && list.some(it => it.id === prev) ? prev : list[0]?.id ?? null));
      })
      .catch(err => {
        if (!cancelled) {
          setArchiveState(prev => ({
            ...prev,
            key: requestKey,
            error: err instanceof Error ? err.message : "Impossible de charger les archives IA.",
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [requestKey, scope, kindFilter, symbol]);

  const loading = archiveState.key !== requestKey;
  const items = archiveState.items;
  const error = actionError || (archiveState.key === requestKey ? archiveState.error : null);

  const filteredItems = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return items;
    return items.filter(it => {
      const hay = `${it.symbol || ""} ${it.company_name || ""} ${it.expert_name || ""} ${it.verdict || ""} ${it.model || ""} ${it.question || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [items, searchText]);

  const activeItem =
    filteredItems.find(it => it.id === selectedId) ?? filteredItems[0] ?? null;

  async function handleDelete(item: FinanceAiAnalysisRecord) {
    if (!item.id) return;
    setActionError(null);
    try {
      await deleteFinanceAiHistoryItem(item.id);
      setArchiveState(prev => ({ ...prev, items: prev.items.filter(x => x.id !== item.id) }));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  return (
    <div className="finance-ai-archive-wrap">
      <div className="finance-ai-archive-toolbar">
        <div className="finance-ai-archive-title">
          <History size={16} />
          <div>
            <h3>Archives datées des analyses IA</h3>
            <p>Retrouvez à tout moment vos consultations d&apos;experts, synthèses complètes, MOAT et veilles sauvegardés.</p>
          </div>
        </div>

        <div className="finance-ai-archive-controls">
          <div className="finance-timeframe-selector" role="group" aria-label="Périmètre">
            <button
              type="button"
              className={`finance-tf-btn ${scope === "all" ? "active" : ""}`}
              onClick={() => setScope("all")}
            >
              Toutes les actions
            </button>
            <button
              type="button"
              className={`finance-tf-btn ${scope === "current" ? "active" : ""}`}
              onClick={() => setScope("current")}
            >
              {symbol} uniquement
            </button>
          </div>

          <button
            type="button"
            className="finance-tf-btn"
            onClick={() => setReloadNonce(n => n + 1)}
            title="Actualiser l'archive"
          >
            <RefreshCw size={12} className={loading ? "spin" : ""} />
            <span>Actualiser</span>
          </button>
        </div>
      </div>

      <div className="finance-ai-archive-filters">
        <div className="finance-timeframe-selector" role="group" aria-label="Type d'analyse">
          {(["all", "expert", "dossier", "moat", "news", "report"] as const).map(k => (
            <button
              key={k}
              type="button"
              className={`finance-tf-btn ${kindFilter === k ? "active" : ""}`}
              onClick={() => setKindFilter(k)}
            >
              {k === "all" ? "Tout" : KIND_LABELS[k]}
            </button>
          ))}
        </div>

        <div className="finance-ai-archive-search">
          <Search size={13} />
          <input
            type="text"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            placeholder="Filtrer par action, expert, verdict, question…"
          />
        </div>
      </div>

      {error && <p className="text-rose">{error}</p>}

      {loading && items.length === 0 ? (
        <p className="finance-dossier-ai-placeholder">Chargement des archives IA…</p>
      ) : filteredItems.length === 0 ? (
        <div className="finance-expert-empty-state">
          Aucune analyse sauvegardée ne correspond à ce filtre pour le moment. Lancez un <strong>Avis d&apos;expert</strong> ou une <strong>Analyse IA</strong> pour l&apos;archiver ici automatiquement.
        </div>
      ) : (
        <div className="finance-ai-archive-layout">
          <aside className="finance-ai-archive-list" aria-label="Liste des analyses archivées">
            {filteredItems.map(item => {
              const kind = (item.kind || "dossier") as FinanceAiAnalysisKind;
              const isSelected = activeItem?.id === item.id;
              return (
                <div
                  key={item.id || `${item.symbol}-${item.created_at}`}
                  className={`finance-ai-archive-row ${isSelected ? "active" : ""}`}
                >
                  <button
                    type="button"
                    className="finance-ai-archive-row-btn"
                    onClick={() => setSelectedId(item.id || null)}
                  >
                    <div className="finance-ai-archive-row-top">
                      <span
                        className="finance-ai-archive-kind"
                        style={{ background: KIND_ACCENTS[kind] || "#4f46e5" }}
                      >
                        {KIND_LABELS[kind] || kind}
                      </span>
                      <strong className="finance-ai-archive-sym">{item.symbol}</strong>
                      <small className="finance-ai-archive-dt">{fmtFullDate(item.created_at)}</small>
                    </div>
                    <div className="finance-ai-archive-row-mid">
                      <span>{item.expert_name || item.company_name || item.symbol}</span>
                      {item.verdict && <span className="finance-ai-hist-verdict">{item.verdict}</span>}
                    </div>
                    {item.question && (
                      <div className="finance-ai-archive-row-q">« {item.question} »</div>
                    )}
                    {item.model && (
                      <div className="finance-ai-archive-row-model">{item.model}</div>
                    )}
                  </button>
                  {item.id && (
                    <button
                      type="button"
                      className="finance-ai-archive-row-del"
                      onClick={() => void handleDelete(item)}
                      title="Supprimer cette archive"
                      aria-label="Supprimer"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              );
            })}
          </aside>

          {activeItem && (
            <div className="finance-ai-archive-detail">
              {onSelectSymbol && activeItem.symbol && activeItem.symbol !== symbol && (
                <div className="finance-ai-archive-jump">
                  <span>
                    Action consultée : <strong>{activeItem.company_name || activeItem.symbol}</strong> ({activeItem.symbol})
                  </span>
                  <button
                    type="button"
                    className="finance-tf-btn active"
                    onClick={() => onSelectSymbol(activeItem.symbol!)}
                  >
                    <span>Ouvrir la fiche {activeItem.symbol}</span>
                    <ArrowUpRight size={12} />
                  </button>
                </div>
              )}

              <FinanceRichReport
                contentHtml={activeItem.content_html}
                markdown={activeItem.markdown}
                newsArticles={activeItem.news_articles}
                onInsertIntoChat={onInsertIntoChat}
                meta={{
                  title:
                    activeItem.expert_name
                      ? `${activeItem.expert_name} — ${activeItem.company_name || activeItem.symbol || ""}`
                      : `${KIND_LABELS[(activeItem.kind || "dossier") as FinanceAiAnalysisKind] || "Analyse IA"} — ${activeItem.company_name || activeItem.symbol || ""}`,
                  subtitle: activeItem.model || "",
                  symbol: activeItem.symbol,
                  model: activeItem.model,
                  createdAt: activeItem.created_at,
                  accent: KIND_ACCENTS[(activeItem.kind || "dossier") as FinanceAiAnalysisKind] || "#4f46e5",
                  badgeLabel: KIND_LABELS[(activeItem.kind || "dossier") as FinanceAiAnalysisKind] || "Analyse IA",
                  question: activeItem.question,
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
