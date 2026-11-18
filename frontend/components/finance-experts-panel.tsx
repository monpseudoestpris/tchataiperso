"use client";

import {
  ChevronDown,
  Eye,
  History,
  LoaderCircle,
  Send,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  deleteFinanceAiHistoryItem,
  fetchFinanceExperts,
  requestFinanceExpertOpinion,
  type FinanceExpertOpinion,
  type FinanceExpertPersona,
  type Model,
} from "@/lib/api";
import { useModelFavorites } from "@/lib/model-favorites";

type FinanceExpertsPanelProps = {
  symbol: string;
  companyName: string;
  selectedModel: string;
  selectedModelInfo?: Model;
  onOpenModelModal: () => void;
  onInsertIntoChat?: (text: string) => void;
};

function fmtShortDate(iso?: string | null): string {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso.slice(0, 16);
  return dt.toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Onglet « Avis des Experts » : analyse datée et archivée en HTML coloré par des personnalités célèbres. */
export function FinanceExpertsPanel({
  symbol,
  companyName,
  selectedModel,
  selectedModelInfo,
  onOpenModelModal,
  onInsertIntoChat,
}: FinanceExpertsPanelProps) {
  const { isFavorite } = useModelFavorites();
  const [loadedState, setLoadedState] = useState<{
    loadedSymbol: string;
    experts: FinanceExpertPersona[];
    opinionsById: Record<string, FinanceExpertOpinion>;
    history: FinanceExpertOpinion[];
    fetchError: string | null;
  }>({
    loadedSymbol: "",
    experts: [],
    opinionsById: {},
    history: [],
    fetchError: null,
  });
  const [selectedExpertId, setSelectedExpertId] = useState<string>("warren_buffett");
  const [selectedHistoryByExpert, setSelectedHistoryByExpert] = useState<Record<string, string>>({});
  const [question, setQuestion] = useState("");
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFinanceExperts(symbol)
      .then(res => {
        if (cancelled) return;
        setLoadedState({
          loadedSymbol: symbol,
          experts: res.experts || [],
          opinionsById: res.cached_opinions || {},
          history: res.history || [],
          fetchError: null,
        });
      })
      .catch(err => {
        if (!cancelled) {
          setLoadedState(prev => ({
            ...prev,
            loadedSymbol: symbol,
            fetchError: err instanceof Error ? err.message : "Impossible de charger les profils d'experts.",
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const loadingList = loadedState.loadedSymbol !== symbol && !loadedState.fetchError;
  const experts = loadedState.experts;
  const opinionsById = loadedState.opinionsById;
  const allHistory = loadedState.history;
  const error = actionError || (loadedState.loadedSymbol === symbol ? loadedState.fetchError : null);
  const activeExpert = experts.find(e => e.id === selectedExpertId) ?? experts[0] ?? null;
  const expertHistory = activeExpert ? allHistory.filter(h => h.expert_id === activeExpert.id) : [];
  const selectedEntryId = activeExpert ? selectedHistoryByExpert[activeExpert.id] : undefined;
  const activeOpinion =
    (selectedEntryId ? expertHistory.find(h => h.id === selectedEntryId) : undefined) ??
    expertHistory[0] ??
    (activeExpert ? opinionsById[activeExpert.id] : undefined);
  const isGeneratingCurrent = Boolean(activeExpert && generatingId === activeExpert.id);

  const modelPriceLabel = (() => {
    if (!selectedModelInfo) return null;
    if (selectedModelInfo.prompt_price_1m === 0 && selectedModelInfo.completion_price_1m === 0) return "Gratuit";
    if (selectedModelInfo.prompt_price_1m != null) return `$${selectedModelInfo.prompt_price_1m.toFixed(2)}/M`;
    return null;
  })();

  async function handleConsult(expertIdOverride?: string) {
    const targetId = expertIdOverride || activeExpert?.id;
    if (!targetId || generatingId) return;
    setGeneratingId(targetId);
    setActionError(null);
    try {
      const res = await requestFinanceExpertOpinion({
        symbol,
        expertId: targetId,
        modelId: selectedModel || null,
        question: question.trim() || null,
      });
      setLoadedState(prev => ({
        ...prev,
        opinionsById: { ...prev.opinionsById, [res.expert_id]: res },
        history: [res, ...prev.history.filter(h => h.id !== res.id)],
      }));
      if (res.id) {
        setSelectedHistoryByExpert(prev => ({ ...prev, [res.expert_id]: res.id! }));
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Erreur lors de la consultation de l'expert.");
    } finally {
      setGeneratingId(null);
    }
  }

  async function handleDeleteHistoryItem(entry: FinanceExpertOpinion) {
    if (!entry.id) return;
    try {
      await deleteFinanceAiHistoryItem(entry.id);
      setLoadedState(prev => {
        const nextHistory = prev.history.filter(h => h.id !== entry.id);
        const latestForExp = nextHistory.find(h => h.expert_id === entry.expert_id);
        const nextById = { ...prev.opinionsById };
        if (latestForExp) nextById[entry.expert_id] = latestForExp;
        else delete nextById[entry.expert_id];
        return { ...prev, history: nextHistory, opinionsById: nextById };
      });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  return (
    <div className="finance-experts-wrap">
      <div className="finance-experts-toolbar">
        <div className="finance-experts-intro">
          <h3>Avis des Grands Experts sur {companyName} ({symbol})</h3>
          <p>
            Chaque consultation est <strong>sauvegardée, datée et archivée en HTML</strong> pour y revenir à tout moment (bilans 5–10 ans, valeurs intrinsèques, 31 scores, actualités EODHD/SearXNG &amp; macro).
          </p>
        </div>

        <div className="finance-experts-model-bar">
          <span className="finance-experts-model-label">Modèle IA :</span>
          <button
            type="button"
            className="model-selector-btn finance-experts-model-btn"
            onClick={onOpenModelModal}
            title="Choisir le modèle IA dans la modale habituelle"
            aria-label="Choisir le modèle IA pour l'avis de l'expert"
          >
            <span className="model-indicator" />
            {selectedModel && isFavorite(selectedModel) && (
              <Star size={11} fill="#f59e0b" color="#f59e0b" />
            )}
            <span className="model-current-name">
              {selectedModelInfo?.name || selectedModel || "Choisir un modèle IA"}
            </span>
            {selectedModelInfo?.vision && (
              <span className="model-topbar-pill vision">
                <Eye size={11} />
                <span>Vision</span>
              </span>
            )}
            {modelPriceLabel && (
              <span className={`model-topbar-pill price ${modelPriceLabel === "Gratuit" ? "is-free" : ""}`}>
                {modelPriceLabel}
              </span>
            )}
            <ChevronDown size={14} className="model-chevron" />
          </button>
        </div>
      </div>

      {loadingList && experts.length === 0 ? (
        <p className="finance-dossier-ai-placeholder">Chargement du panel des experts financiers…</p>
      ) : (
        <div className="finance-experts-grid" role="listbox" aria-label="Choisir un expert financier">
          {experts.map(exp => {
            const isSelected = exp.id === (activeExpert?.id || selectedExpertId);
            const expHistCount = allHistory.filter(h => h.expert_id === exp.id).length;
            const hasCached = expHistCount > 0 || Boolean(opinionsById[exp.id]);
            const isBusy = generatingId === exp.id;
            return (
              <button
                key={exp.id}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`finance-expert-card ${isSelected ? "is-selected" : ""}`}
                onClick={() => setSelectedExpertId(exp.id)}
              >
                <div className="finance-expert-card-top">
                  <span
                    className="finance-expert-avatar"
                    style={{ background: exp.accent }}
                    aria-hidden="true"
                  >
                    {exp.monogram}
                  </span>
                  <div className="finance-expert-card-titles">
                    <strong>{exp.name}</strong>
                    <small>{exp.era_firm}</small>
                  </div>
                  {isBusy ? (
                    <LoaderCircle size={14} className="spin finance-expert-status-icon" />
                  ) : hasCached ? (
                    <span className="finance-expert-cached-pill" title="Avis archivé(s) pour cette action">
                      ✓ {expHistCount > 1 ? `${expHistCount} avis` : "Avis"}
                    </span>
                  ) : null}
                </div>
                <div className="finance-expert-style">{exp.style}</div>
                <div className="finance-expert-metrics">
                  {exp.favorite_metrics.slice(0, 3).map(m => (
                    <span key={m}>{m}</span>
                  ))}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {activeExpert && (
        <div className="finance-expert-consult-box">
          <div className="finance-expert-consult-head">
            <div className="finance-expert-consult-persona">
              <span
                className="finance-expert-avatar is-lg"
                style={{ background: activeExpert.accent }}
              >
                {activeExpert.monogram}
              </span>
              <div>
                <div className="finance-expert-consult-name">
                  <strong>{activeExpert.name}</strong>
                  <span className="finance-expert-style-badge">{activeExpert.style}</span>
                </div>
                <p className="finance-expert-tagline">
                  {activeExpert.tagline} · <em>Collecte automatique des dernières actualités (EODHD / SearXNG) incluse.</em>
                </p>
                <div className="finance-expert-metrics">
                  {activeExpert.favorite_metrics.map(m => (
                    <span key={m}>{m}</span>
                  ))}
                </div>
              </div>
            </div>

            <button
              type="button"
              className="finance-expert-submit-btn"
              disabled={Boolean(generatingId)}
              onClick={() => void handleConsult(activeExpert.id)}
            >
              {isGeneratingCurrent ? (
                <>
                  <LoaderCircle size={15} className="spin" />
                  <span>Analyse en cours…</span>
                </>
              ) : (
                <>
                  <Sparkles size={15} />
                  <span>
                    {activeOpinion
                      ? `Nouvel avis daté (${activeExpert.name})`
                      : `Demander l'avis de ${activeExpert.name}`}
                  </span>
                </>
              )}
            </button>
          </div>

          <form
            className="finance-expert-question-form"
            onSubmit={e => {
              e.preventDefault();
              void handleConsult(activeExpert.id);
            }}
          >
            <input
              type="text"
              className="finance-expert-question-input"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              placeholder={`Question ciblée pour ${activeExpert.name} (optionnel, ex. "À quel prix la marge de sécurité devient-elle irrésistible ?")…`}
              maxLength={400}
              disabled={Boolean(generatingId)}
            />
            <button
              type="submit"
              className="finance-tf-btn active"
              disabled={Boolean(generatingId) || !question.trim()}
              title="Poser cette question précise avec l'ensemble des chiffres du dossier"
            >
              <Send size={13} />
              <span>Poser la question</span>
            </button>
          </form>

          {error && <p className="text-rose">{error}</p>}

          {expertHistory.length > 0 && (
            <div className="finance-ai-history-strip" aria-label="Historique daté de cet expert">
              <span className="finance-ai-history-label">
                <History size={12} />
                <span>Historique daté ({expertHistory.length}) :</span>
              </span>
              <div className="finance-ai-history-pills">
                {expertHistory.map((item, idx) => {
                  const isCurrent = activeOpinion?.id === item.id || (!activeOpinion?.id && idx === 0);
                  return (
                    <div key={item.id || `${idx}-${item.created_at}`} className={`finance-ai-hist-chip ${isCurrent ? "active" : ""}`}>
                      <button
                        type="button"
                        className="finance-ai-hist-chip-btn"
                        onClick={() => {
                          if (item.id) {
                            setSelectedHistoryByExpert(prev => ({ ...prev, [activeExpert.id]: item.id! }));
                          }
                        }}
                        title={item.question ? `Question : ${item.question}` : item.model || ""}
                      >
                        <strong>{fmtShortDate(item.created_at || item.updated_at)}</strong>
                        {item.verdict && <span className="finance-ai-hist-verdict">{item.verdict}</span>}
                        {item.model && <small>{item.model.split("/").pop()}</small>}
                      </button>
                      {item.id && (
                        <button
                          type="button"
                          className="finance-ai-hist-del"
                          onClick={() => void handleDeleteHistoryItem(item)}
                          title="Supprimer cet avis archivé"
                          aria-label="Supprimer cet avis"
                        >
                          <Trash2 size={10} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeOpinion ? (
            <div className="finance-expert-result-card">
              <FinanceRichReport
                contentHtml={activeOpinion.content_html}
                markdown={activeOpinion.markdown}
                newsArticles={activeOpinion.news_articles}
                onInsertIntoChat={onInsertIntoChat}
                meta={{
                  title: `Avis de ${activeExpert.name} — ${companyName || symbol}`,
                  subtitle: `${activeExpert.style} · ${activeExpert.era_firm}`,
                  symbol,
                  model: activeOpinion.model,
                  createdAt: activeOpinion.created_at || activeOpinion.updated_at,
                  accent: activeExpert.accent,
                  badgeLabel: "Avis d'Expert",
                  question: activeOpinion.question,
                  monogram: activeExpert.monogram,
                }}
              />
            </div>
          ) : (
            <div className="finance-expert-empty-state">
              Cliquez sur <strong>« Demander l&apos;avis de {activeExpert.name} »</strong> pour générer et archiver son verdict HTML avec le modèle IA sélectionné ci-dessus ({selectedModelInfo?.name || selectedModel || "par défaut"}).
            </div>
          )}
        </div>
      )}
    </div>
  );
}
