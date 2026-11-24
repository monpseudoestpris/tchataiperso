"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Database,
  Eye,
  EyeOff,
  History,
  Lock,
  Play,
  RefreshCw,
  Shuffle,
  Sparkles,
  Trophy,
  Unlock,
  X,
} from "lucide-react";

import {
  FinanceGameControls,
  FinanceGameHistoryDrawer,
  FinanceGameVerdictCard,
} from "@/components/finance-game-hud";
import { FinanceTvChart } from "@/components/finance-tv-chart";
import type {
  CustomIndicator,
  FinanceWatchlistMeta,
  PrincipalIndexInfo,
} from "@/lib/api";
import {
  closeGamePosition,
  fetchGameRound,
  fetchGameState,
  finishGameRound,
  openGamePosition,
  resetGameProfile,
  startGameRound,
  stepGameRound,
  type GameHorizon,
  type GamePositionSide,
  type GameProfile,
  type GameRoundSummary,
  type GameRoundView,
  type GameTimeframe,
  type GameUniverseType,
} from "@/lib/finance-game-api";
import {
  buildRoundChartOverlays,
  formatCurrencyAmount,
  formatSignedCurrency,
  formatSignedPct,
  HORIZONS_BY_TIMEFRAME,
  resolveHorizonForTimeframe,
} from "@/lib/finance-game-helpers";
import type { IndicatorKey } from "@/lib/indicator-params";
import styles from "./finance-game-panel.module.css";

type FinanceGamePanelProps = {
  isActive: boolean;
  dark: boolean;
  indices: PrincipalIndexInfo[];
  watchlists: FinanceWatchlistMeta[];
  activeListId: string | null;
  customIndicators: CustomIndicator[];
  onOpenStock?: (symbol: string, displayName: string, openTab: "fundamentals" | "chart_tech") => void;
  onOpenDataSync?: () => void;
};

const TIMEFRAME_OPTIONS: Array<{ value: GameTimeframe; label: string }> = [
  { value: "day", label: "Jour" },
  { value: "week", label: "Semaine" },
  { value: "month", label: "Mois" },
];

const DEFAULT_GAME_INDICATORS: IndicatorKey[] = ["sma20", "sma50", "volume", "rsi"];

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : "Une erreur est survenue dans le jeu Trading Replay.";
}

/** Arène complète du jeu « Trading Replay » dans le Mode Finance. */
export function FinanceGamePanel({
  isActive,
  dark,
  indices,
  watchlists,
  activeListId,
  customIndicators,
  onOpenStock,
  onOpenDataSync,
}: FinanceGamePanelProps) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<GameProfile | null>(null);
  const [activeRound, setActiveRound] = useState<GameRoundView | null>(null);
  const [inspectedRound, setInspectedRound] = useState<GameRoundView | null>(null);
  const [history, setHistory] = useState<GameRoundSummary[]>([]);
  const [eligibleCount, setEligibleCount] = useState<number>(0);

  // Configuration de tirage
  const [universeType, setUniverseType] = useState<GameUniverseType>("all");
  const [selectedIndex, setSelectedIndex] = useState<string>("");
  const [selectedWatchlist, setSelectedWatchlist] = useState<string>("");
  const [symbolInput, setSymbolInput] = useState<string>("");
  const [timeframe, setTimeframe] = useState<GameTimeframe>("day");
  const [horizonCode, setHorizonCode] = useState<GameHorizon>("3m");
  const [blindMode, setBlindMode] = useState<boolean>(true);

  // État UI local
  const [showHistory, setShowHistory] = useState<boolean>(false);
  const [autoPlaying, setAutoPlaying] = useState<boolean>(false);
  const [autoSpeed, setAutoSpeed] = useState<1 | 2>(1);
  const [gameNativeIndicators, setGameNativeIndicators] = useState<IndicatorKey[]>(DEFAULT_GAME_INDICATORS);
  const [gameCustomIds, setGameCustomIds] = useState<string[]>([]);

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const effectiveIndex = selectedIndex || indices[0]?.code || "";
  const effectiveWatchlist = selectedWatchlist || activeListId || watchlists[0]?.id || "";
  const displayedRound = inspectedRound ?? activeRound;

  const refreshHistory = useCallback(async () => {
    const state = await fetchGameState();
    if (!mountedRef.current) return;
    setProfile(state.profile);
    setHistory(state.history);
    setEligibleCount(state.eligible_symbols_count);
    if (state.active_round) {
      setActiveRound(state.active_round);
    }
  }, []);

  const loadInitialState = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const state = await fetchGameState();
      if (!mountedRef.current) return;
      setProfile(state.profile);
      setActiveRound(state.active_round);
      setHistory(state.history);
      setEligibleCount(state.eligible_symbols_count);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(errorText(err));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const state = await fetchGameState();
        if (cancelled) return;
        setProfile(state.profile);
        setActiveRound(state.active_round);
        setHistory(state.history);
        setEligibleCount(state.eligible_symbols_count);
      } catch (err) {
        if (cancelled) return;
        setError(errorText(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const applyRoundResponse = useCallback(
    (res: { round: GameRoundView; profile: GameProfile }) => {
      if (!mountedRef.current) return;
      setInspectedRound(null);
      setActiveRound(res.round);
      setProfile(res.profile);
      if (res.round.status === "finished" || res.round.remaining_bars <= 0) {
        setAutoPlaying(false);
        if (res.round.status === "finished") {
          void refreshHistory();
        }
      }
      if (res.round.triggered_event === "stop_loss" || res.round.triggered_event === "take_profit") {
        setAutoPlaying(false);
      }
    },
    [refreshHistory],
  );

  const handleStartRound = useCallback(async () => {
    if (busy) return;
    setAutoPlaying(false);
    setBusy(true);
    setError(null);
    try {
      let uVal = "";
      if (universeType === "index") uVal = effectiveIndex;
      else if (universeType === "watchlist") uVal = effectiveWatchlist;
      else if (universeType === "symbol") uVal = symbolInput.trim();

      const res = await startGameRound({
        universe_type: universeType,
        universe_value: uVal,
        timeframe,
        horizon_code: horizonCode,
        blind_mode: blindMode,
      });
      applyRoundResponse(res);
    } catch (err) {
      if (mountedRef.current) setError(errorText(err));
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }, [
    applyRoundResponse,
    blindMode,
    busy,
    effectiveIndex,
    effectiveWatchlist,
    horizonCode,
    symbolInput,
    timeframe,
    universeType,
  ]);

  const handleOpenPosition = useCallback(
    async (side: GamePositionSide, sizePct: number, sl: number | null, tp: number | null) => {
      if (!displayedRound || displayedRound.status !== "active" || busy) return;
      setAutoPlaying(false);
      setBusy(true);
      setError(null);
      try {
        const res = await openGamePosition(displayedRound.id, {
          side,
          size_pct: sizePct,
          stop_loss: sl,
          take_profit: tp,
        });
        applyRoundResponse(res);
      } catch (err) {
        if (mountedRef.current) setError(errorText(err));
      } finally {
        if (mountedRef.current) setBusy(false);
      }
    },
    [applyRoundResponse, busy, displayedRound],
  );

  const handleStep = useCallback(
    async (steps: number) => {
      if (!displayedRound || displayedRound.status !== "active" || busy) return;
      setBusy(true);
      setError(null);
      try {
        const res = await stepGameRound(displayedRound.id, steps);
        applyRoundResponse(res);
      } catch (err) {
        if (mountedRef.current) {
          setAutoPlaying(false);
          setError(errorText(err));
        }
      } finally {
        if (mountedRef.current) setBusy(false);
      }
    },
    [applyRoundResponse, busy, displayedRound],
  );

  const handleClosePosition = useCallback(async () => {
    if (!displayedRound || displayedRound.status !== "active" || busy) return;
    setAutoPlaying(false);
    setBusy(true);
    setError(null);
    try {
      const res = await closeGamePosition(displayedRound.id, false);
      applyRoundResponse(res);
    } catch (err) {
      if (mountedRef.current) setError(errorText(err));
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }, [applyRoundResponse, busy, displayedRound]);

  const handleFinishRound = useCallback(async () => {
    if (!displayedRound || displayedRound.status !== "active" || busy) return;
    setAutoPlaying(false);
    setBusy(true);
    setError(null);
    try {
      const res = await finishGameRound(displayedRound.id);
      applyRoundResponse(res);
    } catch (err) {
      if (mountedRef.current) setError(errorText(err));
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }, [applyRoundResponse, busy, displayedRound]);

  const handleSelectHistoryRound = useCallback(async (roundId: string) => {
    setAutoPlaying(false);
    setBusy(true);
    setError(null);
    try {
      const res = await fetchGameRound(roundId);
      if (!mountedRef.current) return;
      setInspectedRound(res.round);
      setProfile(res.profile);
    } catch (err) {
      if (mountedRef.current) setError(errorText(err));
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }, []);

  const handleResetProfile = useCallback(async (clearHistory: boolean) => {
    setAutoPlaying(false);
    setBusy(true);
    setError(null);
    try {
      const state = await resetGameProfile({ starting_capital: 10000, clear_history: clearHistory });
      if (!mountedRef.current) return;
      setProfile(state.profile);
      setActiveRound(state.active_round);
      setInspectedRound(null);
      setHistory(state.history);
      setEligibleCount(state.eligible_symbols_count);
    } catch (err) {
      if (mountedRef.current) setError(errorText(err));
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }, []);

  // Lecture automatique séquentielle (attend la fin de chaque requête avant la suivante)
  useEffect(() => {
    if (
      !autoPlaying ||
      !isActive ||
      !displayedRound ||
      displayedRound.status !== "active" ||
      displayedRound.remaining_bars <= 0 ||
      busy
    ) {
      return;
    }
    const delayMs = autoSpeed === 2 ? 280 : 620;
    const timer = window.setTimeout(() => {
      void handleStep(1);
    }, delayMs);
    return () => window.clearTimeout(timer);
  }, [autoPlaying, autoSpeed, busy, displayedRound, handleStep, isActive]);

  // Raccourcis clavier (désactivés dans les inputs ou hors onglet actif)
  useEffect(() => {
    if (!isActive) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || target?.isContentEditable) {
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key.toLowerCase();
      if (e.code === "Space" && displayedRound?.status === "active") {
        e.preventDefault();
        void handleStep(1);
      } else if (key === "n") {
        e.preventDefault();
        void handleStartRound();
      } else if (key === "b" && displayedRound?.status === "active" && displayedRound.position_status === "none") {
        e.preventDefault();
        void handleOpenPosition("long", 100, null, null);
      } else if (key === "s" && displayedRound?.status === "active" && displayedRound.position_status === "none") {
        e.preventDefault();
        void handleOpenPosition("short", 100, null, null);
      } else if (key === "c" && displayedRound?.status === "active" && displayedRound.position_status === "open") {
        e.preventDefault();
        void handleClosePosition();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [displayedRound, handleClosePosition, handleOpenPosition, handleStartRound, handleStep, isActive]);

  const overlays = useMemo(
    () => (displayedRound ? buildRoundChartOverlays(displayedRound) : { priceLines: [], markers: [] }),
    [displayedRound],
  );

  if (loading) {
    return (
      <div className={styles.root}>
        <div className={styles.skeletonBox} aria-label="Chargement du simulateur Trading Replay" />
      </div>
    );
  }

  const pnlPositive = (profile?.total_pnl ?? 0) >= 0;
  const isBlindActive = Boolean(
    displayedRound && displayedRound.status === "active" && displayedRound.blind_mode,
  );
  const progressPct = displayedRound
    ? Math.min(100, Math.round((displayedRound.current_step / Math.max(1, displayedRound.horizon_bars)) * 100))
    : 0;

  return (
    <div className={styles.root}>
      {/* Barre supérieure : KPIs portefeuille & configuration de manche */}
      <section className={styles.topCard}>
        <div className={styles.topBar}>
          <div className={styles.titleBlock}>
            <span className={styles.titleIcon}>
              <Trophy size={18} />
            </span>
            <div>
              <h3>Défi Trading Replay</h3>
              <p className={styles.subtitle}>
                Entraînement sur données historiques réelles · 100 % local (0 crédit EODHD) · {eligibleCount}{" "}
                action(s) jouable(s)
              </p>
            </div>
          </div>

          {profile && (
            <div className={styles.kpiStrip}>
              <span className={styles.kpiPill}>
                Capital <strong>{formatCurrencyAmount(profile.equity)}</strong>
              </span>
              <span className={`${styles.kpiPill} ${pnlPositive ? styles.kpiPos : styles.kpiNeg}`}>
                PnL <strong>{formatSignedCurrency(profile.total_pnl)}</strong> (
                {formatSignedPct(profile.total_return_pct)})
              </span>
              <span className={styles.kpiPill}>
                Réussite <strong>{profile.winrate_pct != null ? `${profile.winrate_pct} %` : "—"}</strong>
              </span>
              <span className={styles.kpiPill}>
                Série <strong>{profile.current_streak}</strong> (max {profile.best_streak})
              </span>
              <button
                type="button"
                className={`${styles.toggleBtn} ${showHistory ? styles.toggleBtnActive : ""}`}
                onClick={() => setShowHistory(v => !v)}
              >
                <History size={15} />
                <span>Historique ({history.length})</span>
              </button>
            </div>
          )}
        </div>

        <div className={styles.configRow}>
          <label className={styles.fieldGroup}>
            <span className={styles.fieldLabel}>Univers</span>
            <select
              className={styles.selectInput}
              value={universeType}
              onChange={e => setUniverseType(e.target.value as GameUniverseType)}
              disabled={busy}
            >
              <option value="all">Entrepôt complet</option>
              <option value="index">Indice boursier</option>
              <option value="watchlist">Watchlist</option>
              <option value="symbol">Action précise</option>
            </select>
          </label>

          {universeType === "index" && (
            <label className={styles.fieldGroup}>
              <span className={styles.fieldLabel}>Indice</span>
              <select
                className={styles.selectInput}
                value={effectiveIndex}
                onChange={e => setSelectedIndex(e.target.value)}
                disabled={busy}
              >
                {indices.length === 0 ? (
                  <option value="">Aucun indice synchronisé</option>
                ) : (
                  indices.map(idx => (
                    <option key={idx.code} value={idx.code}>
                      {idx.name} ({idx.code})
                    </option>
                  ))
                )}
              </select>
            </label>
          )}

          {universeType === "watchlist" && (
            <label className={styles.fieldGroup}>
              <span className={styles.fieldLabel}>Liste de suivi</span>
              <select
                className={styles.selectInput}
                value={effectiveWatchlist}
                onChange={e => setSelectedWatchlist(e.target.value)}
                disabled={busy}
              >
                {watchlists.length === 0 ? (
                  <option value="">Aucune watchlist</option>
                ) : (
                  watchlists.map(wl => (
                    <option key={wl.id} value={wl.id}>
                      {wl.name} ({wl.items_count})
                    </option>
                  ))
                )}
              </select>
            </label>
          )}

          {universeType === "symbol" && (
            <label className={styles.fieldGroup}>
              <span className={styles.fieldLabel}>Ticker ou Nom</span>
              <input
                type="text"
                className={styles.textInput}
                placeholder="ex. AI.PA, AAPL.US..."
                value={symbolInput}
                onChange={e => setSymbolInput(e.target.value)}
                disabled={busy}
              />
            </label>
          )}

          <div className={styles.fieldGroup}>
            <span className={styles.fieldLabel}>Unité</span>
            <div className={styles.segmented} role="group" aria-label="Unité de temps">
              {TIMEFRAME_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  disabled={busy}
                  className={`${styles.segmentedBtn} ${timeframe === opt.value ? styles.segmentedBtnActive : ""}`}
                  onClick={() => {
                    setTimeframe(opt.value);
                    setHorizonCode(prev => resolveHorizonForTimeframe(opt.value, prev));
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.fieldGroup}>
            <span className={styles.fieldLabel}>Horizon</span>
            <div className={styles.segmented} role="group" aria-label="Horizon de la manche">
              {HORIZONS_BY_TIMEFRAME[timeframe].map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  disabled={busy}
                  className={`${styles.segmentedBtn} ${horizonCode === opt.value ? styles.segmentedBtnActive : ""}`}
                  onClick={() => setHorizonCode(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            className={`${styles.toggleBtn} ${blindMode ? styles.toggleBtnActive : ""}`}
            onClick={() => setBlindMode(v => !v)}
            disabled={busy}
            title="Masque le nom de l'action, le ticker et les vraies dates pendant la manche"
          >
            {blindMode ? <EyeOff size={15} /> : <Eye size={15} />}
            <span>{blindMode ? "Mode Aveugle" : "Mode Visible"}</span>
          </button>

          <button
            type="button"
            className={`${styles.btn} ${styles.btnAccent}`}
            disabled={busy}
            onClick={() => void handleStartRound()}
          >
            <Shuffle size={15} />
            <span>{activeRound?.status === "active" ? "Nouvelle manche" : "Lancer une manche"}</span>
          </button>
        </div>
      </section>

      {error && (
        <div className={styles.errorBanner} role="alert">
          <span>{error}</span>
          <div className={styles.hudGroup}>
            <button type="button" className={styles.quickChip} onClick={() => void loadInitialState()}>
              <RefreshCw size={12} /> Recharger
            </button>
            <button type="button" className={styles.quickChip} onClick={() => setError(null)} aria-label="Fermer">
              <X size={12} />
            </button>
          </div>
        </div>
      )}

      {showHistory && profile && (
        <FinanceGameHistoryDrawer
          profile={profile}
          history={history}
          busy={busy}
          onSelectRound={id => void handleSelectHistoryRound(id)}
          onResetProfile={clear => void handleResetProfile(clear)}
        />
      )}

      {/* État vide : aucun titre avec assez de barres ou aucune manche encore lancée */}
      {!displayedRound ? (
        <section className={styles.emptyCard}>
          <div className={styles.titleBlock}>
            <span className={styles.titleIcon}>
              <Sparkles size={18} />
            </span>
            <div>
              <h3>
                {eligibleCount === 0
                  ? "Historique EOD local insuffisant pour lancer une manche"
                  : "Prêt pour votre prochain défi boursier"}
              </h3>
              <p className={styles.subtitle}>
                {eligibleCount === 0
                  ? "Synchronisez au moins une action ou un indice avec un historique EOD (>= 125 jours) dans « Données & Synchro »."
                  : "Choisissez votre univers, l'unité et l'horizon ci-dessus puis cliquez sur « Lancer une manche ». Vous pourrez analyser le graphique avec tous vos indicateurs, ouvrir un Achat ou une Vente, placer un Stop-Loss / Take-Profit et avancer bougie par bougie."}
              </p>
            </div>
          </div>
          <div className={styles.hudGroup}>
            {eligibleCount === 0 && onOpenDataSync ? (
              <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={onOpenDataSync}>
                <Database size={15} />
                <span>Ouvrir Données &amp; Synchro</span>
              </button>
            ) : (
              <button
                type="button"
                className={`${styles.btn} ${styles.btnAccent}`}
                disabled={busy}
                onClick={() => void handleStartRound()}
              >
                <Play size={15} />
                <span>Démarrer immédiatement</span>
              </button>
            )}
          </div>
        </section>
      ) : (
        <>
          {inspectedRound && activeRound && activeRound.status === "active" && (
            <div className={`${styles.eventNotice} ${styles.eventInfo}`}>
              <span>
                Consultation d&apos;une manche archivée ({inspectedRound.symbol}) en lecture seule.
              </span>
              <button type="button" className={styles.quickChip} onClick={() => setInspectedRound(null)}>
                Revenir à la manche en cours
              </button>
            </div>
          )}

          <section className={styles.arenaCard}>
            <div className={styles.contextBanner}>
              <div className={styles.assetIdentity}>
                <span className={styles.assetBadge}>
                  {isBlindActive ? <Lock size={12} /> : <Unlock size={12} />}
                  <span>
                    {isBlindActive ? "AVEUGLE" : displayedRound.symbol || "RÉVÉLÉ"}
                  </span>
                </span>
                <h4 className={styles.assetTitle}>
                  {displayedRound.company_name}
                  {!isBlindActive && displayedRound.cutoff_date
                    ? ` · T0 : ${displayedRound.cutoff_date}`
                    : ""}
                </h4>
              </div>

              <div className={styles.quoteCluster}>
                <span className={styles.priceMain}>
                  {displayedRound.current_price.toFixed(2)}{" "}
                  {!isBlindActive && displayedRound.currency ? displayedRound.currency : ""}
                </span>
                <span
                  className={`${styles.deltaChip} ${
                    displayedRound.change_from_cutoff_pct >= 0 ? styles.kpiPos : styles.kpiNeg
                  }`}
                >
                  {displayedRound.change_from_cutoff_pct >= 0 ? (
                    <ArrowUpRight size={13} />
                  ) : (
                    <ArrowDownRight size={13} />
                  )}
                  <span>Depuis T0 : {formatSignedPct(displayedRound.change_from_cutoff_pct)}</span>
                </span>
              </div>
            </div>

            <div className={styles.progressWrap}>
              <span>
                Progression : <strong>{displayedRound.current_step}</strong> / {displayedRound.horizon_bars}{" "}
                bougies ({displayedRound.horizon_code})
              </span>
              <div className={styles.progressTrack} aria-hidden="true">
                <div className={styles.progressFill} style={{ width: `${progressPct}%` }} />
              </div>
              <span>
                {displayedRound.status === "finished"
                  ? "Manche terminée"
                  : `${displayedRound.remaining_bars} restante(s)`}
              </span>
            </div>

            {displayedRound.triggered_event === "take_profit" && (
              <div className={`${styles.eventNotice} ${styles.eventSuccess}`}>
                <span>
                  Take-Profit déclenché à {displayedRound.exit_price?.toFixed(2)} (
                  {formatSignedPct(displayedRound.return_pct)} · {formatSignedCurrency(displayedRound.pnl_amount)}) !
                </span>
              </div>
            )}
            {displayedRound.triggered_event === "stop_loss" && (
              <div className={`${styles.eventNotice} ${styles.eventDanger}`}>
                <span>
                  Stop-Loss déclenché à {displayedRound.exit_price?.toFixed(2)} (
                  {formatSignedPct(displayedRound.return_pct)} · {formatSignedCurrency(displayedRound.pnl_amount)}).
                </span>
              </div>
            )}

            <div className={styles.chartShell}>
              <FinanceTvChart
                bars={displayedRound.bars}
                symbol={displayedRound.is_revealed && displayedRound.symbol ? displayedRound.symbol : "MYSTERE"}
                tabId={`game-${displayedRound.id}`}
                dark={dark}
                customIndicators={customIndicators}
                activeNativeKeys={gameNativeIndicators}
                onChangeActiveNativeKeys={setGameNativeIndicators}
                activeCustomIds={gameCustomIds}
                onChangeActiveCustomIds={setGameCustomIds}
                priceLines={overlays.priceLines}
                markers={overlays.markers}
                blindCutoffIndex={isBlindActive ? displayedRound.cutoff_index : null}
                blindTimeframe={displayedRound.timeframe}
                disableDrawingsPersistence
              />
            </div>
          </section>

          {displayedRound.status === "active" ? (
            <FinanceGameControls
              key={displayedRound.id}
              round={displayedRound}
              busy={busy}
              autoPlaying={autoPlaying}
              autoSpeed={autoSpeed}
              onToggleAutoPlay={() => setAutoPlaying(v => !v)}
              onChangeAutoSpeed={setAutoSpeed}
              onOpenPosition={(side, sizePct, sl, tp) => void handleOpenPosition(side, sizePct, sl, tp)}
              onStep={steps => void handleStep(steps)}
              onClosePosition={() => void handleClosePosition()}
              onFinishRound={() => void handleFinishRound()}
            />
          ) : (
            <FinanceGameVerdictCard
              round={displayedRound}
              busy={busy}
              onNextRound={() => void handleStartRound()}
              onOpenStock={onOpenStock}
            />
          )}
        </>
      )}
    </div>
  );
}
