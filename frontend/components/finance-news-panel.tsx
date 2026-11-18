"use client";

import { useEffect, useState } from "react";
import { ExternalLink, LoaderCircle, MessageSquarePlus, Newspaper, RefreshCw, Search, Trash2 } from "lucide-react";

import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  deleteStockNews,
  fetchStockNewsWithFeed,
  searchStockNews,
  type StockNewsEntry,
  type StockNewsFeed,
} from "@/lib/api";

type FinanceNewsPanelProps = {
  symbol: string;
  companyName: string;
  onInsertIntoChat?: (text: string) => void;
};

export function FinanceNewsPanel({ symbol, companyName, onInsertIntoChat }: FinanceNewsPanelProps) {
  const [state, setState] = useState<{
    symbol: string;
    items: StockNewsEntry[];
    feed: StockNewsFeed | null;
    error: string | null;
  }>({ symbol: "", items: [], feed: null, error: null });
  const [refreshingFeed, setRefreshingFeed] = useState(false);
  const [searching, setSearching] = useState(false);
  const [focusQuery, setFocusQuery] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchStockNewsWithFeed(symbol, false)
      .then(res => {
        if (!cancelled) {
          setActionError(null);
          setState({ symbol, items: res.items, feed: res.feed, error: null });
        }
      })
      .catch(err => {
        if (!cancelled) {
          setState({
            symbol,
            items: [],
            feed: null,
            error: err instanceof Error ? err.message : "Impossible de charger les actualités.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const loading = state.symbol !== symbol && !state.error;
  const items = state.symbol === symbol ? state.items : [];
  const feed = state.symbol === symbol ? state.feed : null;
  const error = actionError || (state.symbol === symbol ? state.error : null);

  async function handleRefreshFeed() {
    if (refreshingFeed) return;
    setRefreshingFeed(true);
    setActionError(null);
    try {
      const res = await fetchStockNewsWithFeed(symbol, true);
      setState({ symbol, items: res.items, feed: res.feed, error: null });
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Impossible d'actualiser les dépêches.");
    } finally {
      setRefreshingFeed(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (searching) return;
    setSearching(true);
    setActionError(null);
    try {
      const created = await searchStockNews({
        symbol,
        company_name: companyName,
        focus_query: focusQuery.trim(),
      });
      setState(prev => ({
        ...prev,
        symbol,
        items: [created, ...(prev.symbol === symbol ? prev.items : [])],
      }));
      setFocusQuery("");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "La recherche d'actualités a échoué.");
    } finally {
      setSearching(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteStockNews(id);
      setState(prev => ({
        ...prev,
        items: prev.items.filter(item => item.id !== id),
      }));
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  const feedItems = feed?.items || [];

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
          <span>{searching ? "Synthèse IA…" : "Nouvelle veille IA"}</span>
        </button>
      </form>

      {error && <div className="finance-modal-error">⚠️ {error}</div>}

      {/* 1. Fil d'actualités EODHD (ou Yahoo en repli) chargé directement */}
      <section className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>
            <Newspaper size={14} style={{ display: "inline", marginRight: 6, verticalAlign: "-2px" }} />
            Dépêches EODHD &amp; Sentiment ({feedItems.length})
          </h4>
          <div className="finance-timeframe-selector">
            {feed?.source && (
              <small className="finance-dossier-unit">
                Source : {feed.source}
                {feed.updated_at ? ` · ${new Date(feed.updated_at).toLocaleString("fr-FR")}` : ""}
              </small>
            )}
            <button
              type="button"
              className="finance-tf-btn finance-stmt-refresh-btn"
              disabled={refreshingFeed || loading}
              onClick={() => void handleRefreshFeed()}
              title="Recharger les dernières dépêches EODHD (/api/news)"
            >
              <RefreshCw size={12} className={refreshingFeed ? "spin" : ""} />
              <span>Actualiser</span>
            </button>
          </div>
        </div>

        {loading && feedItems.length === 0 ? (
          <div className="finance-panel-empty">
            <LoaderCircle size={16} className="spin" /> Chargement des dépêches EODHD pour {companyName || symbol}…
          </div>
        ) : feedItems.length === 0 ? (
          <div className="finance-panel-empty">
            Aucune dépêche EODHD récente retournée pour <strong>{symbol}</strong>. Utilisez « Nouvelle veille IA » pour
            lancer une recherche web élargie.
          </div>
        ) : (
          <div className="finance-dossier-news-list">
            {feedItems.map((item, idx) => {
              const safeUrl = /^https?:\/\//i.test(item.url) ? item.url : "";
              const pol = item.sentiment?.polarity;
              const sentLabel =
                pol == null ? null : pol >= 0.15 ? "Positif" : pol <= -0.15 ? "Négatif" : "Neutre";
              const sentCls =
                pol == null ? "" : pol >= 0.15 ? "is-pos" : pol <= -0.15 ? "is-neg" : "is-neu";
              return (
                <article key={`feed-${idx}-${item.url}`} className="finance-dossier-news-card">
                  <div className="finance-dossier-news-head">
                    {safeUrl ? (
                      <a href={safeUrl} target="_blank" rel="noopener noreferrer">
                        {item.title} <ExternalLink size={11} />
                      </a>
                    ) : (
                      <strong>{item.title}</strong>
                    )}
                    {sentLabel && (
                      <span className={`finance-dossier-sentiment-badge ${sentCls}`}>
                        {sentLabel} ({pol! >= 0 ? "+" : ""}
                        {pol!.toFixed(2)})
                      </span>
                    )}
                  </div>
                  <div className="finance-dossier-news-meta">
                    <span>{item.source}</span>
                    {item.published_at && <span>· {item.published_at}</span>}
                    {item.tags && item.tags.length > 0 && (
                      <span className="finance-dossier-news-tags">
                        {item.tags.slice(0, 4).map(t => (
                          <code key={t}>{t}</code>
                        ))}
                      </span>
                    )}
                  </div>
                  {item.snippet && <p className="finance-dossier-news-snippet">{item.snippet}</p>}
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* 2. Historique des veilles & synthèses IA enregistrées */}
      {items.length > 0 && (
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
                    {entry.articles.map((art, i) => {
                      const pol = art.sentiment?.polarity;
                      return (
                        <li key={`${art.url}-${i}`}>
                          <a href={art.url} target="_blank" rel="noreferrer">
                            <span>{art.title}</span>
                            <ExternalLink size={11} />
                          </a>
                          <small>
                            {art.source}
                            {art.published_at ? ` · ${art.published_at}` : ""}
                            {pol != null ? ` · Sentiment ${pol >= 0 ? "+" : ""}${pol.toFixed(2)}` : ""}
                          </small>
                        </li>
                      );
                    })}
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
