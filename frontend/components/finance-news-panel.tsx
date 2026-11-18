"use client";

import { useEffect, useState } from "react";
import { ExternalLink, LoaderCircle, MessageSquarePlus, Newspaper, Search, Trash2 } from "lucide-react";

import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  deleteStockNews,
  fetchStockNews,
  searchStockNews,
  type StockNewsEntry,
} from "@/lib/api";

type FinanceNewsPanelProps = {
  symbol: string;
  companyName: string;
  onInsertIntoChat?: (text: string) => void;
};

export function FinanceNewsPanel({ symbol, companyName, onInsertIntoChat }: FinanceNewsPanelProps) {
  const [items, setItems] = useState<StockNewsEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [focusQuery, setFocusQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchStockNews(symbol)
      .then(list => {
        if (!cancelled) setItems(list);
      })
      .catch(err => {
        if (!cancelled) setError(err?.message || "Impossible de charger l'historique des actualités.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (searching) return;
    setSearching(true);
    setError(null);
    try {
      const created = await searchStockNews({
        symbol,
        company_name: companyName,
        focus_query: focusQuery.trim(),
      });
      setItems(prev => [created, ...prev]);
      setFocusQuery("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "La recherche d'actualités a échoué.");
    } finally {
      setSearching(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteStockNews(id);
      setItems(prev => prev.filter(item => item.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  return (
    <div className="finance-tab-content finance-news-panel">
      <form className="finance-panel-toolbar" onSubmit={handleSearch}>
        <div className="finance-panel-input-wrap">
          <Search size={14} className="finance-panel-input-icon" />
          <input
            type="text"
            value={focusQuery}
            onChange={e => setFocusQuery(e.target.value)}
            placeholder={`Mot-clé optionnel pour ${companyName || symbol} (ex. résultats, dividende, acquisition)...`}
            disabled={searching}
          />
        </div>
        <button type="submit" className="finance-insert-btn" disabled={searching}>
          {searching ? <LoaderCircle size={14} className="spin" /> : <Newspaper size={14} />}
          <span>{searching ? "Recherche & synthèse…" : "Rechercher les news"}</span>
        </button>
      </form>

      {error && <div className="finance-modal-error">⚠️ {error}</div>}

      {loading && items.length === 0 ? (
        <div className="finance-panel-empty">
          <LoaderCircle size={18} className="spin" /> Chargement des actualités stockées…
        </div>
      ) : items.length === 0 ? (
        <div className="finance-panel-empty">
          Aucune veille enregistrée pour <strong>{companyName || symbol}</strong>. Cliquez sur{" "}
          <strong>« Rechercher les news »</strong> pour collecter, résumer et archiver les dernières actualités.
        </div>
      ) : (
        <div className="finance-archive-list">
          {items.map(entry => (
            <article key={entry.id} className="finance-archive-card">
              <header className="finance-archive-card-head">
                <div>
                  <strong>
                    Veille {entry.company_name} ({entry.symbol})
                  </strong>
                  <div className="finance-archive-meta">
                    <span>{new Date(entry.created_at).toLocaleString("fr-FR")}</span>
                    {entry.search_query && <span className="finance-archive-tag">Filtre : {entry.search_query}</span>}
                    <span>{entry.articles.length} source(s)</span>
                  </div>
                </div>
                <div className="finance-archive-actions">
                  {onInsertIntoChat && (
                    <button
                      type="button"
                      className="finance-copy-btn"
                      onClick={() =>
                        onInsertIntoChat(
                          `Voici la synthèse récente des actualités pour **${entry.company_name} (${entry.symbol})** :\n\n${entry.summary_markdown}\n\nQuels impacts concrets anticipes-tu sur la valorisation et le cours ?`,
                        )
                      }
                      title="Analyser cette synthèse dans le chat"
                    >
                      <MessageSquarePlus size={13} />
                      <span>Discuter</span>
                    </button>
                  )}
                  <button
                    type="button"
                    className="finance-wl-remove-btn"
                    onClick={() => void handleDelete(entry.id)}
                    title="Supprimer cette veille"
                    aria-label="Supprimer cette veille"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </header>

              <FinanceRichReport
                markdown={entry.summary_markdown}
                meta={{
                  title: `Veille Actualités — ${entry.company_name || entry.symbol}`,
                  subtitle: entry.search_query || "Synthèse d'actualités boursières",
                  symbol: entry.symbol,
                  model: "Veille IA",
                  createdAt: entry.created_at,
                  accent: "#f59e0b",
                  badgeLabel: "Actualités IA",
                  question: entry.search_query || null,
                }}
              />

              {entry.articles.length > 0 && (
                <div className="finance-news-sources">
                  <span className="profile-label">Articles collectés</span>
                  <ul>
                    {entry.articles.map((art, i) => (
                      <li key={`${art.url}-${i}`}>
                        <a href={art.url} target="_blank" rel="noreferrer">
                          <span>{art.title}</span>
                          <ExternalLink size={11} />
                        </a>
                        <small>
                          {art.source}
                          {art.published_at ? ` · ${art.published_at}` : ""}
                        </small>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
