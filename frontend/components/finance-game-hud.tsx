"use client";

import { useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ExternalLink,
  FastForward,
  Flag,
  History,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  StepForward,
  TrendingDown,
  TrendingUp,
  Trophy,
  XCircle,
} from "lucide-react";

import type {
  GameExitReason,
  GamePositionSide,
  GameProfile,
  GameRoundSummary,
  GameRoundView,
} from "@/lib/finance-game-api";
import {
  computeQuickSlTp,
  formatCurrencyAmount,
  formatSignedCurrency,
  formatSignedPct,
} from "@/lib/finance-game-helpers";
import styles from "./finance-game-panel.module.css";

const EXIT_REASON_LABELS: Record<GameExitReason, string> = {
  manual: "Clôture manuelle",
  stop_loss: "Stop-Loss déclenché",
  take_profit: "Take-Profit atteint",
  horizon_end: "Fin de l'horizon",
  skipped: "Manche passée",
};

const STAKE_PCT_OPTIONS = [25, 50, 100] as const;

type FinanceGameControlsProps = {
  round: GameRoundView;
  busy: boolean;
  autoPlaying: boolean;
  autoSpeed: 1 | 2;
  onToggleAutoPlay: () => void;
  onChangeAutoSpeed: (speed: 1 | 2) => void;
  onOpenPosition: (side: GamePositionSide, sizePct: number, sl: number | null, tp: number | null) => void;
  onStep: (steps: number) => void;
  onClosePosition: () => void;
  onFinishRound: () => void;
};

export function FinanceGameControls({
  round,
  busy,
  autoPlaying,
  autoSpeed,
  onToggleAutoPlay,
  onChangeAutoSpeed,
  onOpenPosition,
  onStep,
  onClosePosition,
  onFinishRound,
}: FinanceGameControlsProps) {
  const [sizePct, setSizePct] = useState<number>(100);
  const [slInput, setSlInput] = useState<string>("");
  const [tpInput, setTpInput] = useState<string>("");

  const parseOptionalNumber = (raw: string): number | null => {
    const clean = raw.trim().replace(",", ".");
    if (!clean) return null;
    const num = Number(clean);
    return Number.isFinite(num) && num > 0 ? num : null;
  };

  const applyPreset = (side: GamePositionSide, slPct: number, tpPct: number) => {
    const { sl, tp } = computeQuickSlTp(round.current_price, side, slPct, tpPct);
    setSlInput(String(sl));
    setTpInput(String(tp));
  };

  const replayBar = (
    <div className={styles.hudGroup}>
      <button
        type="button"
        className={styles.btn}
        disabled={busy || autoPlaying || round.remaining_bars <= 0}
        onClick={() => onStep(1)}
        title="Avancer d'une bougie (Raccourci : Espace)"
      >
        <StepForward size={15} />
        <span>+1</span>
      </button>
      <button
        type="button"
        className={styles.btn}
        disabled={busy || autoPlaying || round.remaining_bars <= 0}
        onClick={() => onStep(5)}
        title="Avancer de 5 bougies"
      >
        <FastForward size={15} />
        <span>+5</span>
      </button>
      <button
        type="button"
        className={`${styles.btn} ${autoPlaying ? styles.btnAccent : ""}`}
        disabled={busy && !autoPlaying}
        onClick={onToggleAutoPlay}
        title={autoPlaying ? "Mettre la lecture en pause" : "Lecture automatique bougie par bougie"}
      >
        {autoPlaying ? <Pause size={15} /> : <Play size={15} />}
        <span>{autoPlaying ? "Pause" : "Lecture"}</span>
      </button>
      <div className={styles.segmented} role="group" aria-label="Vitesse de lecture">
        <button
          type="button"
          className={`${styles.segmentedBtn} ${autoSpeed === 1 ? styles.segmentedBtnActive : ""}`}
          onClick={() => onChangeAutoSpeed(1)}
        >
          ×1
        </button>
        <button
          type="button"
          className={`${styles.segmentedBtn} ${autoSpeed === 2 ? styles.segmentedBtnActive : ""}`}
          onClick={() => onChangeAutoSpeed(2)}
        >
          ×2
        </button>
      </div>
    </div>
  );

  if (round.position_status === "none") {
    return (
      <section className={styles.hudCard} aria-label="Passage d'ordre et pilotage Replay">
        <div className={styles.hudGrid}>
          <div className={styles.hudGroup}>
            <span className={styles.fieldLabel}>Mise</span>
            <div className={styles.segmented} role="group" aria-label="Taille de la mise">
              {STAKE_PCT_OPTIONS.map(pct => (
                <button
                  key={pct}
                  type="button"
                  disabled={busy}
                  className={`${styles.segmentedBtn} ${sizePct === pct ? styles.segmentedBtnActive : ""}`}
                  onClick={() => setSizePct(pct)}
                >
                  {pct}%
                </button>
              ))}
            </div>

            <label className={styles.fieldGroup}>
              <span className={styles.fieldLabel}>Stop-Loss</span>
              <input
                type="text"
                inputMode="decimal"
                className={styles.numberInput}
                placeholder="Optionnel"
                value={slInput}
                disabled={busy}
                onChange={e => setSlInput(e.target.value)}
                aria-label="Prix Stop-Loss optionnel"
              />
            </label>

            <label className={styles.fieldGroup}>
              <span className={styles.fieldLabel}>Take-Profit</span>
              <input
                type="text"
                inputMode="decimal"
                className={styles.numberInput}
                placeholder="Optionnel"
                value={tpInput}
                disabled={busy}
                onChange={e => setTpInput(e.target.value)}
                aria-label="Prix Take-Profit optionnel"
              />
            </label>

            <div className={styles.hudGroup}>
              <button
                type="button"
                className={styles.quickChip}
                disabled={busy}
                onClick={() => applyPreset("long", 5, 10)}
                title="Pré-remplir SL -5 % / TP +10 % pour un Achat"
              >
                Long ±5/10%
              </button>
              <button
                type="button"
                className={styles.quickChip}
                disabled={busy}
                onClick={() => applyPreset("short", 5, 10)}
                title="Pré-remplir SL +5 % / TP -10 % pour une Vente"
              >
                Short ±5/10%
              </button>
              {(slInput || tpInput) && (
                <button
                  type="button"
                  className={styles.quickChip}
                  disabled={busy}
                  onClick={() => {
                    setSlInput("");
                    setTpInput("");
                  }}
                >
                  Effacer SL/TP
                </button>
              )}
            </div>
          </div>
        </div>

        <div className={styles.hudGrid}>
          <div className={styles.hudGroup}>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnBuy}`}
              disabled={busy || autoPlaying}
              onClick={() =>
                onOpenPosition("long", sizePct, parseOptionalNumber(slInput), parseOptionalNumber(tpInput))
              }
              title="Acheter / Long au cours courant (Raccourci : B)"
            >
              <TrendingUp size={16} />
              <span>Acheter (Long)</span>
            </button>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnSell}`}
              disabled={busy || autoPlaying}
              onClick={() =>
                onOpenPosition("short", sizePct, parseOptionalNumber(slInput), parseOptionalNumber(tpInput))
              }
              title="Vendre à découvert / Short au cours courant (Raccourci : S)"
            >
              <TrendingDown size={16} />
              <span>Vendre (Short)</span>
            </button>
          </div>

          <div className={styles.hudGroup}>
            {replayBar}
            <button
              type="button"
              className={styles.btn}
              disabled={busy}
              onClick={onFinishRound}
              title="Passer cette manche et révéler la suite"
            >
              <SkipForward size={15} />
              <span>Passer &amp; Révéler</span>
            </button>
          </div>
        </div>

        <span className={styles.shortcutHint}>
          Raccourcis clavier : Espace (+1 bougie) · B (Acheter) · S (Vendre) · N (Nouvelle manche)
        </span>
      </section>
    );
  }

  if (round.position_status === "open") {
    const isLong = round.position_side === "long";
    const latentPositive = (round.unrealized_pnl ?? 0) >= 0;
    return (
      <section className={styles.hudCard} aria-label="Position ouverte et pilotage Replay">
        <div className={styles.positionStrip}>
          <strong>{isLong ? "Position ACHETEUR (Long)" : "Position VENDEUR (Short)"}</strong>
          <span>Entrée : <strong>{round.entry_price?.toFixed(2)}</strong></span>
          <span>Mise : <strong>{formatCurrencyAmount(round.stake_amount)}</strong> ({round.position_size_pct}%)</span>
          {round.stop_loss != null && <span>SL : <strong>{round.stop_loss.toFixed(2)}</strong></span>}
          {round.take_profit != null && <span>TP : <strong>{round.take_profit.toFixed(2)}</strong></span>}
          <span className={`${styles.kpiPill} ${latentPositive ? styles.kpiPos : styles.kpiNeg}`}>
            Latent : <strong>{formatSignedPct(round.unrealized_return_pct)}</strong> ({formatSignedCurrency(round.unrealized_pnl)})
          </span>
        </div>

        <div className={styles.hudGrid}>
          {replayBar}
          <div className={styles.hudGroup}>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimary}`}
              disabled={busy}
              onClick={onClosePosition}
              title="Clôturer votre position au cours courant (Raccourci : C)"
            >
              <Flag size={15} />
              <span>Clôturer la position</span>
            </button>
            <button
              type="button"
              className={styles.btn}
              disabled={busy}
              onClick={onFinishRound}
              title="Simuler jusqu'à la fin de l'horizon et révéler"
            >
              <SkipForward size={15} />
              <span>Aller à la fin</span>
            </button>
          </div>
        </div>
      </section>
    );
  }

  // Position déjà clôturée avant la fin de l'horizon : on peut encore observer les bougies restantes
  const realizedPositive = (round.pnl_amount ?? 0) >= 0;
  return (
    <section className={styles.hudCard} aria-label="Position clôturée, observation de la suite">
      <div className={styles.positionStrip}>
        <span>
          Trade verrouillé ({round.position_side === "long" ? "Long" : "Short"} ·{" "}
          {round.exit_reason ? EXIT_REASON_LABELS[round.exit_reason] : "Clôturé"})
        </span>
        <span className={`${styles.kpiPill} ${realizedPositive ? styles.kpiPos : styles.kpiNeg}`}>
          <strong>{formatSignedPct(round.return_pct)}</strong> · {formatSignedCurrency(round.pnl_amount)}
        </span>
      </div>

      <div className={styles.hudGrid}>
        {replayBar}
        <button
          type="button"
          className={`${styles.btn} ${styles.btnAccent}`}
          disabled={busy}
          onClick={onFinishRound}
        >
          <SkipForward size={15} />
          <span>Révéler la suite et l&apos;action</span>
        </button>
      </div>
    </section>
  );
}

type FinanceGameVerdictCardProps = {
  round: GameRoundView;
  busy: boolean;
  onNextRound: () => void;
  onOpenStock?: (symbol: string, displayName: string, openTab: "fundamentals" | "chart_tech") => void;
};

export function FinanceGameVerdictCard({
  round,
  busy,
  onNextRound,
  onOpenStock,
}: FinanceGameVerdictCardProps) {
  const skipped = round.position_status === "skipped";
  const isWin = !skipped && (round.pnl_amount ?? 0) > 0;
  const isLoss = !skipped && (round.pnl_amount ?? 0) < 0;

  return (
    <section className={styles.verdictCard} aria-label="Verdict final et révélation">
      <div className={styles.topBar}>
        <div className={styles.titleBlock}>
          <span className={styles.titleIcon}>
            {isWin ? <CheckCircle2 size={18} /> : isLoss ? <XCircle size={18} /> : <Trophy size={18} />}
          </span>
          <div>
            <h3>
              {round.company_name} ({round.symbol || "—"})
            </h3>
            <p className={styles.subtitle}>
              {round.exchange ? `${round.exchange} · ` : ""}
              {round.sector ? `${round.sector} · ` : ""}
              Période réelle : {round.cutoff_date || "—"} → {round.end_date || "—"}
            </p>
          </div>
        </div>

        <div className={styles.hudGroup}>
          {round.symbol && onOpenStock && (
            <button
              type="button"
              className={styles.btn}
              onClick={() => onOpenStock(round.symbol!, round.company_name, "fundamentals")}
            >
              <ExternalLink size={14} />
              <span>Ouvrir la fiche complète</span>
            </button>
          )}
          <button
            type="button"
            className={`${styles.btn} ${styles.btnAccent}`}
            disabled={busy}
            onClick={onNextRound}
          >
            <Play size={14} />
            <span>Manche suivante</span>
          </button>
        </div>
      </div>

      <div className={styles.verdictGrid}>
        <div className={styles.verdictMetric}>
          <span className={styles.verdictMetricLabel}>Résultat du trade</span>
          <span className={styles.verdictMetricValue}>
            {skipped ? "Passé" : formatSignedPct(round.return_pct)}
          </span>
          <span className={styles.subtitle}>
            {round.exit_reason ? EXIT_REASON_LABELS[round.exit_reason] : "—"}
          </span>
        </div>

        <div className={styles.verdictMetric}>
          <span className={styles.verdictMetricLabel}>Impact portefeuille</span>
          <span className={styles.verdictMetricValue}>
            {skipped ? "0,00 €" : formatSignedCurrency(round.pnl_amount)}
          </span>
          <span className={styles.subtitle}>
            {round.position_side ? (round.position_side === "long" ? "Sens Achat (Long)" : "Sens Vente (Short)") : "Sans position"}
          </span>
        </div>

        <div className={styles.verdictMetric}>
          <span className={styles.verdictMetricLabel}>Buy &amp; Hold sur la période</span>
          <span className={styles.verdictMetricValue}>
            {formatSignedPct(round.buy_hold_return_pct)}
          </span>
          <span className={styles.subtitle}>Performance passive T0 → Fin</span>
        </div>

        <div className={styles.verdictMetric}>
          <span className={styles.verdictMetricLabel}>Cours T0 → Fin</span>
          <span className={styles.verdictMetricValue}>
            {round.cutoff_price.toFixed(2)} → {round.current_price.toFixed(2)}
          </span>
          <span className={styles.subtitle}>
            {round.currency || "Devise locale"}
          </span>
        </div>
      </div>
    </section>
  );
}

type FinanceGameHistoryDrawerProps = {
  profile: GameProfile;
  history: GameRoundSummary[];
  busy: boolean;
  onSelectRound: (roundId: string) => void;
  onResetProfile: (clearHistory: boolean) => void;
};

export function FinanceGameHistoryDrawer({
  profile,
  history,
  busy,
  onSelectRound,
  onResetProfile,
}: FinanceGameHistoryDrawerProps) {
  const [confirmReset, setConfirmReset] = useState(false);

  return (
    <section className={styles.historyCard} aria-label="Statistiques et historique des manches">
      <div className={styles.topBar}>
        <div className={styles.titleBlock}>
          <span className={styles.titleIcon}>
            <History size={16} />
          </span>
          <div>
            <h3>Portefeuille Virtuel &amp; Historique</h3>
            <p className={styles.subtitle}>
              {profile.rounds_played} manche(s) jouée(s) · {profile.trades_taken} trade(s) ·{" "}
              {profile.wins}G / {profile.losses}P / {profile.draws}N · Profit Factor :{" "}
              {profile.profit_factor != null ? profile.profit_factor.toFixed(2) : "—"} · Meilleure série :{" "}
              {profile.best_streak}
            </p>
          </div>
        </div>

        <div className={styles.hudGroup}>
          {!confirmReset ? (
            <button
              type="button"
              className={`${styles.btn} ${styles.btnDangerOutline}`}
              disabled={busy}
              onClick={() => setConfirmReset(true)}
            >
              <RotateCcw size={14} />
              <span>Réinitialiser (10 000 €)</span>
            </button>
          ) : (
            <>
              <button
                type="button"
                className={`${styles.btn} ${styles.btnSell}`}
                disabled={busy}
                onClick={() => {
                  setConfirmReset(false);
                  onResetProfile(true);
                }}
              >
                Confirmer (effacer tout)
              </button>
              <button
                type="button"
                className={styles.btn}
                disabled={busy}
                onClick={() => setConfirmReset(false)}
              >
                Annuler
              </button>
            </>
          )}
        </div>
      </div>

      {history.length === 0 ? (
        <p className={styles.subtitle}>Aucune manche terminée pour le moment.</p>
      ) : (
        <div className={styles.historyTableWrap}>
          <table className={styles.historyTable}>
            <thead>
              <tr>
                <th>Action</th>
                <th>Période</th>
                <th>Sens</th>
                <th>Sortie</th>
                <th>Perf</th>
                <th>PnL</th>
                <th>Buy &amp; Hold</th>
              </tr>
            </thead>
            <tbody>
              {history.map(item => {
                const pnlPos = (item.pnl_amount ?? 0) > 0;
                const pnlNeg = (item.pnl_amount ?? 0) < 0;
                return (
                  <tr
                    key={item.id}
                    className={styles.historyRowBtn}
                    onClick={() => onSelectRound(item.id)}
                    title="Cliquer pour revoir le graphique de cette manche"
                  >
                    <td>
                      <strong>{item.symbol}</strong> · {item.company_name}
                    </td>
                    <td>
                      {item.cutoff_date} → {item.end_date}
                    </td>
                    <td>
                      {item.position_side === "long" ? (
                        <span className={styles.deltaChip}>
                          <ArrowUpRight size={12} /> Long
                        </span>
                      ) : item.position_side === "short" ? (
                        <span className={styles.deltaChip}>
                          <ArrowDownRight size={12} /> Short
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{item.exit_reason ? EXIT_REASON_LABELS[item.exit_reason] : "—"}</td>
                    <td>{formatSignedPct(item.return_pct)}</td>
                    <td style={{ color: pnlPos ? "var(--status-success-ink)" : pnlNeg ? "var(--status-danger-ink)" : undefined }}>
                      <strong>{item.pnl_amount != null ? formatSignedCurrency(item.pnl_amount) : "—"}</strong>
                    </td>
                    <td>{formatSignedPct(item.buy_hold_return_pct)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
